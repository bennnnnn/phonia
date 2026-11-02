"""Per-user cache generations in Redis.

A cache key that folds in the user's current generation goes unreachable the
moment the generation changes, so invalidation needs no SCAN. The generation
used to be an INCR counter with no TTL: one key per user, kept forever, even
after the account was deleted.

Now each bump stores a fresh random value with a TTL. Random rather than
INCR, so a key that expired and starts over can never land on a generation an
older cache entry was written under. The TTL only has to outlast the caches
that fold it in (minutes); a reader that finds no key uses generation "0",
which was last current before the first bump, at least a TTL ago.

A key can also be lost early (eviction, a flush, a failover, a hand-run DEL),
and then "0" can name entries written before the last bump. A cache that must
never serve those (the user rows, ``core/user_cache``) reads with
``ensure_generation`` instead: a missing key gets a fresh random value first.
"""

from __future__ import annotations

import secrets

from redis.asyncio import Redis

GENERATION_TTL_SECONDS = 30 * 24 * 60 * 60


async def bump_generation(redis: Redis, key: str) -> str:
    """Store and return a fresh generation for ``key``."""
    generation = secrets.token_hex(8)
    await redis.set(key, generation, ex=GENERATION_TTL_SECONDS)
    return generation


async def ensure_generation(redis: Redis, key: str) -> str:
    """``key``'s generation; a missing key first gets a fresh one (SET NX).

    One round trip. Two readers that both find the key missing agree: the
    second SET NX does nothing and both read the first one's value.
    """
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(key, secrets.token_hex(8), nx=True, ex=GENERATION_TTL_SECONDS)
        pipe.get(key)
        _created, current = await pipe.execute()
    return current.decode() if isinstance(current, bytes) else str(current)
