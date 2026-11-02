"""Token-based Redis locks for periodic schedulers and turn serialization.

``SET key token NX EX`` + compare-and-delete / compare-and-expire so a slow
holder that outlives its TTL cannot delete or refresh a lock owned by a
later instance. Prefers Lua (atomic); falls back to GET+compare for clients
that lack ``EVAL`` (e.g. some fakeredis setups in tests).

A release that cannot reach Redis is logged and left to the TTL: no caller can
do better, and raising from a ``finally`` turned finished work into a failure.
"""

from __future__ import annotations

import logging
import secrets
from typing import Final

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

logger = logging.getLogger(__name__)

_RELEASE_LUA: Final[str] = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

_REFRESH_LUA: Final[str] = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], tonumber(ARGV[2]))
end
return 0
"""


async def acquire_lock(redis: Redis, key: str, ttl_seconds: int) -> str | None:
    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl_seconds)
    return token if acquired else None


async def release_lock(redis: Redis, key: str, token: str) -> None:
    """Delete ``key`` when ``token`` still owns it; on a Redis error the TTL frees it."""
    try:
        try:
            await redis.eval(_RELEASE_LUA, 1, key, token)
        except ResponseError:
            if await redis.get(key) == token:
                await redis.delete(key)
    except (RedisError, OSError) as exc:
        logger.warning("Lock release failed; %s expires on its TTL: %r", key, exc)


async def refresh_lock(redis: Redis, key: str, token: str, ttl_seconds: int) -> bool:
    """Extend TTL only when ``token`` still owns the key."""
    try:
        result = await redis.eval(_REFRESH_LUA, 1, key, token, str(ttl_seconds))
        return bool(result)
    except ResponseError:
        if await redis.get(key) == token:
            await redis.expire(key, ttl_seconds)
            return True
        return False
