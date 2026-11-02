from functools import lru_cache

import redis.asyncio as redis

from app.core.config import get_settings

# Request-path commands should fail fast. The jobs consumer uses a longer
# socket_timeout so XREADGROUP BLOCK (5s) does not race the socket deadline.
_REQUEST_SOCKET_TIMEOUT_S = 5.0
_JOBS_SOCKET_TIMEOUT_S = 15.0


def _connect(socket_timeout: float) -> redis.Redis:
    """One client (and its connection pool) per process and purpose.

    Fail fast on transient Upstash/network blips instead of hanging the
    request path: a 5s connect timeout + a command timeout covers quota, job
    enqueue, rate limits, and locks. health_check_interval keeps idle pooled
    connections from going stale behind a network flap. Pool size is
    redis-py's default (unbounded); docs/SCALING.md has what bounding it means.
    """
    return redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=socket_timeout,
        health_check_interval=30,
    )


@lru_cache
def get_redis_client() -> redis.Redis:
    return _connect(_REQUEST_SOCKET_TIMEOUT_S)


@lru_cache
def get_jobs_redis_client() -> redis.Redis:
    """Redis client for the jobs worker loop (long-poll XREADGROUP)."""
    return _connect(_JOBS_SOCKET_TIMEOUT_S)
