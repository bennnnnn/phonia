"""Per-user daily counters in Redis, and the table of per-feature daily caps."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.models.orm import User
from app.modules.billing.entitlements import Allowance, allowance
from app.services.quota.messages import (
    DOCUMENT_LIMIT_EXCEEDED_MESSAGE_FREE,
    DOCUMENT_LIMIT_EXCEEDED_MESSAGE_PAID,
    IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_FREE,
    IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_PAID,
    IMAGE_LIMIT_EXCEEDED_MESSAGE_FREE,
    IMAGE_LIMIT_EXCEEDED_MESSAGE_PAID,
    IMAGE_SEARCH_LIMIT_EXCEEDED_MESSAGE_FREE,
    IMAGE_SEARCH_LIMIT_EXCEEDED_MESSAGE_PAID,
    SPEECH_LIMIT_EXCEEDED_MESSAGE,
    SPEECH_TTS_LIMIT_EXCEEDED_MESSAGE,
    plan_message,
)

logger = logging.getLogger(__name__)


def _utc_date() -> date:
    return datetime.now(UTC).date()


# The day every daily counter is keyed by. Every reader goes through ``utc_today``,
# however it imported it, so a test that fixes this (``quota_clock``) fixes them all.
clock: Callable[[], date] = _utc_date


def utc_today() -> date:
    return clock()


def daily_key(prefix: str, owner: str | UUID, day: date | None = None) -> str:
    """Per-user, per-UTC-day counter key shared by every daily cap."""
    return f"{prefix}:{owner}:{(day or utc_today()).isoformat()}"


# Daily counters outlive their day by enough to read yesterday, then expire.
DAILY_TTL = 60 * 60 * 48

# Raise Redis to db_total only when missing or behind. Never lower a live counter.
_HEAL_USAGE_LUA = """
local db = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local cur = redis.call('GET', KEYS[1])
if not cur then
  redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ttl)
  return db
end
local n = tonumber(cur)
if n < db then
  redis.call('SET', KEYS[1], ARGV[1], 'EX', ttl)
  return db
end
return n
"""


# Lower a counter that still exists by ARGV[1], never below 0, keeping its TTL.
# A missing key (expired, or never reserved) stays missing.
_REFUND_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  return 0
end
if redis.call('DECRBY', KEYS[1], ARGV[1]) < 0 then
  redis.call('SET', KEYS[1], 0, 'KEEPTTL')
end
return 1
"""


# Floor the daily usage counter at 0 so a buggy double-refund can never drive it
# negative (which would grant the user free quota). Set on refund/record.
async def floor_counter(redis: Redis, key: str) -> None:
    """Clamp a counter to 0 without wiping its TTL (SET alone drops EXPIRE)."""
    await redis.set(key, 0, keepttl=True)


async def _reserve_daily_slot(redis: Redis, key: str, *, limit: int) -> bool:
    """Atomically take one slot from a per-day cap; roll back when over limit.

    INCR-then-rollback keeps parallel requests honest: the loser of a race
    lands over the limit and gives its slot back, so the cap can't be
    exceeded by concurrent calls. A limit of 0 (feature off / not entitled)
    always refuses. INCRBY and ``EXPIRE … NX`` run in one transaction, so no
    charge is left without a TTL (as in ``core/rate_limit.allow_request``).

    M10: Redis outages fail closed with ``RedisUnavailableError`` — same
    pattern as ``reserve_usage_up_to`` so speech/image/Tavily paths return 503
    instead of an opaque 500.
    """
    if limit <= 0:
        return False
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, 1)
            pipe.expire(key, DAILY_TTL, nx=True)
            new_total, _ = await pipe.execute()
        if new_total > limit:
            await redis.incrby(key, -1)
            return False
        return True
    except RedisError as exc:
        logger.warning("Daily slot reserve failed; Redis unavailable key=%s", key, exc_info=True)
        raise RedisUnavailableError() from exc


async def refund_daily(redis: Redis, key: str, *, amount: int = 1) -> None:
    """Give back reserved units, flooring at zero (double-refund safe).

    Only a counter that still exists is lowered: a refund never creates a key,
    so it can never leave one without a TTL. Atomic via Lua; EXISTS+INCRBY
    fallback when EVAL is unavailable (some fakeredis setups).
    """
    try:
        await redis.eval(_REFUND_LUA, 1, key, str(amount))
    except ResponseError:
        if not await redis.exists(key):
            return
        if await redis.incrby(key, -amount) < 0:
            await floor_counter(redis, key)


async def _raise_counter_cas(redis: Redis, key: str, floor: int, ttl: int) -> None:
    current = await redis.get(key)
    if current is None:
        await redis.set(key, floor, nx=True, ex=ttl)
        return
    if int(current) < floor:
        await redis.set(key, floor, ex=ttl)


async def raise_counter(redis: Redis, key: str, floor: int, *, ttl: int) -> None:
    """Raise a counter to *floor* when missing or behind; never lower it.

    Atomic via Lua; GET+SET fallback when EVAL is unavailable (some fakeredis
    setups).
    """
    try:
        await redis.eval(_HEAL_USAGE_LUA, 1, key, str(floor), str(ttl))
    except ResponseError:
        await _raise_counter_cas(redis, key, floor, ttl)


CounterName = Literal[
    "image_upload",
    "document_upload",
    "speech_transcription",
    "speech_tts",
    "tavily_search",
    "image_generation",
    "image_search",
]


@dataclass(frozen=True, kw_only=True)
class CounterSpec:
    """One daily cap: one slot per reserve under ``<prefix>:<user id>:<UTC day>``.

    ``allowance`` names the plan's cap (0 refuses without touching Redis).
    ``message`` is the (free, paid) copy for a refusal; None when a refusal is
    silent. ``refund`` is whether a failed request gets its slot back; False
    keeps a reserved slot spent.
    """

    prefix: str
    allowance: Allowance
    message: tuple[str, str] | None
    refund: bool


# Account delete carries every prefix here to a new account for the same
# sign-in (``carryover.read_carried_usage``).
COUNTERS: dict[CounterName, CounterSpec] = {
    # Vision/image inputs cost more than text and aren't well captured by the
    # text token reserve, so image uploads are capped per user per UTC day.
    "image_upload": CounterSpec(
        prefix="imgup",
        allowance="daily_image_uploads",
        message=(IMAGE_LIMIT_EXCEEDED_MESSAGE_FREE, IMAGE_LIMIT_EXCEEDED_MESSAGE_PAID),
        refund=True,
    ),
    # Documents are parsed on the API machine (and may be OCR'd); with no cap one
    # account could re-upload ten 10 MiB files a message, every message.
    "document_upload": CounterSpec(
        prefix="docup",
        allowance="daily_document_uploads",
        message=(DOCUMENT_LIMIT_EXCEEDED_MESSAGE_FREE, DOCUMENT_LIMIT_EXCEEDED_MESSAGE_PAID),
        refund=True,
    ),
    "speech_transcription": CounterSpec(
        prefix="speech",
        allowance="daily_speech_transcriptions",
        message=(SPEECH_LIMIT_EXCEEDED_MESSAGE, SPEECH_LIMIT_EXCEEDED_MESSAGE),
        refund=True,
    ),
    "speech_tts": CounterSpec(
        prefix="tts",
        allowance="daily_speech_tts",
        message=(SPEECH_TTS_LIMIT_EXCEEDED_MESSAGE, SPEECH_TTS_LIMIT_EXCEEDED_MESSAGE),
        refund=True,
    ),
    # Past the cap a turn searches DuckDuckGo instead; a reserved search stays spent.
    "tavily_search": CounterSpec(
        prefix="tavily",
        allowance="daily_web_searches",
        message=None,
        refund=False,
    ),
    "image_generation": CounterSpec(
        prefix="imggen",
        allowance="daily_image_generations",
        message=(
            IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_FREE,
            IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_PAID,
        ),
        refund=True,
    ),
    # Reference-photo lookup: every plan, per-plan cap.
    "image_search": CounterSpec(
        prefix="imgsearch",
        allowance="daily_image_searches",
        message=(
            IMAGE_SEARCH_LIMIT_EXCEEDED_MESSAGE_FREE,
            IMAGE_SEARCH_LIMIT_EXCEEDED_MESSAGE_PAID,
        ),
        refund=True,
    ),
}


def limit(counter: CounterName, user: User, settings: Settings) -> int:
    return allowance(user, COUNTERS[counter].allowance, settings)


async def reserve(
    counter: CounterName, redis: Redis, user: User, settings: Settings
) -> date | None:
    """Take one of today's *counter* slots for *user*.

    Returns the UTC day it was charged to, which a refund of this slot passes
    back, or None at the plan's cap.
    """
    day = utc_today()
    cap = limit(counter, user, settings)
    key = daily_key(COUNTERS[counter].prefix, user.id, day)
    return day if await _reserve_daily_slot(redis, key, limit=cap) else None


async def refund(
    counter: CounterName, redis: Redis, user_id: UUID, *, day: date | None = None
) -> None:
    """Give back a slot taken on *day* (a failed or cancelled request).

    A request refunding its own reservation passes the day ``reserve``
    returned, so a request that runs past UTC midnight gives the slot back to
    the day it took it from. Without *day* it is today's slot: for a later,
    separate refund, such as an upload cancelled while still pending. A day
    whose counter has expired is left alone.
    """
    spec = COUNTERS[counter]
    if not spec.refund:
        raise ValueError(f"{counter} slots are not refunded")
    await refund_daily(redis, daily_key(spec.prefix, user_id, day))


def limit_message(counter: CounterName, user: User) -> str:
    message = COUNTERS[counter].message
    if message is None:
        raise ValueError(f"{counter} refuses without a message")
    free, paid = message
    return plan_message(user, free=free, paid=paid)
