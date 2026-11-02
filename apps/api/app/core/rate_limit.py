import logging

from redis.asyncio import Redis

from app.exceptions import RedisUnavailableError

logger = logging.getLogger(__name__)


async def allow_request(redis: Redis, key: str, *, limit: int, window_seconds: int) -> bool:
    """Increment a windowed counter; expire on first hit.

    INCR and EXPIRE run in one pipeline so a crash between them cannot leave a
    counter key with no TTL (permanent rate-limit for that bucket).

    Requires Redis ≥ 7 for ``EXPIRE … NX`` (set TTL only when missing). Upstash
    and current Fly Redis satisfy this; without NX every hit would refresh the
    window and weaken the limit.
    """
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        count, _ = await pipe.execute()
    return int(count) <= limit


async def allow_request_unless_down(
    redis: Redis, key: str, *, limit: int, window_seconds: int
) -> bool:
    """Like ``allow_request``, but a Redis error raises ``RedisUnavailableError`` (fail closed).

    Nothing gets through while the counter cannot be read: an outage must not silently
    remove a limit. ``False`` is a real limit hit, which the caller answers 429; the
    outage reaches the client as 503 unavailable + Retry-After 5 (``core/unavailable.py``),
    or as the chat socket's ``unavailable`` frame. Every limit answered an outage as its
    own 429: the phone took it for "too many" (sign-in, scans, voice, memory edits, live
    talk's minutes) and never checked its connection, which it does after a 503.
    """
    try:
        return await allow_request(redis, key, limit=limit, window_seconds=window_seconds)
    except Exception as exc:
        logger.warning("Rate limit check failed; failing closed key=%s", key, exc_info=True)
        raise RedisUnavailableError() from exc
