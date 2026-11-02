"""The refusals a client switches on, as the API sends them (code-health audit DUP-10).

The phone recovered a refusal's meaning by matching the server's English ("Too many
scans in a row…", ``/content type/``), so a reworded message silently changed what it
did. Each refusal now names a ``code``. ``docs/fixtures/error_codes.json`` is written
here from real requests (``UPDATE_ERROR_CODES=1``) and read by the phone's tests, which
key their words and actions on the codes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import TransportError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_settings_dep
from app.core.spend_counter import MICRO_USD_PER_USD, spend_key
from app.gateways.openai_speech_gateway import RealtimeClientSecretResult
from app.main import create_app
from app.models.orm import User
from app.models.schemas.scan import SCAN_MAX_IMAGE_BYTES
from app.modules.account.email_authority import AccountExistsError
from app.modules.speech.live_talk import LiveTalkSessionContext
from app.services.quota import IMAGE_GENERATION_SPEND_CAP_MESSAGE, counters

FIXTURE = Path(__file__).resolve().parents[4] / "docs" / "fixtures" / "error_codes.json"
_AUTH = {"Authorization": "Bearer tok"}
_IMAGE = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()


def _client(user: Any, settings: Settings | None = None) -> TestClient:
    async def db() -> Any:
        yield SimpleNamespace(refresh=AsyncMock(), commit=AsyncMock())

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_settings_dep] = lambda: settings or Settings()
    return TestClient(app)


def _user(*, consented: bool = True) -> Any:
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.plan = "free"
    user.ai_data_consent_at = object() if consented else None
    return user


def _refusal(response: Any) -> dict[str, Any]:
    return {"status": response.status_code, "detail": response.json()["detail"]}


def _scan(body: dict[str, Any], *, settings: Settings | None = None, **redis: bool) -> Any:
    with (
        patch("app.services.scan_read.get_redis_client", return_value=MagicMock()),
        patch(
            "app.services.scan_read.quota_service.global_spend_exceeded",
            AsyncMock(return_value=redis.get("spend_exceeded", False)),
        ),
        patch("app.services.scan_read.quota_service.record_global_spend", AsyncMock()),
        patch(
            "app.services.scan_read.allow_request_unless_down",
            AsyncMock(return_value=redis.get("allowed", True)),
        ),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        return _client(_user(), settings).post("/math/scan/read", headers=_AUTH, json=body)


async def _seed(redis: Any, key: str, value: int) -> None:
    await redis.set(key, value, ex=60)


def _presign(content_type: str, size_bytes: int, *, at_daily_cap: bool = False) -> Any:
    user = _user()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    if at_daily_cap:
        day = counters.utc_today().isoformat()
        cap = counters.limit("image_upload", user, Settings())
        asyncio.run(_seed(fake_redis, f"imgup:{user.id}:{day}", cap))
    with (
        patch("app.modules.attachments.upload.get_redis_client", return_value=fake_redis),
    ):
        return _client(user).post(
            "/attachments/presign",
            headers=_AUTH,
            json={"content_type": content_type, "size_bytes": size_bytes},
        )


def _transcribe(
    *, at_daily_cap: bool = False, allowed: bool = True, spend_capped: bool = False
) -> Any:
    """POST /speech/transcribe for a Pro user, at the day's cap or past the minute's rate,
    or with the day's global spend cap reached."""
    user = _user()
    user.plan = "pro"
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    if at_daily_cap:
        cap = counters.limit("speech_transcription", user, Settings())
        key = counters.daily_key("speech", user.id, counters.utc_today())
        asyncio.run(_seed(fake_redis, key, cap))
    if spend_capped:
        asyncio.run(_seed(fake_redis, spend_key(), 2 * MICRO_USD_PER_USD))
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.gates.allow_request_unless_down",
            AsyncMock(return_value=allowed),
        ),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        return _client(user, Settings(daily_global_spend_usd=1.0)).post(
            "/speech/transcribe",
            headers=_AUTH,
            json={"audio_base64": base64.b64encode(b"audio").decode(), "filename": "a.m4a"},
        )


def _memory_instruct(*, spend_capped: bool = False, allowed: bool = True) -> Any:
    """POST /memories/instruct while the day's spend cap is reached, past the hour's
    edits (``allowed``), or (below both) while another write holds the user's memory."""
    with (
        patch(
            "app.modules.memory.api.allow_request_unless_down",
            AsyncMock(return_value=allowed),
        ),
        patch("app.modules.memory.api.get_redis_client", return_value=MagicMock()),
        patch(
            "app.modules.memory.api.quota_service.global_spend_exceeded",
            AsyncMock(return_value=spend_capped),
        ),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.core.rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.modules.memory.locks.take_memory_write_lock", AsyncMock(return_value=None)),
    ):
        return _client(_user()).post(
            "/memories/instruct", headers=_AUTH, json={"instruction": "Remember I like tea"}
        )


def _live_talk_unconfigured() -> Any:
    """POST /speech/live/session for a Pro user on a server with no Realtime key."""
    user = _user()
    user.plan = "pro"
    user.tts_voice = None
    settings = Settings(
        speech_live_talk_enabled=True, speech_realtime_voice_enabled=True, openai_api_key=""
    )
    with (
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_session_context",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        return _client(user, settings).post("/speech/live/session", headers=_AUTH, json={})


_LIVE_TALK_ON = Settings(
    openai_api_key="sk-test", speech_live_talk_enabled=True, speech_realtime_voice_enabled=True
)


def _live_talk(
    path: str,
    *,
    settings: Settings | None = None,
    plan: str = "pro",
    consented: bool = True,
    **refused: bool,
) -> Any:
    """POST a live talk route for a user on ``plan``, refused where ``refused`` says.

    ``rate_limited``: the route's own per-minute limit is used up; ``spend_capped``: the
    voice spend breaker is open; ``minutes_used``: the month has no session left;
    ``mint_failed``: the realtime provider minted no key; ``saves_used``: the call saved
    every turn it may; ``session_ended``: the save names no live session. A save names
    this chat's session.
    """
    user = _user(consented=consented)
    user.plan = plan
    user.tts_voice = None
    user.custom_instructions = None
    chat_id = uuid4()
    allowed = AsyncMock(return_value=not refused.get("rate_limited"))
    minted = RealtimeClientSecretResult(value="ek_test", expires_at=123)
    with (
        patch(
            "app.modules.speech.realtime.get_redis_client",
            return_value=fakeredis.aioredis.FakeRedis(decode_responses=True),
        ),
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_session_context",
            AsyncMock(return_value=LiveTalkSessionContext(None, "", "")),
        ),
        patch(
            "app.modules.speech.realtime.live_talk_service.realtime_session_bound_chat_id",
            AsyncMock(return_value=None if refused.get("session_ended") else chat_id),
        ),
        patch("app.modules.speech.gates.allow_request_unless_down", allowed),
        patch("app.modules.speech.realtime.allow_request_unless_down", allowed),
        patch(
            "app.services.quota.global_spend_exceeded",
            AsyncMock(return_value=refused.get("spend_capped", False)),
        ),
        patch(
            "app.services.quota.reserve_live_talk_seconds",
            AsyncMock(return_value=0 if refused.get("minutes_used") else 900),
        ),
        patch(
            "app.services.quota.take_live_talk_save",
            AsyncMock(return_value=not refused.get("saves_used")),
        ),
        patch(
            "app.modules.speech.realtime.openai_speech_gateway.create_realtime_client_secret",
            AsyncMock(return_value=None if refused.get("mint_failed") else minted),
        ),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        body = {"chat_id": str(chat_id), "call_id": "issued-session", "user_text": "hi"}
        return _client(user, settings or _LIVE_TALK_ON).post(
            path, headers=_AUTH, json=body if path.endswith("/persist") else {}
        )


def _generate(code: str) -> Any:
    """POST /images/generate refused the way the picture service refuses."""
    from app.modules.images.generation import ImageGenerationError

    refusals = {
        "daily_limit": ImageGenerationError(
            "No more pictures today.",
            status_code=429,
            code="daily_limit",
            feature="image_generation",
        ),
        "content_blocked": ImageGenerationError(
            "That picture can't be made.",
            status_code=422,
            code="content_blocked",
            feature="image_generation",
        ),
        "spend_cap": ImageGenerationError(
            IMAGE_GENERATION_SPEND_CAP_MESSAGE, status_code=429, code="spend_cap"
        ),
        # The image service failed (generation.py's 502s): the code is the status's.
        "upstream_failed": ImageGenerationError("Could not generate image", status_code=502),
    }
    with (
        patch(
            "app.modules.images.api.image_generation_service.generate_for_chat",
            AsyncMock(side_effect=refusals[code]),
        ),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        return _client(_user()).post(
            "/images/generate", headers=_AUTH, json={"chat_id": str(uuid4()), "prompt": "a cat"}
        )


_APPLE_PAYLOAD = {"sub": "apple-1", "email": "person@icloud.com", "email_verified": "true"}
_GOOGLE_PAYLOAD = {"sub": "google-1", "email": "person@gmail.com", "email_verified": True}


def _sign_in(
    provider: str,
    *,
    settings: Settings | None = None,
    google: Any = None,
    apple: Any = None,
    address_allowed: bool = True,
    redis_down: bool = False,
) -> Any:
    """POST /auth/<provider> as the phone sends it, refused where the refusal starts.

    ``google`` stands in for Google's verify (its return value, or the error it raises);
    ``apple`` for the Apple payload the gateway accepted. No account holds the identity.
    ``redis_down``: the limits' counter cannot be read.
    """
    verify = (
        MagicMock(side_effect=google)
        if isinstance(google, Exception)
        else MagicMock(return_value=google)
    )
    bodies = {
        "google": {"id_token": "token"},
        "apple": {"id_token": "token", "nonce": "nonce"},
        "dev": {"email": "dev@recall.local"},
    }
    with (
        patch("app.gateways.google_auth.id_token.verify_oauth2_token", verify),
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(return_value=apple),
        )
        if apple is not None
        else nullcontext(),
        patch(
            "app.core.rate_limit.allow_request",
            AsyncMock(side_effect=RedisConnectionError("down")),
        )
        if redis_down
        else patch(
            "app.modules.account.signin_limit.address_allowed",
            AsyncMock(return_value=address_allowed),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub", AsyncMock(return_value=None)
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_apple_sub", AsyncMock(return_value=None)
        ),
    ):
        return _client(_user(), settings).post(f"/auth/{provider}", json=bodies[provider])


def _apple_token(kid: str) -> str:
    """A token whose header names ``kid``: Apple's keys are looked up before its signature."""
    return pyjwt.encode(
        {"sub": "apple-1"}, "secret-32-bytes-long-enough-for-hs256", headers={"kid": kid}
    )


def _apple(token: str, *, keys: list[dict[str, Any]] | None = None) -> Any:
    """POST /auth/apple through the real gateway; Apple's keys are ``keys``, or unreachable."""
    response = MagicMock(raise_for_status=lambda: None, json=lambda: {"keys": keys or []})
    client = MagicMock(get=AsyncMock(return_value=response))
    with (
        patch("app.gateways.apple_auth.get_pooled_client", return_value=client)
        if keys is not None
        else nullcontext(),
        patch("app.modules.account.signin_limit.address_allowed", AsyncMock(return_value=True)),
    ):
        return _client(_user()).post("/auth/apple", json={"id_token": token, "nonce": "nonce"})


def _sign_in_bodies() -> dict[str, dict[str, Any]]:
    """Every refusal of /auth/google, /auth/apple and /auth/dev the login screen words."""
    no_apple = Settings(apple_client_id="")
    # Before any case keeps Apple's keys: a kid they lack refetches once per interval only.
    apple_unavailable = _refusal(_apple(_apple_token("any-kid")))
    return {
        "sign_in_rate_limited": _refusal(_sign_in("google", address_allowed=False)),
        "sign_in_unavailable": _refusal(_sign_in("google", redis_down=True)),
        "google_token_invalid": _refusal(_sign_in("google", google=ValueError("bad token"))),
        "google_unavailable": _refusal(_sign_in("google", google=TransportError("down"))),
        "google_email_unverified": _refusal(
            _sign_in("google", google={**_GOOGLE_PAYLOAD, "email_verified": False})
        ),
        "google_email_missing": _refusal(
            _sign_in("google", google={**_GOOGLE_PAYLOAD, "email": ""})
        ),
        "apple_not_configured": _refusal(_sign_in("apple", settings=no_apple)),
        "apple_token_invalid": _refusal(_apple("not-a-token", keys=[])),
        "apple_key_unknown": _refusal(_apple(_apple_token("unknown-kid"), keys=[])),
        "apple_unavailable": apple_unavailable,
        "apple_email_unverified": _refusal(
            _sign_in("apple", apple={**_APPLE_PAYLOAD, "email_verified": "false"})
        ),
        "apple_email_missing": _refusal(_sign_in("apple", apple={**_APPLE_PAYLOAD, "email": None})),
        "dev_auth_disabled": _refusal(_sign_in("dev", settings=Settings(dev_auth_enabled=False))),
    }


def _outage() -> Any:
    """A read while Redis is down: the request limiter cannot count, so it answers what any
    route's database or Redis outage answers (``core/unavailable.py``)."""
    with patch(
        "app.core.rest_rate_limit.allow_request",
        AsyncMock(side_effect=RedisConnectionError("down")),
    ):
        return _client(_user()).get("/todos/page", headers=_AUTH)


def _over_the_limit() -> Any:
    """A read past the request limiter's minute (``core/rest_rate_limit.py``)."""
    with patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=False)):
        return _client(_user()).get("/todos/page", headers=_AUTH)


def _chat_over_its_limit() -> Any:
    """A Regenerate past the chat stream's own per-user limit (``require_chat_rate_limit``)."""
    # The limit's own counter says no (core.rate_limit), so the route's real check runs.
    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.core.rate_limit.allow_request", AsyncMock(return_value=False)),
    ):
        return _client(_user()).post(f"/chats/{uuid4()}/regenerate/stream", headers=_AUTH, json={})


def _refresh_over_its_limit() -> Any:
    """A refresh past its per-address limit (``modules/account/refresh_limit.py``)."""
    with patch("app.modules.account.refresh_limit.address_allowed", AsyncMock(return_value=False)):
        return _client(_user()).post("/auth/refresh", json={"refresh_token": "token"})


def _link_preview(*, allowed: bool = True, busy: bool = False) -> Any:
    """GET /link-preview past the user's minute, or with their most previews loading."""
    from app.modules.link_preview.service import LinkPreviewBusyError

    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.modules.link_preview.api.get_redis_client", return_value=MagicMock()),
        patch(
            "app.modules.link_preview.api.allow_request_unless_down",
            AsyncMock(return_value=allowed),
        ),
        patch(
            "app.modules.link_preview.api.fetch_link_preview_cached",
            AsyncMock(side_effect=LinkPreviewBusyError() if busy else None),
        ),
    ):
        return _client(_user()).get(
            "/link-preview", headers=_AUTH, params={"url": "https://example.com/a"}
        )


def _export_busy() -> Any:
    """GET /auth/me/export past the hour's exports (one runs at a time, a few an hour)."""
    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
        patch("app.modules.account.api.allow_request_unless_down", AsyncMock(return_value=False)),
    ):
        return _client(_user()).get("/auth/me/export", headers=_AUTH)


def _bodies() -> dict[str, dict[str, Any]]:
    too_big = base64.b64encode(b"\xff" * (SCAN_MAX_IMAGE_BYTES + 1)).decode()
    with (
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        consent = _client(_user(consented=False)).post(
            "/math/scan/read", headers=_AUTH, json={"image_base64": _IMAGE}
        )
    with (
        patch(
            "app.modules.account.api.auth_service.login_with_google",
            AsyncMock(side_effect=AccountExistsError("apple")),
        ),
        patch("app.modules.account.signin_limit.address_allowed", AsyncMock(return_value=True)),
    ):
        exists = _client(_user()).post("/auth/google", json={"id_token": "token"})
    return {
        "service_unavailable": _refusal(_outage()),
        "rate_limited": _refusal(_over_the_limit()),
        # Each route's own limit over its minute answers the same code.
        "chat_rate_limited": _refusal(_chat_over_its_limit()),
        "refresh_rate_limited": _refusal(_refresh_over_its_limit()),
        "link_preview_rate_limited": _refusal(_link_preview(allowed=False)),
        "link_preview_busy": _refusal(_link_preview(busy=True)),
        "consent_required": _refusal(consent),
        "account_exists": _refusal(exists),
        "scan_not_available": _refusal(
            _scan({"image_base64": _IMAGE}, settings=Settings(math_tools_enabled=False))
        ),
        "scan_too_large": _refusal(_scan({"image_base64": too_big})),
        "scan_invalid_image": _refusal(_scan({"image_base64": "not base64!"})),
        "scan_rate_limited": _refusal(_scan({"image_base64": _IMAGE}, allowed=False)),
        "scan_spend_cap": _refusal(_scan({"image_base64": _IMAGE}, spend_exceeded=True)),
        "presign_unsupported_type": _refusal(_presign("application/x-msdownload", 100)),
        # The schema caps the size: FastAPI's own 422, which the phone reads as too large.
        "presign_too_large": {
            "status": (too_large := _presign("image/png", 10_485_761)).status_code,
            "detail": too_large.json()["detail"],
        },
        "presign_daily_limit": _refusal(_presign("image/png", 128, at_daily_cap=True)),
        "dictation_daily_limit": _refusal(_transcribe(at_daily_cap=True)),
        "dictation_rate_limited": _refusal(_transcribe(allowed=False)),
        # Every voice request at the day's spend cap: dictation, live talk's session and saves.
        "voice_spend_cap": _refusal(_transcribe(spend_capped=True)),
        "live_talk_not_configured": _refusal(_live_talk_unconfigured()),
        "live_talk_minutes_used": _refusal(_live_talk("/speech/live/session", minutes_used=True)),
        "live_talk_rate_limited": _refusal(_live_talk("/speech/live/session", rate_limited=True)),
        "live_talk_spend_cap": _refusal(_live_talk("/speech/live/session", spend_capped=True)),
        "live_talk_upstream_failed": _refusal(_live_talk("/speech/live/session", mint_failed=True)),
        "live_talk_not_available": _refusal(
            _live_talk(
                "/speech/live/session", settings=Settings(speech_realtime_voice_enabled=False)
            )
        ),
        # The paywall opens for this code only; consent opens the consent step instead.
        "live_talk_not_in_plan": _refusal(_live_talk("/speech/live/session", plan="free")),
        "live_talk_consent_required": _refusal(_live_talk("/speech/live/session", consented=False)),
        "live_talk_save_rate_limited": _refusal(
            _live_talk("/speech/live/persist", rate_limited=True)
        ),
        "live_talk_save_spend_cap": _refusal(_live_talk("/speech/live/persist", spend_capped=True)),
        "live_talk_saves_used": _refusal(_live_talk("/speech/live/persist", saves_used=True)),
        # A save the plan or the session no longer allows ends the call.
        "live_talk_save_not_in_plan": _refusal(_live_talk("/speech/live/persist", plan="free")),
        "live_talk_session_ended": _refusal(_live_talk("/speech/live/persist", session_ended=True)),
        "memory_spend_cap": _refusal(_memory_instruct(spend_capped=True)),
        "memory_busy": _refusal(_memory_instruct()),
        "memory_rate_limited": _refusal(_memory_instruct(allowed=False)),
        "export_busy": _refusal(_export_busy()),
        "image_daily_limit": _refusal(_generate("daily_limit")),
        "image_content_blocked": _refusal(_generate("content_blocked")),
        "image_spend_cap": _refusal(_generate("spend_cap")),
        "image_upstream_failed": _refusal(_generate("upstream_failed")),
        **_sign_in_bodies(),
    }


@pytest.mark.usefixtures("consent_enforced")
def test_the_fixture_is_what_the_api_sends() -> None:
    bodies = _bodies()
    if os.environ.get("UPDATE_ERROR_CODES"):
        FIXTURE.write_text(json.dumps(bodies, indent=1, ensure_ascii=False) + "\n")
    assert json.loads(FIXTURE.read_text()) == bodies


def test_every_refusal_in_the_fixture_names_a_code() -> None:
    for name, refusal in json.loads(FIXTURE.read_text()).items():
        assert refusal["status"] >= 400, name
        if refusal["status"] != 422:  # FastAPI's validation body: a list of errors
            assert refusal["detail"]["code"] and refusal["detail"]["message"], name
