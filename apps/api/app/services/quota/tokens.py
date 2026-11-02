"""The daily token budget: reserve before a turn, settle after, heal from the DB."""

import logging
from datetime import date

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError, WatchError

from app.core.config import Settings
from app.core.redis_counters import incr_with_ttl
from app.exceptions import RedisUnavailableError
from app.models.orm import User
from app.modules.billing.entitlements import allowance
from app.services.quota.counters import (
    DAILY_TTL,
    daily_key,
    floor_counter,
    raise_counter,
    refund_daily,
    utc_today,
)

logger = logging.getLogger(__name__)


def _usage_key(user_id: str, day: date) -> str:
    return daily_key("usage", user_id, day)


def _heal_flag_key(user_id: str, day: date) -> str:
    return daily_key("usage:heal", user_id, day)


def daily_limit_for_user(user: User, settings: Settings) -> int:
    return allowance(user, "daily_tokens", settings)


async def get_daily_usage(redis: Redis, user_id: str) -> int:
    key = _usage_key(user_id, utc_today())
    value = await redis.get(key)
    return int(value or 0)


async def has_daily_usage_key(redis: Redis, user_id: str, *, day: date | None = None) -> bool:
    """True when today's Redis usage counter already exists (seed is a no-op)."""
    return bool(await redis.exists(_usage_key(user_id, day or utc_today())))


async def seed_usage_if_missing(
    redis: Redis,
    user_id: str,
    db_total: int,
    *,
    day: date | None = None,
) -> None:
    """Self-heal the Redis daily counter after a flush/eviction.

    If the Redis key for today is absent, seed it with the DB-recorded total so
    quota enforcement resumes from the correct baseline instead of resetting to
    zero. Uses SET NX so concurrent calls (e.g. overlapping turns) can't
    double-count, and never overwrites a live counter. No-op when db_total <= 0.
    """
    if db_total <= 0:
        return
    key = _usage_key(user_id, day or utc_today())
    await redis.set(key, db_total, nx=True, ex=DAILY_TTL)


async def mark_usage_needs_heal(
    redis: Redis,
    user_id: str,
    *,
    day: date | None = None,
) -> None:
    """Remember that post-commit ``adjust_usage`` failed so the next turn can heal."""
    try:
        await redis.set(_heal_flag_key(user_id, day or utc_today()), "1", ex=DAILY_TTL)
    except RedisError:
        logger.warning("mark_usage_needs_heal failed user_id=%s", user_id, exc_info=True)


async def usage_needs_heal(
    redis: Redis,
    user_id: str,
    *,
    day: date | None = None,
) -> bool:
    try:
        return bool(await redis.exists(_heal_flag_key(user_id, day or utc_today())))
    except RedisError:
        logger.warning("usage_needs_heal failed user_id=%s", user_id, exc_info=True)
        return False


async def clear_usage_needs_heal(
    redis: Redis,
    user_id: str,
    *,
    day: date | None = None,
) -> None:
    try:
        await redis.delete(_heal_flag_key(user_id, day or utc_today()))
    except RedisError:
        logger.warning("clear_usage_needs_heal failed user_id=%s", user_id, exc_info=True)


async def heal_usage_drift(
    redis: Redis,
    user_id: str,
    db_total: int,
    *,
    day: date | None = None,
) -> None:
    """Heal Redis/DB drift when Redis holds a stale value lower than the DB.

    ``seed_usage_if_missing`` only seeds when the key is absent — if Redis
    holds a stale value *lower* than the DB total (repeated ``adjust_usage``
    failures, partial outages, manual key edits), seeding is skipped forever
    for that UTC day and the user can exceed daily limits. This compares the
    two and raises Redis to ``max(redis, db_total)`` when DB is ahead. Never
    lowers a live counter. Atomic via Lua; GET+SET fallback when EVAL is
    unavailable (some fakeredis setups).
    """
    if db_total <= 0:
        return
    key = _usage_key(user_id, day or utc_today())
    try:
        await raise_counter(redis, key, db_total, ttl=DAILY_TTL)
    except RedisError:
        logger.warning("heal_usage_drift failed user_id=%s", user_id, exc_info=True)
        raise


# Take what is left of today, up to ARGV[1], in one atomic step: the counter
# never holds more than the limit, so nothing is given back and no settle's
# clip at the limit can land between a take and a give-back.
_RESERVE_UP_TO_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local grant = math.min(tonumber(ARGV[1]), math.max(0, tonumber(ARGV[2]) - used))
if grant > 0 then
  redis.call('INCRBY', KEYS[1], grant)
  if redis.call('TTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
  end
end
return grant
"""
# Another write between the WATCH and the take: read again (fakeredis only).
_WATCHED_RESERVE_ATTEMPTS = 100


async def reserve_usage_up_to(
    redis: Redis,
    user_id: str,
    wanted: int,
    *,
    daily_limit: int,
) -> int:
    """Take ``wanted`` of today's tokens, or all that is left; 0 when none is.

    One Lua script reads today's total and takes ``min(wanted, limit - used)``
    in one round trip and one atomic step, so concurrent turns in different
    chats split what is left instead of each taking it, and a settle's clip at
    the limit can never land in the middle. Redis outages fail closed
    (``RedisUnavailableError``): never skip the reserve and allow unbounded
    generation.
    """
    if wanted <= 0 or daily_limit <= 0:
        return 0
    key = _usage_key(user_id, utc_today())
    try:
        try:
            granted = await redis.eval(
                _RESERVE_UP_TO_LUA, 1, key, str(wanted), str(daily_limit), str(DAILY_TTL)
            )
        except ResponseError:
            return await _reserve_up_to_watched(redis, key, wanted, daily_limit)
        return int(granted)
    except RedisError as exc:
        logger.warning("Quota reserve failed; Redis unavailable user_id=%s", user_id, exc_info=True)
        raise RedisUnavailableError() from exc


async def _reserve_up_to_watched(redis: Redis, key: str, wanted: int, daily_limit: int) -> int:
    """``_RESERVE_UP_TO_LUA`` where EVAL is unavailable (some fakeredis setups):
    WATCH the counter, then take the same share in one MULTI; a write in between
    makes the EXEC fail and the share is read again."""
    async with redis.pipeline(transaction=True) as pipe:
        for _attempt in range(_WATCHED_RESERVE_ATTEMPTS):
            try:
                await pipe.watch(key)
                grant = min(wanted, max(0, daily_limit - int(await pipe.get(key) or 0)))
                if grant <= 0:
                    return 0
                # redis-py's Pipeline.multi carries no annotations.
                pipe.multi()  # type: ignore[no-untyped-call]
                pipe.incrby(key, grant)
                pipe.expire(key, DAILY_TTL, nx=True)
                await pipe.execute()
                return grant
            except WatchError:
                continue
    raise RedisError("Quota reserve kept losing its WATCH")


async def refund_usage(redis: Redis, user_id: str, amount: int) -> None:
    if amount <= 0:
        return
    await refund_daily(redis, _usage_key(user_id, utc_today()), amount=amount)


async def adjust_usage(
    redis: Redis,
    user_id: str,
    reserved: int,
    actual: int,
    *,
    daily_limit: int | None = None,
) -> int:
    delta = actual - reserved
    if delta == 0:
        return await get_daily_usage(redis, user_id)
    return await record_usage(redis, user_id, delta, daily_limit=daily_limit)


async def record_usage(
    redis: Redis,
    user_id: str,
    tokens: int,
    *,
    daily_limit: int | None = None,
) -> int:
    key = _usage_key(user_id, utc_today())
    new_total = await incr_with_ttl(redis, key, tokens, DAILY_TTL)
    if new_total < 0:
        await floor_counter(redis, key)
        new_total = 0
    # Cap overshoot: a single turn whose actual usage exceeds the reserve
    # estimate can push the daily counter past the limit. Clip at daily_limit
    # so one turn can't blow the cap (the over-limit tokens are forfeit —
    # they were genuinely used, but the counter must not exceed the limit
    # or subsequent reserve_usage_up_to calls under-report remaining quota).
    if daily_limit is not None and new_total > daily_limit:
        await redis.set(key, daily_limit, ex=DAILY_TTL)
        new_total = daily_limit
    return new_total


async def reset_daily_usage(redis: Redis, user_id: str, day: date | None = None) -> None:
    """Clear Redis quota counter for a user/day (dev support)."""
    await redis.delete(_usage_key(user_id, day or utc_today()))
