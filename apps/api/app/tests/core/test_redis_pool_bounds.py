"""Each Redis client's pool is bounded: a burst waits for a connection, never opens one per command.

redis-py's default pool is unbounded, so a burst of concurrent commands opened a
connection each and could pass the Upstash plan's connection limit. No command runs
here: building a client opens no connection.
"""

from __future__ import annotations

import pytest
import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.core import redis as core_redis
from app.core.config import Settings


@pytest.mark.parametrize(
    "client, setting",
    [
        (core_redis.get_redis_client, "redis_max_connections"),
        (core_redis.get_jobs_redis_client, "redis_jobs_max_connections"),
    ],
)
async def test_redis_clients_use_a_bounded_blocking_pool(real_redis, client, setting):
    settings = Settings()
    pool = client().connection_pool

    assert isinstance(pool, redis.BlockingConnectionPool)
    assert pool.max_connections == getattr(settings, setting)
    assert pool.timeout == settings.redis_pool_timeout_seconds
    assert pool.connection_kwargs["decode_responses"] is True
    await client().aclose()


def test_an_exhausted_pool_fails_as_redis_down_does():
    """``BlockingConnectionPool`` raises ConnectionError past its wait; every caller
    already handles a RedisError (limiters fail closed)."""
    assert issubclass(RedisConnectionError, RedisError)


def test_default_pool_bounds_cover_the_worker_slots():
    settings = Settings()
    # One blocked XREADGROUP plus a lease, claim or ack per running job.
    assert settings.redis_jobs_max_connections > settings.jobs_worker_concurrency
    assert settings.redis_max_connections > 0
