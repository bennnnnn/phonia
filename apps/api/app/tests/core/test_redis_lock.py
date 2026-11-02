"""Token-safe Redis lock refresh / release."""

from __future__ import annotations

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.redis_lock import acquire_lock, refresh_lock, release_lock
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RedisConnectionError("Upstash blip"), RedisTimeoutError("slow"), TimeoutError("socket")],
)
async def test_release_lock_redis_error_leaves_the_lock_to_its_ttl(error, caplog):
    """A release runs in a ``finally``: raising there turned a finished, saved
    chat turn into an error frame. The TTL frees the key instead."""
    redis = redis_mock()
    redis.eval.side_effect = error

    await release_lock(redis, "chatprep:c", "tok")

    assert "expires on its TTL" in caplog.text


@pytest.mark.asyncio
async def test_refresh_lock_extends_only_for_owner(fake_redis):
    token = await acquire_lock(fake_redis, "k", 2)
    assert token is not None
    assert await refresh_lock(fake_redis, "k", token, 30) is True
    assert await refresh_lock(fake_redis, "k", "not-the-owner", 30) is False
    assert await fake_redis.get("k") == token


@pytest.mark.asyncio
async def test_stale_holder_cannot_release_new_owner(fake_redis):
    first = await acquire_lock(fake_redis, "k", 60)
    assert first is not None
    await fake_redis.delete("k")
    second = await acquire_lock(fake_redis, "k", 60)
    assert second is not None
    assert second != first
    await release_lock(fake_redis, "k", first)
    assert await fake_redis.get("k") == second
    await release_lock(fake_redis, "k", second)
    assert await fake_redis.get("k") is None


@pytest.mark.asyncio
async def test_memory_write_lock_stale_release_is_noop(fake_redis):
    from uuid import uuid4

    from app.modules.memory import locks

    # fake_redis shares the in-memory server every app client uses in tests.
    user_id = uuid4()
    first = await locks.acquire_memory_write_lock(user_id)
    assert first is not None
    await fake_redis.delete(f"memwrite:{user_id}")
    second = await locks.acquire_memory_write_lock(user_id)
    assert second is not None
    await locks.release_memory_write_lock(user_id, first)
    assert await fake_redis.get(f"memwrite:{user_id}") == second
    await locks.release_memory_write_lock(user_id, second)
    assert await fake_redis.get(f"memwrite:{user_id}") is None
