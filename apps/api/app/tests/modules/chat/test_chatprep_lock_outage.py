"""The per-chat prepare lock with Redis down is the turn's ``unavailable`` answer.

``acquire_chatprep_lock`` let the client's raw Redis error escape, and both transports
mapped that unknown exception to "Something went wrong. Try again.": the phone took an
outage for a failed reply instead of checking its connection, as it does after
``unavailable``. A lock another turn really holds is still ``busy``. The real lock code
runs on a fake Redis here: only its ``SET NX`` on the chat's key fails.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.exceptions import ChatBusyError, RedisUnavailableError
from app.main import create_app
from app.modules.chat import turn_resources
from app.tests.api_support import api_user
from app.tests.modules.chat.chat_test_support import signed_in, turn_deps

_UNAVAILABLE = {
    "type": "error",
    "code": "unavailable",
    "message": "Service temporarily unavailable. Please retry shortly.",
    "user_message_saved": False,
}
_BUSY = {
    "type": "error",
    "code": "busy",
    "message": "Still generating — wait or cancel first.",
    "user_message_saved": False,
}


def _redis(chat_id: UUID, lock: str) -> Any:
    """A fake Redis whose prepare lock for ``chat_id`` is ``down``, ``held`` or ``free``."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    real_set = redis.set
    lock_key = f"chatprep:{chat_id}"

    async def set_(key: str, *args: Any, **kwargs: Any) -> Any:
        if key == lock_key and lock == "down":
            raise RedisConnectionError("Error 111 connecting to redis")
        if key == lock_key and lock == "held":
            return None  # Another turn's SET NX won.
        return await real_set(key, *args, **kwargs)

    redis.set = set_  # type: ignore[method-assign,assignment]
    return redis


@pytest.mark.asyncio
@pytest.mark.parametrize("lock, raised", [("down", RedisUnavailableError), ("held", ChatBusyError)])
async def test_acquire_chatprep_lock_down_is_unavailable_held_is_busy(
    lock: str, raised: type[Exception]
) -> None:
    chat_id = uuid4()
    with pytest.raises(raised):
        await turn_resources.acquire_chatprep_lock(turn_deps(), _redis(chat_id, lock), chat_id)


@contextmanager
def _patched(redis: Any) -> Iterator[None]:
    with ExitStack() as stack:
        for target in ("app.modules.chat.stream_api", "app.modules.chat.ws_api"):
            stack.enter_context(patch(f"{target}.get_redis_client", return_value=redis))
        # Every limit in front of the turn lets it by: only the prepare lock is reached.
        stack.enter_context(
            patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch("app.core.rate_limit.allow_request", AsyncMock(return_value=True))
        )
        yield


def _sse_events(lock: str) -> list[dict[str, Any]]:
    chat_id = uuid4()
    user = api_user(ai_data_consent_at=datetime(2026, 1, 1, tzinfo=UTC))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    with _patched(_redis(chat_id, lock)):
        response = TestClient(app).post(
            f"/chats/{chat_id}/messages/stream",
            headers={"Authorization": "Bearer tok"},
            json={"content": "hi"},
        )
    assert response.status_code == 200
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _socket_frames(lock: str) -> list[dict[str, Any]]:
    chat_id = uuid4()
    with (
        _patched(_redis(chat_id, lock)),
        signed_in(uuid4()),
        TestClient(create_app()).websocket_connect(f"/ws/chats/{chat_id}") as socket,
    ):
        socket.send_json({"token": "tok"})
        socket.send_json({"type": "message", "content": "hi"})
        frames = [socket.receive_json()]
        while frames[-1].get("type") not in {"error", "done"}:
            frames.append(socket.receive_json())
    return frames


@pytest.mark.parametrize("lock, error", [("down", _UNAVAILABLE), ("held", _BUSY)])
def test_sse_turn_prepare_lock_down_is_unavailable_held_is_busy(
    lock: str, error: dict[str, Any]
) -> None:
    events = _sse_events(lock)
    assert events[-1] == error
    assert [e["type"] for e in events[:-1]] == ["start"]


@pytest.mark.parametrize("lock, error", [("down", _UNAVAILABLE), ("held", _BUSY)])
def test_socket_turn_prepare_lock_down_is_unavailable_held_is_busy(
    lock: str, error: dict[str, Any]
) -> None:
    frames = _socket_frames(lock)
    assert frames[-1] == error
    assert all(frame["type"] != "token" for frame in frames)
