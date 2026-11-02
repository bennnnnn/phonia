"""/speech over HTTP: transcribe, speak, live talk."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.tests.api_support import api_user, app_with_user

# ── speech ─────────────────────────────────────────────────────────────────────


def test_speech_transcribe_ok():
    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="hello world"),
        ),
    ):
        r = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
    assert r.status_code == 200
    assert r.json()["text"] == "hello world"


def test_speech_transcribe_global_spend_cap():
    import fakeredis.aioredis

    from app.services.quota import VOICE_SPEND_CAP_MESSAGE

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.quota_service.global_spend_exceeded",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="hello"),
        ) as transcribe,
    ):
        r = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
    assert r.status_code == 429
    assert r.json()["detail"]["message"] == VOICE_SPEND_CAP_MESSAGE
    transcribe.assert_not_awaited()


def test_speech_transcribe_json_ok():
    import base64

    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    payload = {
        "audio_base64": base64.b64encode(b"fake-audio").decode(),
        "filename": "speech.m4a",
    }
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="hello json"),
        ),
    ):
        r = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok", "Content-Type": "application/json"},
            json=payload,
        )
    assert r.status_code == 200
    assert r.json()["text"] == "hello json"


def test_speech_transcribe_json_forwards_language():
    import base64

    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    payload = {
        "audio_base64": base64.b64encode(b"fake-audio").decode(),
        "filename": "speech.m4a",
        "language": "es-MX",
    }
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    transcribe = AsyncMock(return_value="hola")
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch("app.modules.speech.api.speech_service.transcribe_audio", transcribe),
    ):
        r = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok", "Content-Type": "application/json"},
            json=payload,
        )
    assert r.status_code == 200
    assert r.json()["text"] == "hola"
    assert transcribe.await_args.kwargs["language"] == "es-MX"


def test_speech_transcribe_empty_text_ok():
    """Empty transcript is a valid no-speech result — 200 with empty text, not a 502 outage."""
    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value=""),
        ),
    ):
        r = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"silence", "audio/m4a")},
        )
    assert r.status_code == 200
    assert r.json()["text"] == ""


def test_speech_transcribe_provider_failure_is_502():
    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value=None),
        ),
    ):
        r = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
    assert r.status_code == 502


def test_speech_transcribe_daily_cap():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        daily_speech_transcriptions_plus=1
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="ok"),
        ),
    ):
        first = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
        second = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
    assert first.status_code == 200
    assert second.status_code == 429


def test_speech_transcribe_cancelled_refunds():
    """Hard cancel (CancelledError) must refund — except Exception would miss it."""
    import asyncio

    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def boom(*_args: object, **_kwargs: object) -> str:
        raise asyncio.CancelledError()

    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch("app.modules.speech.api.speech_service.transcribe_audio", boom),
        patch(
            "app.services.quota.counters.refund",
            AsyncMock(),
        ) as refund,
    ):
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            client.post(
                "/speech/transcribe",
                headers={"Authorization": "Bearer tok"},
                files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
            )
    refund.assert_awaited()


def test_speech_transcribe_rate_limit():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        speech_rate_limit_per_minute=1,
        daily_speech_transcriptions_plus=100,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="ok"),
        ),
    ):
        first = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
        second = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
    assert first.status_code == 200
    assert second.status_code == 429


def test_speech_transcribe_disabled():
    user = api_user(plan="plus")
    from app.core.deps import get_current_user, get_settings_dep

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        speech_transcription_enabled=False
    )
    client = TestClient(app)
    r = client.post(
        "/speech/transcribe",
        headers={"Authorization": "Bearer tok"},
        files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
    )
    assert r.status_code == 404


def test_speech_transcribe_rejects_oversized_multipart_content_length():
    """Multipart uploads with a Content-Length over the limit must be rejected
    BEFORE the file is read into memory (memory-exhaustion DoS guard)."""
    import fakeredis.aioredis

    from app.modules.speech.schemas import SPEECH_MAX_REQUEST_BYTES

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    oversized = b"x" * (SPEECH_MAX_REQUEST_BYTES + 1)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="should not reach"),
        ) as transcribe_mock,
    ):
        r = client.post(
            "/speech/transcribe",
            headers={
                "Authorization": "Bearer tok",
                "Content-Length": str(len(oversized)),
            },
            files={"file": ("speech.m4a", oversized, "audio/m4a")},
        )
    assert r.status_code == 413
    transcribe_mock.assert_not_awaited()


def test_speech_transcribe_6mb_is_413_before_quota():
    """6MB used to pass the 7.5MB body cap, reserve quota, then 502 at 5MB."""
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        daily_speech_transcriptions_plus=1
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    six_mb = b"x" * 6_000_000
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.transcribe_audio",
            AsyncMock(return_value="ok"),
        ) as transcribe_mock,
    ):
        oversized = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", six_mb, "audio/m4a")},
        )
        ok = client.post(
            "/speech/transcribe",
            headers={"Authorization": "Bearer tok"},
            files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
        )
    assert oversized.status_code == 413
    assert ok.status_code == 200
    transcribe_mock.assert_awaited_once()


def test_speech_tts_ok():
    import base64

    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=(b"fake-mp3", "audio/mpeg")),
        ),
    ):
        r = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "hello", "language": "en-US"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["content_type"] == "audio/mpeg"
    assert body["model"] == "speech-tts-model"
    assert base64.b64decode(body["audio_base64"]) == b"fake-mp3"


def test_speech_tts_cancelled_refunds():
    import asyncio

    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def boom(*_args: object, **_kwargs: object) -> tuple[bytes, str]:
        raise asyncio.CancelledError()

    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch("app.modules.speech.api.speech_service.synthesize_speech", boom),
        patch(
            "app.services.quota.counters.refund",
            AsyncMock(),
        ) as refund,
    ):
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            client.post(
                "/speech/tts",
                headers={"Authorization": "Bearer tok"},
                json={"text": "hello"},
            )
    refund.assert_awaited()


def test_speech_tts_daily_cap():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(daily_speech_tts_plus=1)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=(b"ok", "audio/mpeg")),
        ),
    ):
        first = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "one"},
        )
        second = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "two"},
        )
    assert first.status_code == 200
    assert second.status_code == 429
    assert "read-aloud" in second.json()["detail"]["message"].lower()


def test_speech_tts_lead_allows_multiple_rest_followups():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(daily_speech_tts_plus=1)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=(b"ok", "audio/mpeg")),
        ),
    ):
        lead = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "first clip", "part": "lead"},
        )
        lead_hash = lead.json()["lead_hash"]
        rest_one = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "second clip", "part": "rest", "lead_hash": lead_hash},
        )
        rest_two = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "third clip", "part": "rest", "lead_hash": lead_hash},
        )
        extra_full = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "another page", "part": "full"},
        )
    assert lead.status_code == 200
    assert rest_one.status_code == 200
    assert rest_two.status_code == 200
    assert extra_full.status_code == 429


def test_speech_tts_rest_wrong_lead_hash_is_billed():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(daily_speech_tts_plus=1)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=(b"ok", "audio/mpeg")),
        ),
    ):
        lead = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "first clip", "part": "lead"},
        )
        wrong = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={
                "text": "other utterance rest",
                "part": "rest",
                "lead_hash": "deadbeefdeadbeef",
            },
        )
        matched = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={
                "text": "second clip",
                "part": "rest",
                "lead_hash": lead.json()["lead_hash"],
            },
        )
    assert lead.status_code == 200
    assert lead.json()["lead_hash"]
    assert wrong.status_code == 429
    assert matched.status_code == 200


def test_speech_tts_rest_over_char_budget_is_billed():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(daily_speech_tts_plus=1)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=(b"ok", "audio/mpeg")),
        ),
    ):
        lead = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "hi", "part": "lead"},
        )
        rest_over = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={
                "text": "x" * 3999,
                "part": "rest",
                "lead_hash": lead.json()["lead_hash"],
            },
        )
    assert lead.status_code == 200
    assert rest_over.status_code == 429


def test_speech_tts_rate_limit_message():
    import fakeredis.aioredis

    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="plus")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        speech_rate_limit_per_minute=1,
        daily_speech_tts_plus=100,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(app)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.api.speech_service.synthesize_speech",
            AsyncMock(return_value=(b"ok", "audio/mpeg")),
        ),
    ):
        first = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "one"},
        )
        second = client.post(
            "/speech/tts",
            headers={"Authorization": "Bearer tok"},
            json={"text": "two"},
        )
    assert first.status_code == 200
    assert second.status_code == 429
    assert "read-aloud" in second.json()["detail"]["message"].lower()


def test_speech_tts_disabled():
    user = api_user(plan="plus")
    from app.core.deps import get_current_user, get_settings_dep

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(speech_tts_enabled=False)
    client = TestClient(app)
    r = client.post(
        "/speech/tts",
        headers={"Authorization": "Bearer tok"},
        json={"text": "hello"},
    )
    assert r.status_code == 404


@pytest.mark.parametrize(
    "path, provider, prefix, status_code",
    [
        ("/speech/transcribe", "transcribe_audio", "speech", 502),
        ("/speech/tts", "synthesize_speech", "tts", 502),
    ],
)
def test_speech_refunds_the_day_it_reserved(quota_clock, path, provider, prefix, status_code):
    """A clip reserved before UTC midnight that fails after it refunds the first day."""
    import asyncio

    import fakeredis.aioredis

    async def fails_after_midnight(*_args, **_kwargs):
        quota_clock.day = quota_clock.next_day

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(f"app.modules.speech.api.speech_service.{provider}", fails_after_midnight),
    ):
        if path == "/speech/transcribe":
            files = {"file": ("speech.m4a", b"fake-audio", "audio/m4a")}
            r = client.post(path, headers={"Authorization": "Bearer tok"}, files=files)
        else:
            r = client.post(path, headers={"Authorization": "Bearer tok"}, json={"text": "hello"})
        keys = [f"{prefix}:{user.id}:2026-10-{n}" for n in (16, 17)]
        assert asyncio.run(fake_redis.mget(keys)) == ["0", None]
    assert r.status_code == status_code


@pytest.mark.parametrize(
    "path, body",
    [
        ("/speech/transcribe", None),
        ("/speech/tts", {"text": "hello"}),
    ],
)
def test_free_plan_is_refused_voice_input_and_read_aloud(path, body):
    """Called directly, the endpoints refuse a plan without the feature (403 →
    the app opens the paywall), before any audio is read or quota is touched."""
    user = api_user(plan="free")
    client = TestClient(app_with_user(user))
    with (
        patch("app.modules.speech.api.get_redis_client") as redis_client,
        patch("app.modules.speech.api.speech_service.transcribe_audio", AsyncMock()) as stt,
        patch("app.modules.speech.api.speech_service.synthesize_speech", AsyncMock()) as tts,
    ):
        if body is None:
            r = client.post(
                path,
                headers={"Authorization": "Bearer tok"},
                files={"file": ("speech.m4a", b"fake-audio", "audio/m4a")},
            )
        else:
            r = client.post(path, headers={"Authorization": "Bearer tok"}, json=body)
    assert r.status_code == 403
    assert "Upgrade" in r.json()["detail"]["message"]
    redis_client.assert_not_called()
    stt.assert_not_awaited()
    tts.assert_not_awaited()


def test_speech_live_status_free_not_entitled():
    import fakeredis.aioredis

    user = api_user(plan="free")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.modules.speech.api.get_redis_client", return_value=fake_redis):
        r = client.get("/speech/live", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["entitled"] is False
    assert body["remaining"] == 0
    assert body["limit"] == 0


def test_speech_live_status_pro_remaining():
    import fakeredis.aioredis

    user = api_user(plan="pro")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.modules.speech.api.get_redis_client", return_value=fake_redis):
        r = client.get("/speech/live", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["entitled"] is True
    assert body["remaining"] == 60
    assert body["limit"] == 60
    assert body["remaining_seconds"] == 3600
    assert body["resets_at"].endswith("T00:00:00Z")


def test_speech_live_status_plus_not_entitled():
    import fakeredis.aioredis

    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.modules.speech.api.get_redis_client", return_value=fake_redis):
        r = client.get("/speech/live", headers={"Authorization": "Bearer tok"})
    assert r.json()["entitled"] is False
    assert r.json()["limit"] == 0


def test_speech_live_disabled():
    from app.core.deps import get_current_user, get_settings_dep

    user = api_user(plan="pro")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings(speech_live_talk_enabled=False)
    client = TestClient(app)
    r = client.get("/speech/live", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_list_messages_takes_one_cursor():
    """NET-18: a page is before, after or around one message, never two at once."""
    user = api_user()
    app = app_with_user(user)
    chat_id = uuid4()
    client = TestClient(app)
    response = client.get(
        f"/chats/{chat_id}/messages",
        params={"before": str(uuid4()), "around": str(uuid4())},
        headers={"Authorization": "Bearer tok"},
    )
    assert response.status_code == 422
