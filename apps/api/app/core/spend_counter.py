"""The global UTC-day spend counter: estimated provider dollars, in Redis.

Infrastructure, so the gateways can add what each model call cost; what the
cap stops and the fixed prices live in ``services/quota/spend.py``.

Integer micro-dollars (1e-6 USD) so INCRBY stays atomic, rounded UP so no
paid call ever records as free. The previous unit was 1e-3 USD with
round(): a typical $0.0002-0.0005 free-chat turn recorded 0, and the cap
never saw free-tier traffic. 0-limit settings are unlimited (dev/tests).
Redis errors fail closed, so nothing spends while the meter is blind, and say so:
``RedisUnavailableError``, never "the cap is reached".
"""

import logging
import math
from datetime import UTC, date, datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.redis_counters import incr_with_ttl
from app.exceptions import RedisUnavailableError

logger = logging.getLogger(__name__)

MICRO_USD_PER_USD = 1_000_000
# A day's counter outlives it long enough to read yesterday, then expires.
SPEND_KEY_TTL_SECONDS = 60 * 60 * 48


def spend_key(day: date | None = None) -> str:
    return f"spend_musd:{(day or datetime.now(UTC).date()).isoformat()}"


def usd_to_micro_usd(usd: float) -> int:
    if usd <= 0:
        return 0
    # round() first strips float noise (0.0004 * 1e6 = 400.00000000000006).
    return max(1, math.ceil(round(usd * MICRO_USD_PER_USD, 6)))


async def record_global_spend(redis: Redis, usd: float, *, day: date | None = None) -> int:
    """Add estimated dollars to the global spend counter (today's unless *day*).

    Returns that day's total in micro-USD.
    """
    amount = usd_to_micro_usd(usd)
    if amount <= 0:
        return await get_global_spend_micro_usd(redis)
    return await incr_with_ttl(redis, spend_key(day), amount, SPEND_KEY_TTL_SECONDS)


async def get_global_spend_micro_usd(redis: Redis) -> int:
    """Today's spend in micro-USD (every chat turn reads it).

    The pre-fix ``spend_mcents`` key lost its writer on 2026-10-15; its read missed
    every time after that and cost every model-calling path a command."""
    return int(await redis.get(spend_key()) or 0)


async def global_spend_exceeded(redis: Redis, settings: Settings) -> bool:
    """True when today's spend is at/over the cap (a cap of 0 is none).

    Redis down raises ``RedisUnavailableError`` (fail closed): a request answers 503
    unavailable, the chat its ``unavailable`` frame. It returned True, so an outage after
    sign-in said the day's cap was reached: pictures, scans, voice and memory edits
    "paused", chat "at capacity for today". Work nobody waits on skips on either.
    """
    if settings.daily_global_spend_usd <= 0:
        return False
    limit = usd_to_micro_usd(settings.daily_global_spend_usd)
    try:
        return await get_global_spend_micro_usd(redis) >= limit
    except RedisError as exc:
        logger.warning("Global spend check failed; failing closed as unavailable", exc_info=True)
        raise RedisUnavailableError() from exc
