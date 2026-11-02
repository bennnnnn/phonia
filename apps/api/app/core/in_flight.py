"""Cap how many of one user's requests of a kind run at once (Redis, every machine).

A sorted set of open requests scored by start time: an entry older than the TTL
is a request that can no longer be running (a crash, a killed machine) and ages
out on the next call, so a lost release never locks the user out. A Redis error
fails closed (``RedisUnavailableError``, answered 503), like the rate limits.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.exceptions import RedisUnavailableError

logger = logging.getLogger(__name__)


class InFlightBusyError(Exception):
    """The user already has the most requests of this kind open at once."""


@asynccontextmanager
async def in_flight_slot(
    redis: Redis, key: str, *, limit: int, ttl_seconds: int
) -> AsyncIterator[None]:
    """Hold one of *key*'s *limit* slots for the block, or raise ``InFlightBusyError``.

    A *limit* of 0 or less disables the cap (nothing is written)."""
    if limit <= 0:
        yield
        return
    member = uuid.uuid4().hex
    now = time.time()
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", now - ttl_seconds)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, ttl_seconds)
            _, _, open_requests, _ = await pipe.execute()
    except Exception as exc:
        logger.warning("In-flight slot check failed; failing closed key=%s", key, exc_info=True)
        raise RedisUnavailableError() from exc
    try:
        if int(open_requests) > limit:
            raise InFlightBusyError
        yield
    finally:
        try:
            await redis.zrem(key, member)
        except Exception:
            # The TTL frees it: a lost release only holds a slot until then.
            logger.info("In-flight slot release failed key=%s", key, exc_info=True)
