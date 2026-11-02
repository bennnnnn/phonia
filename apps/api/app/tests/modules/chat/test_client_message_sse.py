"""One turn per client message over SSE (the claim itself: ``test_client_message.py``).

Production runs uvicorn at ASGI spec 2.3, where Starlette's ``StreamingResponse``
cancels the response body when the client disconnects, and anyio cancels it
again at every await. The claim must still be settled then: before, it stayed
held for its 15-minute running TTL, so on a flaky network the phone's Retry was
told ``duplicate``, followed a turn that never saved, and came back to Retry.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from starlette.responses import StreamingResponse
from starlette.types import Message

from app.core.background_tasks import drain_background_tasks
from app.core.config import Settings
from app.exceptions import QuotaExceededError
from app.modules.chat.client_message import (
    CLAIM_RUNNING_TTL_SECONDS,
    claim_client_message,
    claim_key,
)
from app.modules.chat.stream_api import _stream_tokens_sse
from app.modules.chat.turn_outcome import TurnOutcome
from app.tests.fakes import make_user
from app.tests.modules.chat.test_client_message import SlowReply


class SlowSend:
    """Redis whose commands wait a round trip before they land, as on a network:
    a cancellation can stop one before Redis sees it."""

    def __init__(self, inner: Any, delay: float) -> None:
        self._inner, self._delay = inner, delay

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)
        if not callable(target):
            return target

        async def call(*args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(self._delay)
            return await target(*args, **kwargs)

        return call


def _request() -> Any:
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)
    return request


async def _events(body: AsyncIterator[str]) -> list[dict[str, Any]]:
    return [json.loads(chunk.removeprefix("data: ")) async for chunk in body]


def _claim(redis: Any, user_id: UUID, chat_id: UUID, name: UUID) -> Any:
    return lambda: claim_client_message(
        redis, user_id=user_id, chat_id=chat_id, client_message_id=name
    )


def _turn(
    runs: list[str],
    *,
    save: str = "first",
    hold: float = 0.0,
    refuse: bool = False,
):
    """A turn that saves its message ``first``, ``never``, or ``late``: while it
    unwinds after the client left, as the real one's user-row save can."""

    def factory(outcome: TurnOutcome, *_args: Any) -> AsyncIterator[str]:
        async def turn() -> AsyncIterator[str]:
            runs.append("turn")
            if refuse:
                raise QuotaExceededError("Daily limit reached.")
            if save == "first":
                outcome.mark_user_message_saved()
            try:
                await asyncio.sleep(hold)
                yield "answer"
            finally:
                if save == "late":
                    await asyncio.sleep(0.05)
                    outcome.mark_user_message_saved()

        return turn()

    return factory


@pytest.mark.asyncio
async def test_sse_resend_of_a_taken_message_is_followed_not_run_twice(fake_redis) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    runs: list[str] = []
    claim = _claim(fake_redis, user_id, chat_id, name)

    first = await _events(
        _stream_tokens_sse(
            chat_id=chat_id, stream_factory=_turn(runs), request=_request(), claim_message=claim
        )
    )
    resend = await _events(
        _stream_tokens_sse(
            chat_id=chat_id, stream_factory=_turn(runs), request=_request(), claim_message=claim
        )
    )
    await drain_background_tasks()
    assert [event["type"] for event in first] == ["start", "token", "stream_end", "done"]
    assert resend == [{"type": "duplicate"}]
    assert runs == ["turn"]
    assert await fake_redis.ttl(claim_key(user_id, chat_id, name)) > CLAIM_RUNNING_TTL_SECONDS


@pytest.mark.asyncio
async def test_sse_refused_message_frees_its_name(fake_redis) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    events = await _events(
        _stream_tokens_sse(
            chat_id=chat_id,
            stream_factory=_turn([], refuse=True),
            request=_request(),
            claim_message=_claim(fake_redis, user_id, chat_id, name),
        )
    )
    await drain_background_tasks()
    assert [event["type"] for event in events] == ["start", "error"]
    assert await fake_redis.exists(claim_key(user_id, chat_id, name)) == 0


@pytest.mark.asyncio
async def test_sse_named_message_is_refused_when_its_claim_cannot_be_made() -> None:
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
    runs: list[str] = []
    events = await _events(
        _stream_tokens_sse(
            chat_id=uuid4(),
            stream_factory=_turn(runs),
            request=_request(),
            claim_message=_claim(redis, uuid4(), uuid4(), uuid4()),
        )
    )
    await drain_background_tasks()
    assert [event["type"] for event in events] == ["error"]
    assert events[0]["code"] == "unavailable"
    assert events[0]["user_message_saved"] is False
    assert runs == []


@pytest.mark.asyncio
async def test_sse_client_gone_at_start_frees_the_claim(fake_redis) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    factory = MagicMock()
    body = cast(
        AsyncGenerator[str, None],
        _stream_tokens_sse(
            chat_id=chat_id,
            stream_factory=factory,
            request=_request(),
            claim_message=_claim(fake_redis, user_id, chat_id, name),
        ),
    )
    assert json.loads((await anext(body)).removeprefix("data: ")) == {"type": "start"}
    await body.aclose()
    await drain_background_tasks()
    factory.assert_not_called()
    assert await fake_redis.exists(claim_key(user_id, chat_id, name)) == 0


async def _serve_then_disconnect(body: AsyncIterator[str], *, after: str) -> None:
    """Run ``body`` through Starlette at uvicorn's ASGI spec; disconnect once ``after`` is sent.

    ``after`` is ``"start"`` (the event went out) or ``"headers"``.
    """
    response = StreamingResponse(body, media_type="text/event-stream")
    sent_it = asyncio.Event()
    disconnect = asyncio.Event()
    first = True

    async def receive() -> Message:
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if after == "headers" and message["type"] == "http.response.start":
            sent_it.set()
        if after == "start" and b'"start"' in message.get("body", b""):
            sent_it.set()

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}}
    serving = asyncio.create_task(response(scope, receive, send))
    await asyncio.wait_for(sent_it.wait(), 2)
    await asyncio.sleep(0.05)
    disconnect.set()
    await asyncio.wait_for(serving, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize("save", ["never", "first", "late"])
async def test_sse_disconnect_mid_turn_still_settles_the_claim(fake_redis, save: str) -> None:
    """Regression: the response's cleanup was cancelled at every await, so the
    claim stayed held 15 min whether or not the message had saved. A settle
    must also wait for the turn: freeing a name whose message saves while the
    turn unwinds would let a resend run a second turn."""
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    redis = SlowSend(fake_redis, 0.002)
    body = _stream_tokens_sse(
        chat_id=chat_id,
        stream_factory=_turn([], save=save, hold=5),
        request=_request(),
        claim_message=_claim(redis, user_id, chat_id, name),
    )
    await _serve_then_disconnect(body, after="start")
    await drain_background_tasks()
    ttl = await fake_redis.ttl(claim_key(user_id, chat_id, name))
    if save == "never":
        assert ttl == -2
    else:
        assert ttl > CLAIM_RUNNING_TTL_SECONDS


@pytest.mark.asyncio
async def test_sse_disconnect_while_claiming_frees_the_name(fake_redis) -> None:
    user_id, chat_id, name = uuid4(), uuid4(), uuid4()
    runs: list[str] = []
    body = _stream_tokens_sse(
        chat_id=chat_id,
        stream_factory=_turn(runs),
        request=_request(),
        claim_message=_claim(SlowReply(fake_redis, 0.3), user_id, chat_id, name),
    )
    await _serve_then_disconnect(body, after="headers")
    await drain_background_tasks()
    assert runs == []
    assert await fake_redis.exists(claim_key(user_id, chat_id, name)) == 0


@pytest.mark.asyncio
async def test_stream_message_sse_claims_the_message_by_its_name(fake_redis) -> None:
    from app.models.schemas import ChatMessageRequest
    from app.modules.chat.stream_api import stream_message_sse

    user = make_user()
    user.id = uuid4()
    chat_id, name = uuid4(), uuid4()
    runs: list[str] = []

    async def turn(*_args: Any, outcome: TurnOutcome, **_kwargs: Any) -> AsyncIterator[str]:
        runs.append("turn")
        outcome.mark_user_message_saved()
        yield "answer"

    async def send() -> list[dict[str, Any]]:
        response = await stream_message_sse(
            chat_id=chat_id,
            body=ChatMessageRequest(content="hi", client_message_id=name),
            request=_request(),
            user=user,
            settings=Settings(),
            redis=fake_redis,
        )
        return await _events(response.body_iterator)  # type: ignore[arg-type]

    with patch("app.modules.chat.stream_api.stream_entry.stream_chat_response", turn):
        first = await send()
        resend = await send()
    await drain_background_tasks()
    assert first[0]["type"] == "start" and first[-1]["type"] == "done"
    assert resend == [{"type": "duplicate"}]
    assert runs == ["turn"]
