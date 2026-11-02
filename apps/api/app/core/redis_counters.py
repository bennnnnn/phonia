"""Counters with an expiry, written in one transaction.

INCRBY followed by a separate EXPIRE left a dated key with no TTL whenever the
process crashed or the task was cancelled between the two, and such keys
outlived their day forever. ``EXPIRE … NX`` in the same MULTI keeps the first
TTL (a later increment never extends it), as ``core/rate_limit`` and the quota
slots already did.
"""

from __future__ import annotations

from redis.asyncio import Redis


async def incr_with_ttl(redis: Redis, key: str, amount: int, ttl_seconds: int) -> int:
    """Add ``amount`` to ``key``; a new key expires after ``ttl_seconds``. Returns the total."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incrby(key, amount)
        pipe.expire(key, ttl_seconds, nx=True)
        total, _ = await pipe.execute()
    return int(total)


async def hincr_with_ttl(redis: Redis, key: str, field: str, amount: int, ttl_seconds: int) -> int:
    """Add ``amount`` to one hash field; a new hash expires after ``ttl_seconds``."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hincrby(key, field, amount)
        pipe.expire(key, ttl_seconds, nx=True)
        total, _ = await pipe.execute()
    return int(total)
