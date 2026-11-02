"""Live talk minutes (a monthly allowance per plan).

Live talk runs phone <-> OpenAI over WebRTC once the server mints a session,
so the server meters time at its own boundary: mint reserves a capped
session length out of this UTC month's seconds, and the end report settles
it to the time that actually passed (never refunding past the reservation).
A phone that never reports keeps the full reservation charged. The global
spend counter follows the same reservation (``LIVE_TALK_SPEND_USD_PER_MINUTE``),
and a session may save one turn per ``LIVE_TALK_SECONDS_PER_SAVE`` reserved
seconds: the phone posts the turns, so neither cost nor rows follow its count.
"""

import logging
import math
from datetime import UTC, date, datetime
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.redis_counters import incr_with_ttl
from app.exceptions import RedisUnavailableError
from app.models.orm import User
from app.modules.billing.entitlements import allowance
from app.services.quota.counters import refund_daily
from app.services.quota.spend import (
    live_talk_spend_usd,
    record_global_spend,
    release_global_spend,
)

logger = logging.getLogger(__name__)

# A month counter outlives its month long enough for a late settle, then expires.
MONTHLY_TTL = 60 * 60 * 24 * 40
# A reservation waits this long past its session for the phone's end report.
_LIVE_TALK_SETTLE_GRACE_SECONDS = 15 * 60
# A spoken exchange (the user, then the reply) takes longer than this, so a
# real call never runs out of saves; a script posting fake turns does.
LIVE_TALK_SECONDS_PER_SAVE = 5
_LIVE_TALK_MIN_SAVES = 12
# Saves per user per minute, across every session they hold.
LIVE_TALK_SAVES_PER_MINUTE = 20


def utc_month(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def next_month_start(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    if current.month == 12:
        return datetime(current.year + 1, 1, 1, tzinfo=UTC)
    return datetime(current.year, current.month + 1, 1, tzinfo=UTC)


def live_talk_month_key(user_id: UUID, month: str) -> str:
    return f"livetalk_sec:{user_id}:{month}"


def _live_talk_reservation_key(user_id: UUID, session_id: str) -> str:
    return f"livetalk_res:{user_id}:{session_id}"


def _live_talk_saves_key(user_id: UUID, session_id: str) -> str:
    return f"livetalk_saves:{user_id}:{session_id}"


def live_talk_save_budget(reserved_seconds: int) -> int:
    """Turns one session may save: proportional to its reserved time."""
    return max(_LIVE_TALK_MIN_SAVES, math.ceil(reserved_seconds / LIVE_TALK_SECONDS_PER_SAVE))


def live_talk_allowance_seconds(user: User, settings: Settings) -> int:
    return allowance(user, "monthly_live_talk_minutes", settings) * 60


async def live_talk_used_seconds(redis: Redis, user_id: UUID, *, month: str | None = None) -> int:
    value = await redis.get(live_talk_month_key(user_id, month or utc_month()))
    return max(0, int(value or 0))


async def reserve_live_talk_seconds(
    redis: Redis,
    user_id: UUID,
    *,
    allowance_seconds: int,
    max_session_seconds: int,
    min_session_seconds: int,
) -> int:
    """Take up to one session's seconds from this month. 0 = refused.

    INCRBY-then-trim keeps parallel mints honest: whoever lands past the
    allowance gives the excess back, and drops out entirely when what is left
    for it is under the minimum session.
    """
    if allowance_seconds <= 0 or max_session_seconds <= 0:
        return 0
    floor = max(1, min_session_seconds)
    key = live_talk_month_key(user_id, utc_month())
    try:
        used = int(await redis.get(key) or 0)
        grant = min(max_session_seconds, allowance_seconds - used)
        if grant < floor:
            return 0
        total = await incr_with_ttl(redis, key, grant, MONTHLY_TTL)
        overshoot = total - allowance_seconds
        if overshoot > 0:
            if grant - overshoot < floor:
                await redis.incrby(key, -grant)
                return 0
            await redis.incrby(key, -overshoot)
            grant -= overshoot
        return grant
    except RedisError as exc:
        logger.warning(
            "Live talk reserve failed; Redis unavailable user=%s", user_id, exc_info=True
        )
        raise RedisUnavailableError() from exc


def _utc_day(timestamp_ms: int) -> date:
    return datetime.fromtimestamp(timestamp_ms / 1000, UTC).date()


async def record_live_talk_reservation(
    redis: Redis, user_id: UUID, session_id: str, *, reserved_seconds: int
) -> None:
    """Remember a minted session: its seconds, its saves, and its spend."""
    started_ms = int(datetime.now(UTC).timestamp() * 1000)
    ttl = reserved_seconds + _LIVE_TALK_SETTLE_GRACE_SECONDS
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(
            _live_talk_reservation_key(user_id, session_id),
            f"{reserved_seconds}:{started_ms}:{utc_month()}",
            ex=ttl,
        )
        pipe.set(
            _live_talk_saves_key(user_id, session_id),
            live_talk_save_budget(reserved_seconds),
            ex=ttl,
        )
        await pipe.execute()
    try:
        spend = live_talk_spend_usd(reserved_seconds)
        await record_global_spend(redis, spend, day=_utc_day(started_ms))
    except Exception:
        logger.exception("Live talk spend not recorded user=%s", user_id)


async def take_live_talk_save(redis: Redis, user_id: UUID, session_id: str) -> bool:
    """Spend one of this session's saves. False when none is left or it has none."""
    key = _live_talk_saves_key(user_id, (session_id or "").strip())
    async with redis.pipeline(transaction=True) as pipe:
        pipe.exists(key)
        pipe.decr(key)
        existed, left = await pipe.execute()
    if not existed:
        # DECR made a key with no TTL; a session minted before saves has none.
        await redis.delete(key)
        return False
    return int(left) >= 0


async def release_live_talk_seconds(
    redis: Redis, user_id: UUID, *, seconds: int, month: str | None = None
) -> None:
    """Give back seconds that were reserved but never became a session."""
    if seconds <= 0:
        return
    await refund_daily(redis, live_talk_month_key(user_id, month or utc_month()), amount=seconds)


async def settle_live_talk_session(redis: Redis, user_id: UUID, session_id: str) -> int | None:
    """Charge the time that passed since mint; refund the rest of the reservation.

    Returns the seconds charged, or None when there is nothing to settle (an
    unknown session, a second report, or one that came after the grace window,
    which keeps the full reservation). The server's clock decides: a phone
    cannot shorten its own session by reporting less.
    """
    raw = await redis.getdel(_live_talk_reservation_key(user_id, (session_id or "").strip()))
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)
    try:
        reserved_text, started_text, month = text.split(":", 2)
        reserved = int(reserved_text)
        started_ms = int(started_text)
    except ValueError:
        return None
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    elapsed = math.ceil(max(0, now_ms - started_ms) / 1000)
    charged = min(reserved, elapsed)
    await release_live_talk_seconds(redis, user_id, seconds=reserved - charged, month=month)
    try:
        unused = live_talk_spend_usd(reserved - charged)
        await release_global_spend(redis, unused, day=_utc_day(started_ms))
    except Exception:
        logger.exception("Live talk spend not released user=%s", user_id)
    return charged
