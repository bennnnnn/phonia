from functools import lru_cache

import redis.asyncio as redis

from app.core.config import get_settings

# Request-path commands should fail fast. The jobs consumer uses a longer
# socket_timeout so XREADGROUP BLOCK (5s) does not race the socket deadline.
_REQUEST_SOCKET_TIMEOUT_S = 5.0
_JOBS_SOCKET_TIMEOUT_S = 15.0


def _connect(socket_timeout: float, max_connections: int) -> redis.Redis:
    """One client (and its connection pool) per process and purpose.

    Fail fast on transient Upstash/network blips instead of hanging the
    request path: a 5s connect timeout + a command timeout covers quota, job
    enqueue, rate limits, and locks. health_check_interval keeps idle pooled
    connections from going stale behind a network flap.

    The pool is bounded (``max_connections``): redis-py's default opened one
    connection per concurrent command, so a burst could pass Upstash's
    per-plan connection limit. A command that finds every connection busy
    waits up to ``redis_pool_timeout_seconds`` for one, then fails with
    ``redis.exceptions.ConnectionError("No connection available.")``, which
    callers already treat as Redis being down (limiters fail closed).
    """
    settings = get_settings()
    pool = redis.BlockingConnectionPool.from_url(
        settings.redis_url,
        max_connections=max(1, max_connections),
        timeout=settings.redis_pool_timeout_seconds,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=socket_timeout,
        health_check_interval=30,
    )
    client = redis.Redis(connection_pool=pool)
    # As ``Redis.from_url`` does: closing the client closes the pool it owns.
    client.auto_close_connection_pool = True
    return client


@lru_cache
def get_redis_client() -> redis.Redis:
    return _connect(_REQUEST_SOCKET_TIMEOUT_S, get_settings().redis_max_connections)


@lru_cache
def get_jobs_redis_client() -> redis.Redis:
    """Redis client for the jobs worker loop (long-poll XREADGROUP)."""
    return _connect(_JOBS_SOCKET_TIMEOUT_S, get_settings().redis_jobs_max_connections)
