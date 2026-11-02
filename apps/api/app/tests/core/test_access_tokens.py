"""Every request's token check reads its revocation keys in one Redis round trip.

The token, its signed-in device and the user's revoked-since cutoff were three
GETs, one after another, before every authenticated request and every chat frame.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import access_tokens, user_cache
from app.core.config import Settings
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.tests.fakes import redis_mock

_SETTINGS = Settings(jwt_secret="x" * 32)


def _commands(redis: Any) -> list[str]:
    """Record every round trip ``redis`` makes from here on: a command, or a pipeline."""
    sent: list[str] = []
    execute = redis.execute_command
    pipeline = redis.pipeline

    async def recording(*args: Any, **kwargs: Any) -> Any:
        sent.append(str(args[0]).upper())
        return await execute(*args, **kwargs)

    def recording_pipeline(*args: Any, **kwargs: Any) -> Any:
        pipe = pipeline(*args, **kwargs)
        run = pipe.execute

        async def execute_pipe(*a: Any, **k: Any) -> Any:
            sent.append("PIPELINE[" + ",".join(str(c[0][0]) for c in pipe.command_stack) + "]")
            return await run(*a, **k)

        pipe.execute = execute_pipe
        return pipe

    redis.execute_command = recording
    redis.pipeline = recording_pipeline
    return sent


async def _with_generation(redis: Any, claims: dict[str, Any]) -> None:
    """The user's row generation exists, as it does after the first request."""
    await redis.set(user_cache.generation_key(UUID(claims["sub"])), "g1")


def _token(*, session_id: str | None = "device-1") -> tuple[str, dict[str, Any]]:
    token = access_tokens.create_access_token(uuid4(), _SETTINGS, session_id=session_id)
    return token, jwt.decode(token, _SETTINGS.jwt_secret, algorithms=["HS256"])


async def _revoke_token(redis: Any, claims: dict[str, Any]) -> None:
    await redis.set(access_tokens.revoked_key(claims["jti"]), "1")


async def _revoke_device(redis: Any, claims: dict[str, Any]) -> None:
    await redis.set(access_tokens.revoked_session_key(claims["sid"]), "1")


async def _revoke_since_now(redis: Any, claims: dict[str, Any]) -> None:
    await redis.set(access_tokens.revoked_since_key(claims["sub"]), str(time.time() + 1))


@pytest.mark.parametrize("revoke", [_revoke_token, _revoke_device, _revoke_since_now])
async def test_verify_access_token_refuses_each_revocation_in_one_round_trip(
    fake_redis, revoke: Callable[[Any, dict[str, Any]], Awaitable[None]]
) -> None:
    token, claims = _token()
    await revoke(fake_redis, claims)
    await _with_generation(fake_redis, claims)
    sent = _commands(fake_redis)

    with pytest.raises(AuthenticationError, match="revoked"):
        await access_tokens.verify_access_token(fake_redis, token, _SETTINGS)

    assert sent == ["MGET"]


@pytest.mark.parametrize("session_id", ["device-1", None])
async def test_verify_access_token_passes_a_live_token_in_one_round_trip(
    fake_redis, session_id: str | None
) -> None:
    token, claims = _token(session_id=session_id)
    # A cutoff from before this token was issued (an earlier sign-out) leaves it valid.
    await fake_redis.set(access_tokens.revoked_since_key(claims["sub"]), str(claims["iat"] - 60))
    await _with_generation(fake_redis, claims)
    sent = _commands(fake_redis)

    user_id = await access_tokens.verify_access_token(fake_redis, token, _SETTINGS)

    assert str(user_id) == claims["sub"]
    assert sent == ["MGET"]


async def test_verify_access_token_fails_closed_when_redis_is_down() -> None:
    token, _claims = _token()
    redis = redis_mock()
    redis.mget.side_effect = RedisConnectionError("down")

    with pytest.raises(RedisUnavailableError):
        await access_tokens.verify_access_token(redis, token, _SETTINGS)


async def test_verify_access_token_refuses_a_bad_signature_without_redis() -> None:
    token = access_tokens.create_access_token(uuid4(), Settings(jwt_secret="y" * 32))
    redis = redis_mock()

    with pytest.raises(AuthenticationError, match="Invalid"):
        await access_tokens.verify_access_token(redis, token, _SETTINGS)

    assert redis.mock_calls == []


async def test_check_access_starts_a_generation_for_a_user_without_one(fake_redis) -> None:
    """A missing key is never read as a generation a copy could be stored under."""
    token, claims = _token()
    sent = _commands(fake_redis)

    first = await access_tokens.check_access(fake_redis, token, _SETTINGS)
    second = await access_tokens.check_access(fake_redis, token, _SETTINGS)

    # The first check sets it (one more round trip); every later one only reads it.
    assert sent == ["MGET", "PIPELINE[SET,GET]", "MGET"]
    key = user_cache.generation_key(UUID(claims["sub"]))
    assert first.user_generation == second.user_generation == await fake_redis.get(key)
    assert await fake_redis.ttl(key) > 0
