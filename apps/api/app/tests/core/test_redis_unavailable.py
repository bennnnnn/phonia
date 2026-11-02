"""Redis outage → RedisUnavailableError (fail closed, 503 / unavailable)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import deps
from app.core.access_tokens import create_access_token
from app.core.config import Settings
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.models.schemas import LogoutRequest, RefreshRequest
from app.modules.account import api as auth_router
from app.modules.account import tokens as tokens_service
from app.modules.chat.stream_events import error_payload_for_exception
from app.services import quota as quota_service
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
async def test_reserve_usage_up_to_raises_when_redis_down():
    server = fakeredis.FakeServer()
    server.connected = False
    redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    with pytest.raises(RedisUnavailableError):
        await quota_service.reserve_usage_up_to(redis, "u1", 100, daily_limit=1000)


@pytest.mark.asyncio
async def test_verify_access_token_raises_when_redis_down():
    settings = Settings(jwt_secret="x" * 32)
    token = create_access_token(uuid4(), settings)
    redis = redis_mock()
    redis.mget = AsyncMock(side_effect=RedisConnectionError("down"))
    with pytest.raises(RedisUnavailableError):
        await tokens_service.verify_access_token(redis, token, settings)


@pytest.mark.asyncio
async def test_refresh_token_pair_raises_when_redis_down():
    settings = Settings(jwt_secret="x" * 32)
    redis = redis_mock()
    redis.get = AsyncMock(side_effect=RedisConnectionError("down"))
    with pytest.raises(RedisUnavailableError):
        await tokens_service.refresh_token_pair(redis, "rtok", AsyncMock(), settings)


@pytest.mark.asyncio
async def test_revoke_access_token_raises_when_redis_down():
    settings = Settings(jwt_secret="x" * 32)
    token = create_access_token(uuid4(), settings)
    redis = redis_mock()
    redis.set = AsyncMock(side_effect=RedisConnectionError("down"))
    with pytest.raises(RedisUnavailableError):
        await tokens_service.revoke_access_token(redis, token, settings)


@pytest.mark.asyncio
async def test_get_current_user_maps_redis_outage_to_503():
    settings = Settings(jwt_secret="test-secret-32-chars-long-enough!!")
    credentials = MagicMock()
    credentials.credentials = "tok"
    with patch(
        "app.core.deps.access_tokens.check_access",
        AsyncMock(side_effect=RedisUnavailableError()),
    ):
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user(
                credentials=credentials,
                settings=settings,
                redis=redis_mock(),
            )
    assert exc.value.status_code == 503
    assert exc.value.headers is not None
    assert exc.value.headers.get("Retry-After") == "5"
    # The app's one unavailable body (core/unavailable.py): the code the phone words.
    assert exc.value.detail == {
        "code": "unavailable",
        "message": "Service temporarily unavailable. Please retry shortly.",
    }


@pytest.mark.asyncio
async def test_refresh_session_leaves_a_redis_outage_to_the_503_handler():
    """``core/unavailable`` answers it 503 + Retry-After, as for every route."""
    settings = Settings(jwt_secret="test-secret-32-chars-long-enough!!")
    request = MagicMock()
    request.client = MagicMock(host="127.0.0.1")
    with (
        patch(
            "app.modules.account.refresh_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.account.refresh_limit.tokens_service.refresh_token_user",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.account.api.tokens_service.refresh_token_pair",
            AsyncMock(side_effect=RedisUnavailableError()),
        ),
    ):
        with pytest.raises(RedisUnavailableError):
            await auth_router.refresh_session(
                RefreshRequest(refresh_token="rtok"),
                request,
                session=AsyncMock(),
                settings=settings,
                redis=redis_mock(),
            )


@pytest.mark.asyncio
async def test_logout_leaves_a_redis_outage_to_the_503_handler():
    """``core/unavailable`` answers it 503 + Retry-After, as for every route."""
    settings = Settings(jwt_secret="test-secret-32-chars-long-enough!!")
    request = MagicMock()
    request.headers = {"authorization": "Bearer atok"}
    with patch(
        "app.modules.account.api.tokens_service.revoke_access_token",
        AsyncMock(side_effect=RedisUnavailableError()),
    ):
        with pytest.raises(RedisUnavailableError):
            await auth_router.logout(
                LogoutRequest(refresh_token="rtok"),
                request=request,
                settings=settings,
                redis=redis_mock(),
                session=AsyncMock(),
            )


def test_error_payload_for_redis_unavailable():
    payload = error_payload_for_exception(RedisUnavailableError())
    assert payload["type"] == "error"
    assert payload["code"] == "unavailable"


@pytest.mark.asyncio
async def test_verify_access_token_reads_the_revocation_keys_in_one_round_trip(fake_redis):
    """Every authenticated request checks three revocation keys: one MGET, not three GETs."""
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    token = create_access_token(user_id, settings, session_id="device-1")
    calls: list[str] = []
    original_mget, original_get = fake_redis.mget, fake_redis.get

    async def mget(*keys):
        calls.append("mget")
        return await original_mget(*keys)

    async def get(key):
        calls.append("get")
        return await original_get(key)

    fake_redis.mget, fake_redis.get = mget, get
    assert await tokens_service.verify_access_token(fake_redis, token, settings) == user_id
    assert calls == ["mget"]
    await fake_redis.set(f"revoked:sid:{'device-1'}", "1")
    with pytest.raises(AuthenticationError):
        await tokens_service.verify_access_token(fake_redis, token, settings)
