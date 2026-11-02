"""The chat socket's three limits: Redis down is ``unavailable`` + 1013, over the limit is not.

Each limit failed closed by reading an outage as a hit: the handshake was refused (1008),
a connect or a message was told "Too many requests". The phone took the outage for its
own doing. The counter is what fails here (``core.rate_limit.allow_request``), so the
real limit code runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.tests.modules.chat.chat_test_support import signed_in, ws_streams

_UNAVAILABLE = {
    "type": "error",
    "code": "unavailable",
    "message": "Service temporarily unavailable. Please retry shortly.",
}
# Each limit's Redis key (ws_api, core/chat_rate_limit).
_KEYS = {
    "handshake": "rate:ws:handshake:",
    "connect": "rate:ws:connect:",
    "message": "rate:chat:msg:",
}


def _counter(name: str, *, down: bool) -> Any:
    """``allow_request`` with limit ``name``'s Redis down, or ``name`` used up; others pass."""

    async def allow(_redis: Any, key: str, **_window: int) -> bool:
        if not key.startswith(_KEYS[name]):
            return True
        if down:
            raise RedisConnectionError("Error 111 connecting to redis")
        return False

    return allow


@contextmanager
def _chat_socket(limit: str, *, down: bool) -> Iterator[TestClient]:
    """A signed-in client whose limit ``limit`` is down or used up. No limit lets a turn by."""
    stream = MagicMock()
    with (
        patch("app.core.rate_limit.allow_request", side_effect=_counter(limit, down=down)),
        patch(
            "app.modules.chat.ws_api.get_redis_client",
            return_value=fakeredis.aioredis.FakeRedis(decode_responses=True),
        ),
        signed_in(uuid4()),
        ws_streams(stream),
    ):
        yield TestClient(create_app())
    stream.assert_not_called()


def _connect(limit: str, *, down: bool, frame: dict[str, Any] | None) -> list[Any]:
    """Open a socket, sign in, send ``frame``; what came back, the close code last."""
    received: list[Any] = []
    with _chat_socket(limit, down=down) as client:
        try:
            with client.websocket_connect(f"/ws/chats/{uuid4()}") as socket:
                socket.send_json({"token": "tok"})
                if frame is not None:
                    socket.send_json(frame)
                while True:
                    received.append(socket.receive_json())
        except WebSocketDisconnect as closed:
            received.append(closed.code)
    return received


_MESSAGE = {"type": "message", "content": "hi"}


@pytest.mark.parametrize(
    "limit, frame",
    [("handshake", None), ("connect", None), ("message", _MESSAGE)],
)
def test_ws_limit_with_redis_down_says_unavailable_and_closes_1013(
    limit: str, frame: dict[str, Any] | None
) -> None:
    received = _connect(limit, down=True, frame=frame)
    # A message frame was not taken: the phone offers it again once Redis is back.
    unsaved = {"user_message_saved": False} if limit == "message" else {}
    assert received == [{**_UNAVAILABLE, **unsaved}, 1013]


def test_ws_handshake_over_its_limit_is_refused_1008() -> None:
    assert _connect("handshake", down=False, frame=None) == [1008]


def test_ws_connect_over_its_limit_says_too_many_requests() -> None:
    received = _connect("connect", down=False, frame=None)
    assert received[0] == {
        "type": "error",
        "code": "rate_limited",
        "message": "Too many requests. Try again shortly.",
    }
    assert received[1] != 1013


def test_ws_message_over_its_limit_says_too_many_requests_and_stays_open() -> None:
    with (
        _chat_socket("message", down=False) as client,
        client.websocket_connect(f"/ws/chats/{uuid4()}") as socket,
    ):
        socket.send_json({"token": "tok"})
        socket.send_json(_MESSAGE)
        refused = socket.receive_json()
        socket.send_json({"type": "ping"})
        pong = socket.receive_json()
    # Coded, as the SSE route's 429 is: a Regenerate over the limit showed the English.
    assert refused == {
        "type": "error",
        "code": "rate_limited",
        "message": "Too many requests. Try again shortly.",
        "user_message_saved": False,
    }
    assert pong == {"type": "pong"}
