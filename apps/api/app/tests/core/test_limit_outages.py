"""Every route's own limit: Redis down answers 503 unavailable, over the limit its 429.

Each limit failed closed by reading an outage as a hit (``allow_request_fail_closed``
returned False), so a Redis outage answered "too many scans", "too many recordings",
"too many memory edits", "an export is already running": the phone took it for the
user's doing and never checked its connection, which it does after a 503. The counter
is what fails here (``core.rate_limit.allow_request``), so each route's real limit runs.
The socket's limits are ``modules/chat/test_ws_limit_outages.py``.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.deps import get_current_user, get_redis, get_settings_dep
from app.main import create_app
from app.tests.api_support import api_user

_AUTH = {"Authorization": "Bearer tok"}
_UNAVAILABLE = {
    "detail": {
        "code": "unavailable",
        "message": "Service temporarily unavailable. Please retry shortly.",
    }
}
_CHAT_ID = uuid4()
_CALL_ID = "issued-session"
_LIVE_TALK = Settings(speech_live_talk_enabled=True, speech_realtime_voice_enabled=True)
_PHOTO = {"image_base64": base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()}


@dataclass(frozen=True)
class _Limit:
    """One route's limit: how to reach it, and the 429 it answers when used up."""

    send: Callable[[TestClient], Any]
    # The 429's code. The chat stream's and the link preview's named none: their English
    # read on the phone as "Couldn't reach the server" after a Regenerate.
    over: str
    plan: str = "free"
    settings: Settings = field(default_factory=Settings)
    # Where the route reads its Redis client: given a fake (the limit's own counter fails).
    redis_at: tuple[str, ...] = ()


LIMITS: dict[str, _Limit] = {
    "chat stream (SSE)": _Limit(
        send=lambda c: c.post(
            f"/chats/{_CHAT_ID}/messages/stream", headers=_AUTH, json={"content": "hi"}
        ),
        over="rate_limited",
    ),
    "dictation": _Limit(
        send=lambda c: c.post(
            "/speech/transcribe",
            headers=_AUTH,
            json={"audio_base64": base64.b64encode(b"audio").decode(), "filename": "a.m4a"},
        ),
        over="speech_rate_limited",
        plan="pro",
        redis_at=("app.modules.speech.api.get_redis_client",),
    ),
    "live talk saves": _Limit(
        send=lambda c: c.post(
            "/speech/live/persist",
            headers=_AUTH,
            json={"chat_id": str(_CHAT_ID), "call_id": _CALL_ID, "user_text": "hi"},
        ),
        over="rate_limited",
        plan="pro",
        settings=_LIVE_TALK,
        redis_at=("app.modules.speech.realtime.get_redis_client",),
    ),
    "live talk lookups": _Limit(
        send=lambda c: c.post(
            "/speech/live/tool",
            headers=_AUTH,
            json={
                "chat_id": str(_CHAT_ID),
                "call_id": _CALL_ID,
                "turn_id": "utterance-1",
                "name": "web_search",
                "query": "latest score",
            },
        ),
        over="rate_limited",
        plan="pro",
        settings=_LIVE_TALK,
        redis_at=("app.modules.speech.realtime.get_redis_client",),
    ),
    "memory edits": _Limit(
        send=lambda c: c.post(
            "/memories/instruct", headers=_AUTH, json={"instruction": "Be brief"}
        ),
        over="rate_limited",
        redis_at=("app.modules.memory.api.get_redis_client",),
    ),
    "link preview": _Limit(
        send=lambda c: c.get(
            "/link-preview", headers=_AUTH, params={"url": "https://example.com/a"}
        ),
        over="rate_limited",
        redis_at=("app.modules.link_preview.api.get_redis_client",),
    ),
    "photo scans": _Limit(
        send=lambda c: c.post("/math/scan/read", headers=_AUTH, json=_PHOTO),
        over="scan_rate_limited",
        redis_at=("app.services.scan_read.get_redis_client",),
    ),
    "data export": _Limit(
        send=lambda c: c.get("/auth/me/export", headers=_AUTH),
        over="export_busy",
    ),
}


@contextmanager
def _client(limit: _Limit, allow_request: AsyncMock) -> Iterator[TestClient]:
    user = api_user(plan=limit.plan, ai_data_consent_at=datetime(2026, 1, 1, tzinfo=UTC))
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: limit.settings
    app.dependency_overrides[get_redis] = lambda: redis
    with ExitStack() as stack:
        # The live talk session the phone named is this chat's (live_talk.issue_realtime_session).
        stack.enter_context(
            patch.object(redis, "get", AsyncMock(side_effect=_session_reads(user.id, redis.get)))
        )
        for target in limit.redis_at:
            stack.enter_context(patch(target, return_value=redis))
        # The request limiter in front of every route lets it by: only the route's own counter fails.
        stack.enter_context(
            patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True))
        )
        stack.enter_context(patch("app.core.rate_limit.allow_request", allow_request))
        yield TestClient(app)


def _session_reads(user_id: Any, read: Callable[[str], Any]) -> Callable[[str], Any]:
    session_key = f"live_talk_rt:{user_id}:{_CALL_ID}"

    async def get(key: str) -> Any:
        return str(_CHAT_ID) if key == session_key else await read(key)

    return get


@pytest.mark.parametrize("name", LIMITS)
def test_a_limit_with_redis_down_answers_503_unavailable(name: str) -> None:
    down = AsyncMock(side_effect=RedisConnectionError("Error 111 connecting to redis"))
    with _client(LIMITS[name], down) as client:
        response = LIMITS[name].send(client)
    assert down.await_count == 1, "the route's own limit was not reached"
    assert response.status_code == 503
    assert response.json() == _UNAVAILABLE
    assert response.headers["retry-after"] == "5"


@pytest.mark.parametrize("name", LIMITS)
def test_a_limit_used_up_still_answers_429(name: str) -> None:
    used_up = AsyncMock(return_value=False)
    with _client(LIMITS[name], used_up) as client:
        response = LIMITS[name].send(client)
    assert used_up.await_count == 1, "the route's own limit was not reached"
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == LIMITS[name].over
    assert detail["message"]


def test_every_route_limit_is_listed() -> None:
    """A new route limit gets a row here: grep the callers of the one limit function."""
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[2]
    callers = sorted(
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "tests" not in path.parts
        and "allow_request_unless_down(" in path.read_text()
        and path.name != "rate_limit.py"
    )
    assert callers == [
        "core/chat_rate_limit.py",  # the chat stream (SSE) here, the socket's message limit there
        "modules/account/api.py",  # data export
        "modules/account/refresh_limit.py",  # test_refresh_limit.py
        "modules/account/signin_limit.py",  # test_signin_limit.py
        "modules/chat/ws_api.py",  # test_ws_limit_outages.py
        "modules/link_preview/api.py",
        "modules/memory/api.py",
        "modules/speech/gates.py",  # dictation, speech, live talk's session
        "modules/speech/realtime.py",  # live talk saves and lookups
        "services/scan_read.py",  # photo scans, every subject
    ]
