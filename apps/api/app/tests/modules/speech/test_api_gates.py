"""Every paid speech route runs the same gates in its own order: plan, spend, rate, day.

Pins each refusal's status, message and rate key on read-aloud, its stream,
transcription and the live talk mint, and that a refusal never reaches the
provider.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.gateways.openai_speech_gateway import RealtimeClientSecretResult
from app.main import create_app
from app.modules.speech.live_talk import LiveTalkSessionContext
from app.services import quota as quota_service
from app.tests.api_support import api_user

_AUTH = {"Authorization": "Bearer tok"}


# path -> (request kwargs, provider patched on speech_service, provider value,
#          plan feature setting, refusal message for the plan, rate key prefix,
#          rate-limit message, daily cap setting)
_ROUTES = {
    "/speech/tts": (
        {"json": {"text": "hello"}},
        "synthesize_speech",
        AsyncMock(return_value=(b"mp3", "audio/mpeg")),
        "daily_speech_tts_plus",
        quota_service.SPEECH_TTS_NOT_IN_PLAN_MESSAGE,
        "speech_tts_rl",
        quota_service.SPEECH_TTS_RATE_LIMIT_MESSAGE,
    ),
    "/speech/transcribe": (
        {"files": {"file": ("speech.m4a", b"fake-audio", "audio/m4a")}},
        "transcribe_audio",
        AsyncMock(return_value="hello"),
        "daily_speech_transcriptions_plus",
        quota_service.SPEECH_NOT_IN_PLAN_MESSAGE,
        "speech_rl",
        quota_service.SPEECH_RATE_LIMIT_MESSAGE,
    ),
}


def _client(user, **settings: object) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(**settings)  # type: ignore[arg-type]
    return TestClient(app)


@contextmanager
def _speech(path: str, *, spend_capped: bool = False) -> Iterator[tuple[object, object]]:
    _, provider_name, provider, *_ = _ROUTES[path]
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    spy = AsyncMock(wraps=provider) if isinstance(provider, AsyncMock) else provider
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(f"app.modules.speech.api.speech_service.{provider_name}", spy),
        patch(
            "app.services.quota.global_spend_exceeded",
            AsyncMock(return_value=spend_capped),
        ),
    ):
        yield fake_redis, spy


@pytest.mark.parametrize("path", list(_ROUTES))
def test_speech_route_refuses_a_plan_without_the_feature(path):
    request, _, _, plan_setting, message, *_ = _ROUTES[path]
    client = _client(api_user(plan="plus"), **{plan_setting: 0})
    with _speech(path) as (_fake_redis, _provider):
        response = client.post(path, headers=_AUTH, **request)
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "not_in_plan", "message": message}}


@pytest.mark.parametrize("path", list(_ROUTES))
def test_speech_route_refuses_while_the_spend_breaker_is_open(path):
    request, *_ = _ROUTES[path]
    client = _client(api_user(plan="plus"))
    with _speech(path, spend_capped=True) as (_fake_redis, _provider):
        response = client.post(path, headers=_AUTH, **request)
    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "voice_spend_cap",
        "message": quota_service.VOICE_SPEND_CAP_MESSAGE,
    }


@pytest.mark.parametrize("path", list(_ROUTES))
def test_speech_route_rate_limits_per_user_and_minute(path):
    import asyncio

    request, _, _, _, _, rate_prefix, rate_message = _ROUTES[path]
    user = api_user(plan="plus")
    client = _client(user, speech_rate_limit_per_minute=1)
    with _speech(path) as (fake_redis, _provider):
        first = client.post(path, headers=_AUTH, **request)
        second = client.post(path, headers=_AUTH, **request)
        rate_key = asyncio.run(fake_redis.get(f"{rate_prefix}:{user.id}"))
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == {"code": "speech_rate_limited", "message": rate_message}
    assert rate_key == "2"


@pytest.mark.parametrize("path", list(_ROUTES))
def test_speech_route_with_rate_limit_off_takes_no_rate_key(path):
    import asyncio

    request, _, _, _, _, rate_prefix, _ = _ROUTES[path]
    user = api_user(plan="plus")
    client = _client(user, speech_rate_limit_per_minute=0)
    with _speech(path) as (fake_redis, _provider):
        response = client.post(path, headers=_AUTH, **request)
        rate_key = asyncio.run(fake_redis.get(f"{rate_prefix}:{user.id}"))
    assert response.status_code == 200
    assert rate_key is None


@pytest.mark.parametrize(
    "path, cap_setting, counter",
    [
        ("/speech/tts", "daily_speech_tts_plus", "speech_tts"),
        ("/speech/transcribe", "daily_speech_transcriptions_plus", "speech_transcription"),
    ],
)
def test_speech_route_refuses_past_the_days_cap(path, cap_setting, counter):
    from app.services.quota import counters

    request, *_ = _ROUTES[path]
    user = api_user(plan="plus")
    client = _client(user, **{cap_setting: 1})
    with _speech(path) as (_fake_redis, _provider):
        first = client.post(path, headers=_AUTH, **request)
        second = client.post(path, headers=_AUTH, **request)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == {
        "code": "daily_limit",
        "message": counters.limit_message(counter, user),
        "feature": counter,
    }


def test_tts_provider_failure_is_502_and_gives_the_slot_back():
    import asyncio

    user = api_user(plan="plus")
    client = _client(user, daily_speech_tts_plus=1)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=None),
        ),
    ):
        failed = client.post("/speech/tts", headers=_AUTH, json={"text": "hello"})
        keys = asyncio.run(fake_redis.keys("tts:*"))
        values = [asyncio.run(fake_redis.get(key)) for key in keys]
    assert failed.status_code == 502
    assert failed.json() == {"detail": "Could not synthesize speech"}
    assert values == ["0"]


@contextmanager
def _mint(spend_capped: bool = False) -> Iterator[tuple[object, AsyncMock]]:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_session_context",
            AsyncMock(return_value=LiveTalkSessionContext(None, "", "")),
        ),
        patch(
            "app.modules.speech.realtime.openai_speech_gateway.create_realtime_client_secret",
            mint,
        ),
        patch(
            "app.services.quota.global_spend_exceeded",
            AsyncMock(return_value=spend_capped),
        ),
    ):
        yield fake_redis, mint


_MINT_SETTINGS: dict[str, object] = {
    "openai_api_key": "sk-test",
    "speech_live_talk_enabled": True,
    "speech_realtime_voice_enabled": True,
    "monthly_live_talk_minutes_pro": 60,
    "live_talk_max_session_seconds": 900,
    "live_talk_min_session_seconds": 60,
}


def test_live_talk_mint_rate_limits_per_user_and_minute():
    import asyncio

    user = api_user(plan="pro")
    client = _client(user, speech_rate_limit_per_minute=1, **_MINT_SETTINGS)
    with _mint() as (fake_redis, mint):
        first = client.post("/speech/live/session", headers=_AUTH, json={})
        second = client.post("/speech/live/session", headers=_AUTH, json={})
        rate_key = asyncio.run(fake_redis.get(f"speech_realtime_rl:{user.id}"))
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == {
        "code": "speech_rate_limited",
        "message": quota_service.LIVE_TALK_RATE_LIMIT_MESSAGE,
    }
    assert rate_key == "2"
    assert mint.await_count == 1


def test_live_talk_mint_refuses_while_the_spend_breaker_is_open():
    client = _client(api_user(plan="pro"), speech_rate_limit_per_minute=0, **_MINT_SETTINGS)
    with _mint(spend_capped=True) as (_fake_redis, mint):
        response = client.post("/speech/live/session", headers=_AUTH, json={})
    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "voice_spend_cap",
        "message": quota_service.VOICE_SPEND_CAP_MESSAGE,
    }
    mint.assert_not_awaited()
