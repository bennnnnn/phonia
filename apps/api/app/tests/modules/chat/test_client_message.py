"""One turn per client message: a resend of a message the server took never runs twice.

The phone sends a message again, with the same ``client_message_id``, when its
socket went quiet before ``start`` (the first send may or may not have arrived),
over SSE, or from Retry. Without the claim a resend after the first turn finished
was a second turn: the same question answered and charged twice. SSE is in
``test_client_message_sse.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import TimeoutError as RedisTimeoutError
from starlette.websockets import WebSocketDisconnect

from app.core.access_tokens import create_access_token
from app.core.background_tasks import drain_background_tasks
from app.core.config import Settings
from app.exceptions import QuotaExceededError, RedisUnavailableError
from app.main import create_app
from app.modules.chat.client_message import (
    CLAIM_RUNNING_TTL_SECONDS,
    CLAIM_SAVED_TTL_SECONDS,
    UNNAMED,
    ClientMessageClaim,
    claim_client_message,
    claim_key,
)
from app.modules.chat.turn_outcome import TurnOutcome
from app.tests.modules.chat.chat_test_support import signed_in, ws_streams

_SECRET = "super-secret-key-that-is-at-least-32-chars!!"


class SetThenFail:
    """Redis whose SET lands and then times out: the reply never reached us."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def set(self, *args: Any, **kwargs: Any) -> Any:
        await self._inner.set(*args, **kwargs)
        raise RedisTimeoutError("Timeout reading from socket")


class SlowReply:
    """Redis whose commands land at once and answer after ``delay``."""

    def __init__(self, inner: Any, delay: float) -> None:
        self._inner, self._delay = inner, delay

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)
        if not callable(target):
            return target

        async def call(*args: Any, **kwargs: Any) -> Any:
            result = await target(*args, **kwargs)
            await asyncio.sleep(self._delay)
            return result

        return call


# ── the claim ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_client_message_without_a_name_is_never_a_duplicate(fake_redis) -> None:
    for _ in range(2):
        claim = await claim_client_message(
            fake_redis, user_id=uuid4(), chat_id=uuid4(), client_message_id=None
        )
        assert claim is UNNAMED
    assert await fake_redis.dbsize() == 0


@pytest.mark.asyncio
async def test_claim_client_message_lets_one_turn_take_a_name(fake_redis) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    first = await claim_client_message(
        fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
    )
    again = await claim_client_message(
        fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
    )
    other_chat = await claim_client_message(
        fake_redis, user_id=user_id, chat_id=uuid4(), client_message_id=name
    )
    assert first is not None and first is not UNNAMED
    assert again is None
    assert other_chat is not None
    ttl = await fake_redis.ttl(claim_key(user_id, chat_id, name))
    assert 0 < ttl <= CLAIM_RUNNING_TTL_SECONDS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome, kept",
    [
        (TurnOutcome(), False),
        (TurnOutcome(user_message_saved=True), True),
        (TurnOutcome(message_id="reply"), True),
    ],
    ids=["nothing-saved", "message-saved", "reply-saved"],
)
async def test_claim_settle_frees_an_unsaved_turn_and_keeps_a_saved_one(
    fake_redis, outcome: TurnOutcome, kept: bool
) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    claim = await claim_client_message(
        fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
    )
    assert claim is not None
    await claim.settle(outcome)
    ttl = await fake_redis.ttl(claim_key(user_id, chat_id, name))
    if kept:
        assert CLAIM_RUNNING_TTL_SECONDS < ttl <= CLAIM_SAVED_TTL_SECONDS
    else:
        assert ttl == -2  # gone: a resend after a refusal runs
        resend = await claim_client_message(
            fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
        )
        assert resend is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [TurnOutcome(), TurnOutcome(user_message_saved=True)])
async def test_claim_settle_leaves_a_hold_that_is_no_longer_its_own(
    fake_redis, outcome: TurnOutcome
) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    key = claim_key(user_id, chat_id, name)
    claim = await claim_client_message(
        fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
    )
    assert claim is not None
    await fake_redis.set(key, "a later turn's hold", ex=60)  # this claim's TTL ran out
    await claim.settle(outcome)
    assert await fake_redis.get(key) == "a later turn's hold"
    assert await fake_redis.ttl(key) <= 60


@pytest.mark.asyncio
async def test_claim_client_message_fails_closed_and_frees_a_set_that_landed(fake_redis) -> None:
    """Regression: a Redis error let the turn run unclaimed (a replay could run a
    second turn), and a SET that timed out after landing held the name 15 min."""
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    with pytest.raises(RedisUnavailableError):
        await claim_client_message(
            SetThenFail(fake_redis),  # type: ignore[arg-type]
            user_id=user_id,
            chat_id=chat_id,
            client_message_id=name,
        )
    await drain_background_tasks()
    assert await fake_redis.exists(claim_key(user_id, chat_id, name)) == 0


@pytest.mark.asyncio
async def test_claim_client_message_cancelled_mid_reply_frees_the_name(fake_redis) -> None:
    """An SSE client that disconnects while the SET's reply is on its way."""
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    claiming = asyncio.create_task(
        claim_client_message(
            SlowReply(fake_redis, 0.2),  # type: ignore[arg-type]
            user_id=user_id,
            chat_id=chat_id,
            client_message_id=name,
        )
    )
    await asyncio.sleep(0.05)
    assert await fake_redis.exists(claim_key(user_id, chat_id, name)) == 1
    claiming.cancel()
    with pytest.raises(asyncio.CancelledError):
        await claiming
    await drain_background_tasks()
    assert await fake_redis.exists(claim_key(user_id, chat_id, name)) == 0


@pytest.mark.asyncio
async def test_claim_settle_never_raises() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(side_effect=ConnectionError("redis down"))
    await ClientMessageClaim(redis, "key", "token").settle(TurnOutcome())
    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_settle_after_waits_for_the_turn(fake_redis) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    claim = await claim_client_message(
        fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
    )
    assert claim is not None
    outcome = TurnOutcome()
    release = asyncio.Event()

    async def turn() -> None:
        await release.wait()
        outcome.mark_user_message_saved()

    running = asyncio.create_task(turn())
    claim.settle_after(running, outcome)
    await asyncio.sleep(0.05)
    assert await fake_redis.ttl(claim_key(user_id, chat_id, name)) <= CLAIM_RUNNING_TTL_SECONDS
    release.set()
    await drain_background_tasks()
    assert await fake_redis.ttl(claim_key(user_id, chat_id, name)) > CLAIM_RUNNING_TTL_SECONDS


# ── over the socket ────────────────────────────────────────────────────────────


_turns: list[str] = []


async def _counted_turn(*_args: Any, outcome: TurnOutcome, content: str, **_kwargs: Any):
    _turns.append(content)
    if content == "over quota":
        raise QuotaExceededError("Daily limit reached.")
    if content == "slow":
        await asyncio.sleep(0.3)
    outcome.mark_user_message_saved()
    yield "answer"


@pytest.fixture(autouse=True)
def _no_turns_yet():
    _turns.clear()


def _socket_client(user_id: UUID, redis: Any) -> tuple[TestClient, ExitStack]:
    from app.core.deps import get_settings_dep

    settings = Settings(jwt_secret=_SECRET, dev_auth_enabled=True)
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: settings
    stack = ExitStack()
    stack.enter_context(patch("app.modules.chat.ws_api.get_settings", return_value=settings))
    stack.enter_context(patch("app.modules.chat.ws_api.get_redis_client", return_value=redis))
    stack.enter_context(
        patch("app.modules.chat.ws_api.allow_request_unless_down", AsyncMock(return_value=True))
    )
    stack.enter_context(
        patch("app.core.chat_rate_limit.allow_chat_message", AsyncMock(return_value=True))
    )
    stack.enter_context(signed_in(user_id))
    stack.enter_context(ws_streams(_counted_turn))
    return TestClient(app), stack


def _auth(socket: Any, user_id: UUID) -> None:
    settings = Settings(jwt_secret=_SECRET, dev_auth_enabled=True)
    socket.send_json({"token": create_access_token(user_id, settings)})


_TURN = ["start", "token", "stream_end", "done"]


def test_ws_answers_ping_between_turns() -> None:
    user_id, chat_id = uuid4(), uuid4()
    client, stack = _socket_client(user_id, fakeredis.aioredis.FakeRedis(decode_responses=True))
    with stack, client.websocket_connect(f"/ws/chats/{chat_id}") as socket:
        _auth(socket, user_id)
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}
        socket.send_json({"type": "message", "content": "hi"})
        assert [socket.receive_json()["type"] for _ in range(4)] == _TURN


def test_ws_answers_ping_while_a_turn_runs() -> None:
    """The phone probes a turn's socket after a network switch; the turn's own
    frame loop answers, between the reply's frames."""
    user_id, chat_id = uuid4(), uuid4()
    client, stack = _socket_client(user_id, fakeredis.aioredis.FakeRedis(decode_responses=True))
    with stack, client.websocket_connect(f"/ws/chats/{chat_id}") as socket:
        _auth(socket, user_id)
        socket.send_json({"type": "message", "content": "slow"})
        assert socket.receive_json()["type"] == "start"
        socket.send_json({"type": "ping"})
        frames = [socket.receive_json()["type"] for _ in range(4)]
    assert frames == ["pong", *_TURN[1:]]


def test_ws_resent_message_is_followed_not_run_twice() -> None:
    """Regression: the phone resends a message whose socket went quiet before
    ``start``; the first send had arrived and its turn already answered."""
    user_id, chat_id, name = uuid4(), uuid4(), str(uuid4())
    client, stack = _socket_client(user_id, fakeredis.aioredis.FakeRedis(decode_responses=True))
    frame = {"type": "message", "content": "hi", "client_message_id": name}
    with stack:
        with client.websocket_connect(f"/ws/chats/{chat_id}") as first:
            _auth(first, user_id)
            first.send_json(frame)
            assert [first.receive_json()["type"] for _ in range(4)] == _TURN
        with client.websocket_connect(f"/ws/chats/{chat_id}") as resend:
            _auth(resend, user_id)
            resend.send_json(frame)
            assert resend.receive_json() == {"type": "duplicate"}
            # The socket stays usable: the next message is a new turn.
            resend.send_json({"type": "message", "content": "next", "client_message_id": None})
            assert [resend.receive_json()["type"] for _ in range(4)] == _TURN
    assert _turns == ["hi", "next"]


def test_ws_refused_message_frees_its_name_for_the_resend() -> None:
    user_id, chat_id, name = uuid4(), uuid4(), str(uuid4())
    client, stack = _socket_client(user_id, fakeredis.aioredis.FakeRedis(decode_responses=True))
    frame = {"type": "message", "content": "over quota", "client_message_id": name}
    with stack, client.websocket_connect(f"/ws/chats/{chat_id}") as socket:
        _auth(socket, user_id)
        for _ in range(2):
            socket.send_json(frame)
            assert socket.receive_json()["type"] == "start"
            error = socket.receive_json()
            assert error["type"] == "error"
            assert error["user_message_saved"] is False
    assert _turns == ["over quota", "over quota"]


def test_ws_named_message_is_refused_when_its_claim_cannot_be_made() -> None:
    user_id, chat_id = uuid4(), uuid4()
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
    client, stack = _socket_client(user_id, redis)
    with stack, client.websocket_connect(f"/ws/chats/{chat_id}") as socket:
        _auth(socket, user_id)
        socket.send_json({"type": "message", "content": "hi", "client_message_id": str(uuid4())})
        error = socket.receive_json()
    assert error["type"] == "error"
    assert error["code"] == "unavailable"
    assert error["user_message_saved"] is False
    assert _turns == []


class _GoneSocket:
    """A socket the phone closed while the server was still before ``start``."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        raise WebSocketDisconnect(code=1006)

    async def receive_json(self) -> dict[str, Any]:
        raise WebSocketDisconnect(code=1006)


def _saving_turn(runs: list[str], *, delay: float = 0.0):
    def factory(outcome: TurnOutcome) -> AsyncIterator[str]:
        async def turn() -> AsyncIterator[str]:
            runs.append("turn")
            await asyncio.sleep(delay)
            outcome.mark_user_message_saved()
            yield "answer"

        return turn()

    return factory


@pytest.mark.asyncio
async def test_ws_named_turn_runs_when_start_cannot_reach_its_client(fake_redis) -> None:
    """Regression: the turn returned and freed its claim after an SSE resend of the
    same message had been told ``duplicate``: no turn ran at all."""
    from app.modules.chat.stream_api import _stream_tokens_sse
    from app.modules.chat.ws_turn import run_chat_stream

    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    runs: list[str] = []

    def claim() -> Any:
        return claim_client_message(
            fake_redis, user_id=user_id, chat_id=chat_id, client_message_id=name
        )

    ws_claim = await claim()
    assert ws_claim is not None
    ws_turn = asyncio.create_task(
        run_chat_stream(
            _GoneSocket(),  # type: ignore[arg-type]
            cancel_event=asyncio.Event(),
            stream_factory=_saving_turn(runs, delay=0.1),
            claim=ws_claim,
        )
    )
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)
    resend = [
        chunk
        async for chunk in _stream_tokens_sse(
            chat_id=chat_id,
            stream_factory=_saving_turn(runs),
            request=request,
            claim_message=claim,
        )
    ]
    await ws_turn
    await drain_background_tasks()
    assert resend == ['data: {"type":"duplicate"}\n\n']
    assert runs == ["turn"]
    assert await fake_redis.ttl(claim_key(user_id, chat_id, name)) > CLAIM_RUNNING_TTL_SECONDS


@pytest.mark.asyncio
async def test_ws_unnamed_turn_still_does_not_run_without_its_client() -> None:
    from app.modules.chat.ws_turn import run_chat_stream

    runs: list[str] = []
    await run_chat_stream(
        _GoneSocket(),  # type: ignore[arg-type]
        cancel_event=asyncio.Event(),
        stream_factory=_saving_turn(runs),
    )
    assert runs == []
