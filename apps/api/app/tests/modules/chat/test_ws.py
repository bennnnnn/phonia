"""WebSocket endpoint tests."""

import asyncio
import json
import threading
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.access_tokens import create_access_token
from app.core.config import Settings
from app.exceptions import AttachmentValidationError, ChatNotFoundError, QuotaExceededError
from app.main import create_app
from app.modules.chat import ws_api
from app.modules.chat.stream_events import REPLY_SAVE_FAILED_MESSAGE
from app.modules.chat.turn_outcome import TurnOutcome
from app.services.quota.messages import QUOTA_EXCEEDED_MESSAGE_FREE
from app.tests.modules.chat.chat_test_support import access_for, signed_in, ws_streams


@pytest.fixture(autouse=True)
def _ws_rate_limit():
    with (
        patch("app.modules.chat.ws_api.allow_request_unless_down", AsyncMock(return_value=True)),
        patch("app.core.chat_rate_limit.allow_chat_message", AsyncMock(return_value=True)),
    ):
        yield


def _settings():
    return Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        dev_auth_enabled=True,
    )


def _token(uid=None):
    uid = uid or uuid4()
    return str(uid), create_access_token(uid, _settings())


def _fake_user(uid=None):
    user = MagicMock()
    user.id = uid or uuid4()
    user.default_model = "free-chat"
    user.memory_enabled = True
    return user


def _app(user):
    from app.core.deps import get_settings_dep

    app = create_app()
    app.dependency_overrides[get_settings_dep] = _settings
    return app


async def _empty_stream(*args, **kwargs):
    return
    yield  # make it an async generator


# ── auth failure ───────────────────────────────────────────────────────────────


def test_ws_missing_token_closes():
    app = _app(None)
    client = TestClient(app)
    with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
        ws.send_json({})
        msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "Missing token" in msg["message"]


@pytest.mark.asyncio
async def test_ws_disconnect_before_auth_is_a_normal_close():
    from starlette.websockets import WebSocketDisconnect

    from app.modules.chat.ws_api import chat_websocket

    socket = AsyncMock()
    socket.receive_json.side_effect = WebSocketDisconnect(code=1000)
    with (
        patch("app.modules.chat.ws_api._ws_handshake_rate_limit", AsyncMock(return_value=True)),
        patch("app.modules.chat.ws_api.get_redis_client", return_value=AsyncMock()),
    ):
        await chat_websocket(socket, uuid4())
    socket.send_json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, socket_closed, ends_quietly",
    [
        # The stream loop already received the client's disconnect.
        (
            RuntimeError('Cannot call "receive" once a disconnect message has been received.'),
            False,
            True,
        ),
        # A send to the dropped client already marked the socket closed.
        (
            RuntimeError('WebSocket is not connected. Need to call "accept" first.'),
            True,
            True,
        ),
        (RuntimeError("something else broke"), False, False),
    ],
)
async def test_ws_receive_after_client_dropped_mid_stream(error, socket_closed, ends_quietly):
    """A client that vanishes mid-reply (no close frame) used to end in an
    unhandled RuntimeError: every abrupt disconnect logged an ASGI traceback."""
    from starlette.websockets import WebSocketState

    from app.modules.chat.ws_api import chat_websocket

    socket = AsyncMock()
    socket.application_state = (
        WebSocketState.DISCONNECTED if socket_closed else WebSocketState.CONNECTED
    )
    socket.receive_json.side_effect = [{"token": "t"}, error]
    with (
        patch("app.modules.chat.ws_api._ws_handshake_rate_limit", AsyncMock(return_value=True)),
        patch("app.modules.chat.ws_api._ws_connect_rate_limit", AsyncMock(return_value=True)),
        patch("app.modules.chat.ws_api.get_redis_client", return_value=AsyncMock()),
        signed_in(uuid4()),
    ):
        if ends_quietly:
            await chat_websocket(socket, uuid4())
        else:
            with pytest.raises(RuntimeError, match="something else broke"):
                await chat_websocket(socket, uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_frame", [json.JSONDecodeError("bad JSON", "{", 1), KeyError("text")]
)
async def test_ws_invalid_frame_during_stream_keeps_producer_owned(invalid_frame):
    from app.modules.chat.ws_turn import stream_over_ws

    first_token = asyncio.Event()
    resume = asyncio.Event()
    frames = []

    async def stream_tokens():
        yield "first"
        first_token.set()
        await resume.wait()
        yield " second"

    class Socket:
        reads = 0

        async def send_json(self, frame):
            frames.append(frame)

        async def receive_json(self):
            self.reads += 1
            if self.reads == 1:
                await first_token.wait()
                raise invalid_frame
            resume.set()
            await asyncio.Event().wait()

    try:
        await asyncio.wait_for(
            stream_over_ws(Socket(), stream_tokens(), asyncio.Event(), TurnOutcome()), timeout=1
        )
    finally:
        resume.set()
        await asyncio.sleep(0)
    assert [frame["content"] for frame in frames if frame["type"] == "token"] == [
        "first",
        " second",
    ]
    assert sum(frame["type"] == "done" for frame in frames) == 1
    assert any(frame.get("message") == "Invalid JSON" for frame in frames)


@pytest.mark.asyncio
async def test_ws_handshake_rate_limit_uses_forwarded_ip_when_trusted():
    """The handshake limiter must key on the edge-seen IP (fly-client-ip/XFF)
    when behind a trusted proxy, not the proxy's own address — otherwise
    every connect shares one proxy bucket."""
    from app.modules.chat.ws_api import _ws_handshake_rate_limit

    websocket = MagicMock()
    websocket.client.host = "10.0.0.1"
    websocket.headers = {"fly-client-ip": "198.51.100.7"}
    settings = Settings(trust_x_forwarded_for=True)

    captured: dict = {}

    async def fake_allow(_redis, key, *, limit, window_seconds):
        captured["key"] = key
        return True

    with (
        patch("app.modules.chat.ws_api.get_settings", return_value=settings),
        patch("app.modules.chat.ws_api.allow_request_unless_down", side_effect=fake_allow),
    ):
        await _ws_handshake_rate_limit(AsyncMock(), websocket)

    assert "198.51.100.7" in captured["key"]


def test_ws_invalid_token_closes():
    app = _app(None)
    client = TestClient(app)
    with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
        ws.send_json({"token": "not-a-valid-jwt"})
        msg = ws.receive_json()
    assert msg["type"] == "error"


def test_ws_auth_timeout_closes():
    """Sockets that never send an auth frame must not hang forever."""
    from app.core.deps import get_settings_dep

    app = _app(None)
    app.dependency_overrides[get_settings_dep] = lambda: _settings().model_copy(
        update={"ws_auth_timeout_seconds": 0.05}
    )
    client = TestClient(app)

    with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "timeout" in msg["message"].lower()


def test_ws_non_dict_frame_does_not_crash():
    """JSON arrays/non-objects must error cleanly, not AttributeError the loop."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    app = _app(user)

    with signed_in(user.id):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json(["not", "an", "object"])
            err = ws.receive_json()
            assert err["type"] == "error"
            assert "Invalid" in err["message"]
            # Socket stays open for a valid follow-up.
            ws.send_json({"type": "cancel"})


def test_ws_null_content_does_not_crash():
    """content: null used to AttributeError on .strip() before validation."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    app = _app(user)

    with signed_in(user.id):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": None})
            err = ws.receive_json()
            assert err["type"] == "error"
            assert "Invalid" in err["message"]


# ── normal message flow ────────────────────────────────────────────────────────


def test_ws_sends_message_and_receives_tokens():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_stream(*args, **kwargs):
        yield "Hello"
        yield " world"

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            start = ws.receive_json()
            assert start["type"] == "start"
            token1 = ws.receive_json()
            assert token1["type"] == "token"
            assert token1["content"] == "Hello"
            token2 = ws.receive_json()
            assert token2["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            done = ws.receive_json()
            assert done["type"] == "done"


def test_ws_done_includes_resolved_model():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_stream(*args, outcome=None, **kwargs):
        if outcome is not None:
            outcome.message_id = str(uuid4())
            outcome.resolved_model = "smart-chat"
        yield "Hello"

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            stream_end = ws.receive_json()
            assert stream_end["type"] == "stream_end"
            assert stream_end["resolved_model"] == "smart-chat"
            done = ws.receive_json()
            assert done["type"] == "done"
            assert done["resolved_model"] == "smart-chat"


def test_ws_passes_client_timezone_to_stream():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_stream(*args, **kwargs):
        assert kwargs.get("client_timezone") == "America/Los_Angeles"
        yield "ok"

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok, "client_timezone": "America/Los_Angeles"})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            assert ws.receive_json()["type"] == "done"


@pytest.mark.parametrize(
    ("frame_zone", "expected"),
    [("Europe/London", "Europe/London"), (None, "America/New_York")],
)
def test_ws_turn_reads_the_zone_its_frame_names(frame_zone, expected):
    """A phone whose zone changes while its socket stays open (a flight, Settings)
    names the new one on each turn; a frame without one (an older phone) keeps the
    zone the socket authenticated with."""
    _, tok = _token()
    user = _fake_user()
    seen: list[str | None] = []

    async def fake_stream(*args, **kwargs):
        seen.append(kwargs.get("client_timezone"))
        yield "ok"

    frame = {"type": "message", "content": "what time is it?"}
    if frame_zone is not None:
        frame["client_timezone"] = frame_zone
    with signed_in(user.id), ws_streams(fake_stream):
        client = TestClient(_app(user))
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            ws.send_json({"token": tok, "client_timezone": "America/New_York"})
            ws.send_json(frame)
            events = [ws.receive_json()["type"] for _ in range(4)]
    assert events == ["start", "token", "stream_end", "done"]
    assert seen == [expected]


def test_ws_empty_message_sends_error_frame():
    """An empty text-only message must produce a visible error frame at the
    WS layer immediately, not be silently ignored or dropped mid-stream —
    the client needs to know the turn was rejected so it can reset its UI."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    app = _app(user)

    with (
        signed_in(user.id),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "   "})
            frame = ws.receive_json()
            assert frame["type"] == "error"
            assert "empty" in frame["message"].lower()


# ── regenerate ─────────────────────────────────────────────────────────────────


def test_ws_regenerate():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_regen(*args, **kwargs):
        yield "Regen"

    app = _app(user)

    with (
        signed_in(user.id),
        patch("app.modules.chat.ws_api.stream_entry.stream_regenerate_response", fake_regen),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "regenerate"})
            start = ws.receive_json()
            assert start["type"] == "start"
            token = ws.receive_json()
            assert token["content"] == "Regen"
            assert ws.receive_json()["type"] == "stream_end"
            done = ws.receive_json()
            assert done["type"] == "done"


def test_ws_regenerate_passes_client_geo():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_regen(*args, **kwargs):
        assert kwargs.get("client_location") == "San Francisco, CA"
        assert kwargs.get("client_latitude") == 37.77
        assert kwargs.get("client_longitude") == -122.42
        # The frame's zone, not the one the socket authenticated with.
        assert kwargs.get("client_timezone") == "America/Los_Angeles"
        yield "nearby"

    app = _app(user)

    with (
        signed_in(user.id),
        patch("app.modules.chat.ws_api.stream_entry.stream_regenerate_response", fake_regen),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok, "client_timezone": "America/New_York"})
            ws.send_json(
                {
                    "type": "regenerate",
                    "client_timezone": "America/Los_Angeles",
                    "client_location": "San Francisco, CA",
                    "client_latitude": 37.77,
                    "client_longitude": -122.42,
                }
            )
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            assert ws.receive_json()["type"] == "done"


# ── cancel ─────────────────────────────────────────────────────────────────────


def test_ws_cancel_sets_flag():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_stream(*args, should_cancel=None, **kwargs):
        for word in ["A", "B", "C"]:
            if should_cancel and should_cancel():
                return
            yield word

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "cancel"})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            while True:
                msg = ws.receive_json()
                if msg["type"] == "done":
                    break


def test_ws_mid_stream_cancel():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def slow_stream(*args, should_cancel=None, **kwargs):
        for word in ["one", "two", "three", "four"]:
            if should_cancel and should_cancel():
                return
            yield word
            await asyncio.sleep(0.05)

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(slow_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            first = ws.receive_json()
            assert first["type"] == "token"
            ws.send_json({"type": "cancel"})
            assert ws.receive_json()["type"] == "stream_end"
            done = ws.receive_json()
            assert done["type"] == "done"


def test_ws_cancel_carries_how_much_the_phone_drew():
    """S7.11: the cancel frame's shown_chars reaches the turn, so the stopped reply
    saves only the text the phone kept on screen."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    outcomes: list[TurnOutcome] = []

    async def slow_stream(*args, should_cancel=None, outcome=None, **kwargs):
        outcomes.append(outcome)
        for word in ["one ", "two ", "three ", "four "]:
            if should_cancel and should_cancel():
                return
            yield word
            await asyncio.sleep(0.05)

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(slow_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            ws.send_json({"type": "cancel", "shown_chars": 4})
            assert ws.receive_json()["type"] == "stream_end"
            assert ws.receive_json()["type"] == "done"

    assert [outcome.client_shown_chars for outcome in outcomes] == [4]


def test_ws_mid_stream_non_dict_frame_is_ignored():
    """A JSON array mid-stream must not error or interrupt the producer."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def slow_stream(*args, should_cancel=None, **kwargs):
        for word in ["one", "two", "three"]:
            if should_cancel and should_cancel():
                return
            yield word
            await asyncio.sleep(0.05)

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(slow_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            ws.send_json([])  # non-dict — ignored, stream continues
            types = []
            while True:
                msg = ws.receive_json()
                types.append(msg["type"])
                assert msg["type"] != "error"
                if msg["type"] == "done":
                    break
            assert "token" in types
            assert "stream_end" in types


@pytest.mark.asyncio
async def test_stream_over_ws_disconnect_still_finalizes():
    """Closing the socket mid-token must still persist the assistant.
    stream_end send fails after disconnect, so `finally` awaits finalize."""
    from starlette.websockets import WebSocketDisconnect

    from app.modules.chat.ws_turn import stream_over_ws

    finalized = asyncio.Event()

    async def slow_finalize() -> None:
        await asyncio.sleep(0.02)
        finalized.set()

    outcome = TurnOutcome(finalize_db_task=asyncio.create_task(slow_finalize()))

    async def short_stream():
        yield "Hi"
        yield "there"

    class FakeWs:
        async def send_json(self, payload: dict) -> None:
            if payload.get("type") in ("stream_end", "done"):
                raise WebSocketDisconnect()

        async def receive_json(self) -> dict:
            await asyncio.sleep(0.01)
            raise WebSocketDisconnect()

    await asyncio.wait_for(
        stream_over_ws(FakeWs(), short_stream(), asyncio.Event(), outcome),
        timeout=2,
    )
    assert finalized.is_set()


@pytest.mark.asyncio
async def test_stream_over_ws_disconnect_does_not_cancel_generation():
    """New chat closes the socket; the model must still run to completion."""
    from starlette.websockets import WebSocketDisconnect

    from app.modules.chat.ws_turn import stream_over_ws

    produced: list[str] = []
    finalized = asyncio.Event()

    async def mark_finalize() -> None:
        finalized.set()

    outcome = TurnOutcome(finalize_db_task=asyncio.create_task(mark_finalize()))

    async def stream():
        for part in ("one", "two", "three"):
            produced.append(part)
            yield part
            await asyncio.sleep(0.01)

    class FakeWs:
        def __init__(self) -> None:
            self._sends = 0

        async def send_json(self, payload: dict) -> None:
            self._sends += 1
            if payload.get("type") == "token" and self._sends >= 2:
                raise WebSocketDisconnect()
            if payload.get("type") in ("stream_end", "done"):
                raise WebSocketDisconnect()

        async def receive_json(self) -> dict:
            await asyncio.sleep(10)
            return {"type": "ping"}

    await asyncio.wait_for(
        stream_over_ws(FakeWs(), stream(), asyncio.Event(), outcome),
        timeout=2,
    )
    assert produced == ["one", "two", "three"]
    assert finalized.is_set()


# ── validation / service errors ────────────────────────────────────────────────


def test_ws_invalid_message_payload():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    app = _app(user)

    with (
        signed_in(user.id),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi", "model": "not-a-model"})
            err = ws.receive_json()
            assert err["type"] == "error"


@pytest.mark.parametrize(
    "error,code",
    [
        (QuotaExceededError(QUOTA_EXCEEDED_MESSAGE_FREE), "quota_exceeded"),
        (AttachmentValidationError("Attach the file again."), "attachment_rejected"),
    ],
)
def test_ws_rejected_send_error_frame(error, code):
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def quota_fail(*args, **kwargs):
        raise error
        yield  # pragma: no cover

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(quota_fail),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["code"] == code
            assert err["message"] == error.message


# ── user not found ─────────────────────────────────────────────────────────────


def test_ws_user_not_found_sends_error():
    _, tok = _token()
    chat_id = uuid4()
    app = _app(None)

    def missing_user_stream(*_args, **_kwargs):
        async def _gen():
            raise ChatNotFoundError("User not found.")
            yield ""  # pragma: no cover

        return _gen()

    with (
        signed_in(uuid4()),
        ws_streams(missing_user_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hello"})
            start = ws.receive_json()
            assert start["type"] == "start"
            err = ws.receive_json()
            assert err["type"] == "error"
            assert "User not found" in err["message"]


def test_ws_message_rate_limit_blocks_second_chargeable_message():
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    app = _app(user)
    msg_calls = {"count": 0}

    async def allow_chat_side_effect(_redis, user_id):
        msg_calls["count"] += 1
        return msg_calls["count"] <= 1

    async def fake_stream(*args, **kwargs):
        yield "ok"

    with (
        patch(
            "app.core.chat_rate_limit.allow_chat_message",
            side_effect=allow_chat_side_effect,
        ),
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "first"})
            assert ws.receive_json()["type"] == "start"
            while True:
                msg = ws.receive_json()
                if msg["type"] == "done":
                    break
            ws.send_json({"type": "message", "content": "second"})
            err = ws.receive_json()
            assert err["type"] == "error"
            assert "Too many requests" in err["message"]
            assert msg_calls["count"] == 2


# ── done is not blocked by background finalization ─────────────────────────────


def test_ws_done_waits_for_finalize_commit():
    """`done` must not be sent until the DB finalize commits, so the
    message_id it carries always references a persisted row (no ghost `done`
    with a pre-assigned id that might never land). The token stream still
    flushes immediately (stream_end is not held); only the final `done`
    waits on the commit. Before this, a failed finalize left the client
    holding a message_id for a row that was never inserted."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    message_id = str(uuid4())
    release_finalize = asyncio.Event()
    captured: dict = {}

    async def fake_stream(*args, outcome=None, **kwargs):
        captured["loop"] = asyncio.get_running_loop()
        yield "Hello"
        if outcome is not None:
            outcome.resolved_model = "free-chat"

            async def slow_finalize():
                # Blocks until the test releases it. The row's id is known only once
                # the commit lands, so a `done` sent before this cannot carry it.
                await asyncio.wait_for(release_finalize.wait(), timeout=8)
                outcome.message_id = message_id

            outcome.finalize_db_task = asyncio.create_task(slow_finalize())

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            # `done` is held while the finalize commit is in flight — the
            # client stays in the streaming state until the commit lands.
            captured["loop"].call_soon_threadsafe(release_finalize.set)
            done = ws.receive_json()
            assert done["type"] == "done"
            # The id the commit set: `done` waited for it, no ghost `done`.
            assert done["message_id"] == message_id


def test_ws_done_sends_error_when_finalize_fails():
    """If the DB finalize FAILS, the client must get an error instead of a
    ghost `done` carrying a message_id for a row that never persisted."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    message_id = str(uuid4())

    async def fake_stream(*args, outcome=None, **kwargs):
        yield "Hello"
        if outcome is not None:
            outcome.message_id = message_id
            outcome.resolved_model = "free-chat"

            async def failing_finalize():
                raise RuntimeError("Neon is down")

            outcome.finalize_db_task = asyncio.create_task(failing_finalize())

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert REPLY_SAVE_FAILED_MESSAGE in msg["message"]


def test_ws_done_sends_persisting_when_finalize_times_out():
    """H2: on finalize TIMEOUT, send `done` without message_id + persisting: true
    so the client keeps the local bubble and refetches instead of trusting a
    row that may never persist if the shielded task later fails."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    message_id = str(uuid4())
    gate = asyncio.Event()

    async def fake_stream(*args, outcome=None, **kwargs):
        yield "Hello"
        if outcome is not None:
            outcome.message_id = message_id
            outcome.resolved_model = "free-chat"

            async def slow_finalize():
                await gate.wait()

            outcome.finalize_db_task = asyncio.create_task(slow_finalize())

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
        patch("app.modules.chat.stream_events.DONE_COMMIT_WAIT_SECONDS", 0.05),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            msg = ws.receive_json()
            assert msg["type"] == "done"
            assert "message_id" not in msg
            assert msg.get("persisting") is True
            gate.set()


def test_ws_status_event_carries_detail():
    """Status events forward the optional activity detail (e.g. the web-search
    query) so the client can render a specific label."""
    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()

    async def fake_stream(*args, on_status=None, **kwargs):
        if on_status is not None:
            await on_status("searching", "weather in berlin")
            await on_status("composing")
        yield "ok"

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            searching = ws.receive_json()
            assert searching == {
                "type": "status",
                "phase": "searching",
                "detail": "weather in berlin",
            }
            composing = ws.receive_json()
            assert composing == {"type": "status", "phase": "composing"}
            assert ws.receive_json()["type"] == "token"
            assert ws.receive_json()["type"] == "stream_end"
            assert ws.receive_json()["type"] == "done"


def test_ws_rechecks_token_on_chargeable_message():
    """After purge/revoke, the next chargeable frame must close the socket."""
    from app.exceptions import AuthenticationError

    _, tok = _token()
    user = _fake_user()
    chat_id = uuid4()
    app = _app(user)
    verify = AsyncMock(side_effect=[access_for(user.id), AuthenticationError("Token revoked")])

    with patch("app.modules.chat.ws_api.access_tokens.check_access", verify):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{chat_id}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "still here?"})
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["message"] == "Unauthorized"
            assert verify.await_count == 2


# ── the next turn, sent once the reply's text is out ───────────────────────────


def _saving_turns(release: dict, contents: list[str]):
    """Each turn streams one token; the first one's save waits until the test releases it."""

    async def fake_stream(*args, content="", outcome=None, **kwargs):
        contents.append(content)
        if outcome is not None:
            # A real turn saves the user's row before it waits on the model.
            outcome.mark_user_message_saved()
        if len(contents) > 1:
            # Long enough for a Stop already sent to reach this turn first.
            await asyncio.sleep(0.2)
        yield f"reply to {content}"
        if outcome is None:
            return
        outcome.message_id = f"id-{content}"
        if len(contents) == 1:
            release["loop"] = asyncio.get_running_loop()
            release["event"] = asyncio.Event()
            outcome.finalize_db_task = asyncio.create_task(release["event"].wait())

    return fake_stream


def _release_first_save(release: dict) -> None:
    import time

    # Let the server read what was just sent while the first save still runs.
    time.sleep(0.2)
    release["loop"].call_soon_threadsafe(release["event"].set)


def test_ws_message_after_stream_end_runs_once_the_last_turn_is_done():
    """A send at stream_end waits for the previous commit instead of a busy refusal."""
    _, tok = _token()
    user = _fake_user()
    release: dict = {}
    contents: list[str] = []
    fake_stream = _saving_turns(release, contents)
    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "first"})
            assert [ws.receive_json()["type"] for _ in range(3)] == [
                "start",
                "token",
                "stream_end",
            ]
            ws.send_json({"type": "message", "content": "second"})
            _release_first_save(release)
            # One at a time: a busy refusal fails here instead of waiting forever.
            assert ws.receive_json() == {"type": "done", "message_id": "id-first"}
            assert ws.receive_json() == {"type": "start"}
            assert ws.receive_json() == {"type": "token", "content": "reply to second"}
            assert ws.receive_json()["type"] == "stream_end"
            assert ws.receive_json() == {"type": "done", "message_id": "id-second"}

    assert contents == ["first", "second"]


def test_ws_message_before_stream_end_is_still_busy():
    _, tok = _token()
    user = _fake_user()
    gate: dict = {}
    contents: list[str] = []

    async def fake_stream(*args, content="", **kwargs):
        contents.append(content)
        gate["loop"] = asyncio.get_running_loop()
        gate["event"] = asyncio.Event()
        yield "one"
        await gate["event"].wait()
        yield " two"

    app = _app(user)

    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "first"})
            assert ws.receive_json()["type"] == "start"
            assert ws.receive_json()["type"] == "token"
            ws.send_json({"type": "message", "content": "second"})
            busy = ws.receive_json()
            gate["loop"].call_soon_threadsafe(gate["event"].set)
            rest = [ws.receive_json()["type"] for _ in range(3)]

    assert busy["code"] == "busy"
    assert busy["user_message_saved"] is False
    assert rest == ["token", "stream_end", "done"]
    assert contents == ["first"]


def test_ws_stop_after_a_waiting_message_stops_that_message_not_the_save(monkeypatch):
    """The waiting turn's own Stop stays unread until that turn runs."""
    _, tok = _token()
    user = _fake_user()
    release: dict = {}
    contents: list[str] = []
    fake_stream = _saving_turns(release, contents)
    app = _app(user)
    # The socket's second idle read (the first took "first"; "second" was held) is the
    # one after the stopped turn: the next frame is sent once it is waiting, so the test
    # never races the turn's end (CI hung once, 2026-11-01; test_ws_pending_read).
    reads: list[int] = []
    reading_again = threading.Event()
    real_receive_frame = ws_api.receive_frame

    async def receive_frame(websocket, idle_seconds, pending=None):
        reads.append(1)
        if len(reads) == 2:
            reading_again.set()
        return await real_receive_frame(websocket, idle_seconds, pending)

    monkeypatch.setattr(ws_api, "receive_frame", receive_frame)
    with (
        signed_in(user.id),
        ws_streams(fake_stream),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            ws.send_json({"token": tok})
            ws.send_json({"type": "message", "content": "first"})
            assert [ws.receive_json()["type"] for _ in range(3)] == [
                "start",
                "token",
                "stream_end",
            ]
            ws.send_json({"type": "message", "content": "second"})
            ws.send_json({"type": "cancel"})
            _release_first_save(release)
            assert ws.receive_json() == {"type": "done", "message_id": "id-first"}
            assert ws.receive_json() == {"type": "start"}
            # The stopped turn sends nothing more (no token, stream_end or done
            # comes before this answer), and the socket still serves frames.
            assert reading_again.wait(5)
            ws.send_json({"type": "message", "content": ""})
            assert ws.receive_json()["message"] == "Message cannot be empty."

    assert contents == ["first", "second"]
