"""An open chat socket has a frame budget, and frames have a size cap.

Only ``message`` / ``regenerate`` frames were rate limited. Pings, cancels,
unknown types and invalid JSON were unlimited on an authenticated socket,
and each invalid frame made the server parse it and send an error back.
uvicorn's default WebSocket frame cap is 16 MiB.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.access_tokens import create_access_token
from app.core.config import Settings
from app.main import create_app
from app.modules.chat import ws_limits
from app.tests.modules.chat.chat_test_support import signed_in

_LIMIT = 10
_SECRET = "super-secret-key-that-is-at-least-32-chars!!"


@pytest.fixture(autouse=True)
def _no_redis_limits():
    with (
        patch("app.modules.chat.ws_api.allow_request_unless_down", AsyncMock(return_value=True)),
        patch("app.core.chat_rate_limit.allow_chat_message", AsyncMock(return_value=True)),
    ):
        yield


@pytest.mark.parametrize("frames, closed", [(_LIMIT, False), (_LIMIT + 5, True)])
def test_ws_closes_a_socket_that_floods_frames(frames: int, closed: bool) -> None:
    from app.core.deps import get_settings_dep

    settings = Settings(jwt_secret=_SECRET, dev_auth_enabled=True)
    user_id = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: settings
    with (
        patch.object(ws_limits, "WS_FRAME_LIMIT", _LIMIT),
        signed_in(user_id),
    ):
        client = TestClient(app)
        with client.websocket_connect(f"/ws/chats/{uuid4()}") as ws:
            ws.send_json({"token": create_access_token(user_id, settings)})
            for _ in range(frames):
                ws.send_json(["not", "an", "object"])
            for _ in range(_LIMIT):
                assert ws.receive_json()["message"] == "Invalid message"
            if not closed:
                return
            refusal = ws.receive_json()
            assert refusal["type"] == "error"
            assert refusal["code"] == "rate_limited"
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008


_REPO = Path(__file__).resolve().parents[6]


@pytest.mark.parametrize(
    "path, pattern",
    [
        (_REPO / "fly.toml", r"app = \"sh -c 'exec /opt/venv/bin/uvicorn [^\"]*\""),
        (_REPO / "apps" / "api" / "Dockerfile", r"CMD \[.*uvicorn.*\]"),
    ],
)
def test_uvicorn_ws_frame_cap_is_set(path: Path, pattern: str) -> None:
    command = re.search(pattern, path.read_text())
    assert command is not None
    size = re.search(r"--ws-max-size (\d+)", command.group(0))
    assert size is not None
    assert int(size.group(1)) <= 1_048_576
