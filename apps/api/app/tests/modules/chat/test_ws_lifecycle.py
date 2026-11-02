"""A chat socket's life: idle close, the per-user cap, error frames that say
whether the message saved, and a server shutdown that stops turns the way the
user's Stop does (WS and SSE)."""

from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import shutdown
from app.core.access_tokens import create_access_token
from app.core.config import Settings
from app.main import create_app
from app.modules.chat import finalize_registry, ws_limits
from app.modules.chat.stream_events import SERVER_RESTARTING_MESSAGE
from app.modules.chat.turn_outcome import TurnOutcome
from app.tests.modules.chat.chat_test_support import offline_deps, signed_in, ws_streams

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)

_SECRET = "super-secret-key-that-is-at-least-32-chars!!"


def _settings(**fields: Any) -> Settings:
    return Settings(jwt_secret=_SECRET, dev_auth_enabled=True, **fields)


@pytest.fixture(autouse=True)
def _no_redis_limits():
    with (
        patch("app.modules.chat.ws_api.allow_request_unless_down", AsyncMock(return_value=True)),
        patch("app.core.chat_rate_limit.allow_chat_message", AsyncMock(return_value=True)),
    ):
        yield


def _client(settings: Settings, user_id) -> tuple[TestClient, ExitStack]:
    from app.core.deps import get_settings_dep

    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: settings
    stack = ExitStack()
    stack.enter_context(patch("app.modules.chat.ws_api.get_settings", return_value=settings))
    stack.enter_context(signed_in(user_id))
    return TestClient(app), stack


def _auth(ws, user_id, settings: Settings) -> None:
    ws.send_json({"token": create_access_token(user_id, settings)})


@pytest.mark.parametrize("saved_first", [False, True])
def test_ws_error_frame_says_whether_the_user_message_saved(saved_first: bool) -> None:
    """The phone offers Retry (resend) only for an unsaved message, Regenerate
    only for a saved one; "generic" errors used to always mean Regenerate."""
    settings, user_id = _settings(), uuid4()

    async def failing_turn(*_args, outcome: TurnOutcome, **_kwargs):
        if saved_first:
            outcome.mark_user_message_saved()
        raise RuntimeError("redis down mid-turn")
        yield  # pragma: no cover

    client, stack = _client(settings, user_id)
    with stack, ws_streams(failing_turn):
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            _auth(ws, user_id, settings)
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "start"
            error = ws.receive_json()
    assert error["type"] == "error"
    assert error["user_message_saved"] is saved_first


def test_ws_rate_limited_message_is_unsaved() -> None:
    settings, user_id = _settings(), uuid4()
    client, stack = _client(settings, user_id)
    with (
        stack,
        patch("app.modules.chat.ws_api._ws_rate_limit", AsyncMock(return_value=False)),
    ):
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            _auth(ws, user_id, settings)
            ws.send_json({"type": "message", "content": "hi"})
            error = ws.receive_json()
    assert error["code"] == "rate_limited"
    assert error["message"] == "Too many requests. Try again shortly."
    assert error["user_message_saved"] is False


def test_ws_idle_socket_closes_with_the_reconnect_code() -> None:
    """Idle authenticated sockets used to stay open forever (no receive timeout)."""
    settings, user_id = _settings(ws_idle_timeout_seconds=0.05), uuid4()
    client, stack = _client(settings, user_id)
    with stack, client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
        _auth(ws, user_id, settings)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == ws_limits.WS_IDLE_CLOSE_CODE


def test_ws_idle_timer_does_not_cut_a_turn() -> None:
    settings, user_id = _settings(ws_idle_timeout_seconds=0.05), uuid4()

    async def slow_turn(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        yield "late but whole"

    client, stack = _client(settings, user_id)
    with stack, ws_streams(slow_turn):
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            _auth(ws, user_id, settings)
            ws.send_json({"type": "message", "content": "hi"})
            types = [ws.receive_json()["type"] for _ in range(4)]
    assert types == ["start", "token", "stream_end", "done"]


def test_ws_caps_sockets_per_user_and_frees_the_slot_on_close() -> None:
    settings, user_id = _settings(ws_max_sockets_per_user=1), uuid4()
    client, stack = _client(settings, user_id)
    with stack:
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as first:
            _auth(first, user_id, settings)
            first.send_json(["held"])  # answered from inside the socket loop
            assert first.receive_json()["message"] == "Invalid message"
            with client.websocket_connect(f"/ws/chats/{uuid4()}") as second:
                _auth(second, user_id, settings)
                with pytest.raises(WebSocketDisconnect) as refused:
                    second.receive_json()
            assert refused.value.code == ws_limits.WS_TOO_MANY_SOCKETS_CLOSE_CODE
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as third:
            _auth(third, user_id, settings)
            third.send_json(["admitted"])
            assert third.receive_json()["message"] == "Invalid message"
    assert user_id not in ws_limits._open_sockets


def test_user_socket_slot_counts_and_releases() -> None:
    user_id = uuid4()
    with ws_limits.user_socket_slot(user_id, 2) as one:
        with ws_limits.user_socket_slot(user_id, 2) as two:
            with ws_limits.user_socket_slot(user_id, 2) as three:
                assert (one, two, three) == (True, True, False)
                assert ws_limits._open_sockets[user_id] == 2
        assert ws_limits._open_sockets[user_id] == 1
    assert user_id not in ws_limits._open_sockets
    with ws_limits.user_socket_slot(user_id, 0) as uncapped:
        assert uncapped is True


def test_ws_refuses_a_new_turn_once_the_server_is_stopping(monkeypatch) -> None:
    monkeypatch.setattr(shutdown, "_stopping", True)
    settings, user_id = _settings(), uuid4()
    turn = MagicMock()
    client, stack = _client(settings, user_id)
    with stack, ws_streams(turn):
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            _auth(ws, user_id, settings)
            ws.send_json({"type": "message", "content": "hi"})
            error = ws.receive_json()
    # Coded: a Regenerate refused during a deploy showed the English.
    assert error == {
        "type": "error",
        "code": "server_restarting",
        "message": SERVER_RESTARTING_MESSAGE,
        "user_message_saved": False,
    }
    turn.assert_not_called()


def _slow_model(*tokens: str):
    async def fake_stream(**_kwargs: object):
        for token in tokens:
            yield token
            await asyncio.sleep(0.05)

    return fake_stream


def _real_turn(outcome: TurnOutcome, should_cancel):
    from app.modules.chat.stream_pipeline import stream_and_finalize
    from app.modules.chat.turn_prep import StreamContext

    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=0,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )
    return stream_and_finalize(
        offline_deps(),
        AsyncMock(),
        Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
        ctx,
        should_cancel=should_cancel,
        outcome=outcome,
    )


@pytest.fixture
def _turn_io(stream_offline_io):
    finalize = AsyncMock()
    with (
        patch("app.gateways.litellm_gateway.stream_chat_completion", _slow_model("a ", "b ", "c")),
        patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)),
        patch("app.services.model_health.record_samples", AsyncMock()),
    ):
        yield finalize


@pytest.mark.asyncio
async def test_shutdown_stops_a_ws_turn_through_its_stop_and_saves_it(_turn_io, monkeypatch):
    """Regression: a deploy left the turn draining the model until Fly's SIGKILL;
    the reply was never saved and the chat's lock and finalize marker stayed."""
    from app.modules.chat.ws_turn import stream_over_ws

    sent: list[dict] = []
    first_token = asyncio.Event()

    class FakeWs:
        async def send_json(self, payload: dict) -> None:
            sent.append(payload)
            if payload.get("type") == "token":
                first_token.set()

        async def receive_json(self) -> dict:
            await asyncio.sleep(10)
            return {"type": "ping"}

    cancel_event = asyncio.Event()
    outcome = TurnOutcome()
    serve = asyncio.create_task(
        stream_over_ws(
            FakeWs(), _real_turn(outcome, cancel_event.is_set), cancel_event, outcome, uuid4()
        )
    )
    await asyncio.wait_for(first_token.wait(), 5)
    monkeypatch.setattr(shutdown, "_stopping", True)
    assert finalize_registry.stop_inflight_streams() == 1
    await asyncio.wait_for(serve, 5)

    _turn_io.assert_awaited_once()
    assert _turn_io.await_args.kwargs["assistant_text"] == "a"
    assert outcome.completion == "interrupted"
    done = [frame for frame in sent if frame["type"] == "done"]
    assert done and done[0]["completion"] == "interrupted"
    assert finalize_registry.stop_inflight_streams() == 0


@pytest.mark.asyncio
async def test_shutdown_stops_an_sse_turn_and_still_tells_the_client(_turn_io, monkeypatch):
    from app.modules.chat import stream_api

    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)
    events: list[dict] = []
    body = stream_api._stream_tokens_sse(
        chat_id=uuid4(),
        stream_factory=lambda outcome, _status, _reasoning, should_cancel: _real_turn(
            outcome, should_cancel
        ),
        request=request,
    )
    async for chunk in body:
        event = json.loads(chunk.removeprefix("data: "))
        events.append(event)
        if event["type"] == "token":
            monkeypatch.setattr(shutdown, "_stopping", True)
            finalize_registry.stop_inflight_streams()

    types = [event["type"] for event in events]
    assert types[0] == "start"
    assert types[-2:] == ["stream_end", "done"]
    assert events[-1]["completion"] == "interrupted"
    _turn_io.assert_awaited_once()


@pytest.mark.asyncio
async def test_sse_refuses_a_new_turn_once_the_server_is_stopping(monkeypatch):
    from app.modules.chat import stream_api

    monkeypatch.setattr(shutdown, "_stopping", True)
    factory = MagicMock()
    chunks = [
        chunk
        async for chunk in stream_api._stream_tokens_sse(
            chat_id=uuid4(), stream_factory=factory, request=AsyncMock()
        )
    ]
    assert [json.loads(chunk.removeprefix("data: ")) for chunk in chunks] == [
        {
            "type": "error",
            "code": "server_restarting",
            "message": SERVER_RESTARTING_MESSAGE,
            "user_message_saved": False,
        }
    ]
    factory.assert_not_called()
