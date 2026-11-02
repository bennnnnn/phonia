"""Every request the global spend cap gates: Redis down answers 503 unavailable, the cap its own.

``global_spend_exceeded`` read a Redis error as the cap reached (fail closed), so an outage
after sign-in answered as the day's spend cap: pictures and voice "temporarily unavailable,
try again later", scans "paused", memory edits "paused", and live talk "this month's minutes
used". The phone took each for the cap and never checked its connection, which it does after
a 503. Nothing spends either way. The spend read is what fails here (``spend_musd:<day>``), so
each route's own gate runs. Chat turns: ``modules/chat/test_turn_quota_reserve.py``.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.deps import get_current_user, get_redis, get_settings_dep
from app.core.spend_counter import spend_key
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
_CAP_USD = 1.0
_LIVE_TALK = Settings(
    speech_live_talk_enabled=True,
    speech_realtime_voice_enabled=True,
    openai_api_key="sk-test",
    daily_global_spend_usd=_CAP_USD,
)
_PHOTO = {"image_base64": base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()}

Spend = Literal["down", "capped"]


@dataclass(frozen=True)
class _Gate:
    """One route the spend cap gates: how to reach it, and what it answers at the cap."""

    send: Callable[[TestClient], Any]
    capped: tuple[int, str]
    plan: str = "free"
    settings: Settings = field(default_factory=lambda: Settings(daily_global_spend_usd=_CAP_USD))
    # Where the route reads its Redis client: given the fake whose spend read fails.
    redis_at: tuple[str, ...] = ()
    # The route's own reads before its spend gate (a chat, a live talk's history).
    stubs: tuple[tuple[str, Any], ...] = ()


GATES: dict[str, _Gate] = {
    "photo scans": _Gate(
        send=lambda c: c.post("/math/scan/read", headers=_AUTH, json=_PHOTO),
        capped=(429, "scan_spend_cap"),
        redis_at=("app.services.scan_read.get_redis_client",),
    ),
    "memory edits": _Gate(
        send=lambda c: c.post(
            "/memories/instruct", headers=_AUTH, json={"instruction": "Be brief"}
        ),
        capped=(503, "memory_spend_cap"),
        redis_at=("app.modules.memory.api.get_redis_client",),
    ),
    "dictation": _Gate(
        send=lambda c: c.post(
            "/speech/transcribe",
            headers=_AUTH,
            json={"audio_base64": base64.b64encode(b"audio").decode(), "filename": "a.m4a"},
        ),
        capped=(429, "voice_spend_cap"),
        plan="pro",
        redis_at=("app.modules.speech.api.get_redis_client",),
    ),
    "read aloud": _Gate(
        send=lambda c: c.post("/speech/tts", headers=_AUTH, json={"text": "Hello there"}),
        capped=(429, "voice_spend_cap"),
        plan="pro",
        redis_at=("app.modules.speech.api.get_redis_client",),
    ),
    "live talk session": _Gate(
        send=lambda c: c.post("/speech/live/session", headers=_AUTH, json={}),
        capped=(429, "voice_spend_cap"),
        plan="pro",
        settings=_LIVE_TALK,
        redis_at=("app.modules.speech.realtime.get_redis_client",),
        stubs=(
            (
                "app.modules.speech.realtime.live_talk_service.load_live_talk_session_context",
                AsyncMock(return_value=MagicMock()),
            ),
        ),
    ),
    "live talk saves": _Gate(
        send=lambda c: c.post(
            "/speech/live/persist",
            headers=_AUTH,
            json={"chat_id": str(_CHAT_ID), "call_id": _CALL_ID, "user_text": "hi"},
        ),
        capped=(429, "voice_spend_cap"),
        plan="pro",
        settings=_LIVE_TALK,
        redis_at=("app.modules.speech.realtime.get_redis_client",),
    ),
    "image generation": _Gate(
        send=lambda c: c.post(
            "/images/generate",
            headers=_AUTH,
            json={"chat_id": str(_CHAT_ID), "prompt": "a cat"},
        ),
        capped=(429, "spend_cap"),
        plan="pro",
        redis_at=("app.modules.images.generation.get_redis_client",),
        stubs=(
            (
                "app.modules.images.generation.history.get_chat",
                AsyncMock(return_value=MagicMock()),
            ),
        ),
    ),
}


def _reads(spend: Spend, user_id: Any, read: Callable[[str], Any]) -> Callable[[str], Any]:
    """Redis reads: the day's spend fails or is over the cap; a live talk's session is open."""
    session_key = f"live_talk_rt:{user_id}:{_CALL_ID}"

    async def get(key: str) -> Any:
        if key == spend_key():
            if spend == "down":
                raise RedisConnectionError("Error 111 connecting to redis")
            return str(10**12)
        return str(_CHAT_ID) if key == session_key else await read(key)

    return get


@contextmanager
def _client(gate: _Gate, spend: Spend) -> Iterator[tuple[TestClient, AsyncMock]]:
    user = api_user(plan=gate.plan, ai_data_consent_at=datetime(2026, 1, 1, tzinfo=UTC))
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: gate.settings
    app.dependency_overrides[get_redis] = lambda: redis
    reads = AsyncMock(side_effect=_reads(spend, user.id, redis.get))
    with ExitStack() as stack:
        stack.enter_context(patch.object(redis, "get", reads))
        for target in gate.redis_at:
            stack.enter_context(patch(target, return_value=redis))
        for target, stub in gate.stubs:
            stack.enter_context(patch(target, stub))
        # Every limit lets it by: only the spend read fails (test_limit_outages.py for those).
        stack.enter_context(
            patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch("app.core.rate_limit.allow_request", AsyncMock(return_value=True))
        )
        yield TestClient(app), reads


def _spend_reads(reads: AsyncMock) -> int:
    return sum(call.args[0] == spend_key() for call in reads.await_args_list)


@pytest.mark.parametrize("name", GATES)
def test_the_spend_cap_with_redis_down_answers_503_unavailable(name: str) -> None:
    with _client(GATES[name], "down") as (client, reads):
        response = GATES[name].send(client)
    assert _spend_reads(reads) == 1, "the route's spend gate was not reached"
    assert response.status_code == 503
    assert response.json() == _UNAVAILABLE
    assert response.headers["retry-after"] == "5"


@pytest.mark.parametrize("name", GATES)
def test_the_spend_cap_reached_still_answers_its_own_refusal(name: str) -> None:
    with _client(GATES[name], "capped") as (client, reads):
        response = GATES[name].send(client)
    assert _spend_reads(reads) == 1, "the route's spend gate was not reached"
    assert (response.status_code, response.json()["detail"]["code"]) == GATES[name].capped


def test_every_spend_gate_is_listed() -> None:
    """A new caller of the spend read is placed here: a request answers an outage 503 (a row
    above, or the chat turn's test), work nobody waits on skips it (its own test says how)."""
    app_dir = Path(__file__).resolve().parents[2]
    callers = sorted(
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "tests" not in path.parts
        and "global_spend_exceeded(" in path.read_text()
        and path.parent.name != "quota"
        and path.name not in {"spend_counter.py", "turn_deps.py"}
    )
    assert callers == [
        # Skips on an outage as at the cap: background/test_job_spend_cap.py.
        "background/handlers.py",
        # Skips (never raises): the user's message is saved. test_index_jobs.py.
        "modules/attachments/jobs.py",
        # Skips: the turn's jobs. modules/chat/test_post_turn_spend.py.
        "modules/chat/post_turn.py",
        # No "saving is paused" note on an outage. modules/chat/test_prompt_memory.py.
        "modules/chat/prompt_memory.py",
        # Follow-up questions: none (take_related_prompts_event logs the failure).
        "modules/chat/related_prompts.py",
        # Skips the tool loop: the turn was admitted. modules/chat/test_post_turn_spend.py.
        "modules/chat/stream_paths.py",
        # Skips the model reader's shadow read: nothing waits on it. test_model_read_shadow.py.
        "modules/chat/turn_prep/model_read_shadow.py",
        # The chat turn: the socket's and SSE's unavailable frame. test_turn_quota_reserve.py.
        "modules/chat/turn_resources.py",
        # Image generation: "image generation" above, and the chat's picture turns.
        "modules/images/generation.py",
        # Photo lookup: the chat's photo turn, and a reply's photo (best-effort, none).
        "modules/images/search.py",
        "modules/memory/api.py",  # memory edits
        "modules/speech/gates.py",  # dictation, read aloud, live talk's session and saves
        # The resolver answers None on any failure: services/test_conversation_reference.py.
        "services/conversation_reference.py",
        "services/scan_read.py",  # photo scans, every subject
    ]
