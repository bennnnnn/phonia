"""Carry-over to a new account for the same sign-in or email address.

Counters are keyed by user id, so deleting an account and signing up again
with the same Google/Apple login, or on the same address, would start every cap
from zero. Account delete reads today's counters; the new account's counters are
raised to them (modules/account/quota_carryover.py).
"""

from uuid import UUID

from pydantic import BaseModel, NonNegativeInt
from redis.asyncio import Redis

from app.services.quota.counters import COUNTERS, DAILY_TTL, daily_key, raise_counter, utc_today

# The token budget's prefix, then every per-feature daily cap's.
DAILY_COUNTER_PREFIXES: tuple[str, ...] = ("usage", *(spec.prefix for spec in COUNTERS.values()))


class CarriedUsage(BaseModel):
    """One account's used counters for one UTC day."""

    day: str
    daily: dict[str, NonNegativeInt] = {}

    def is_empty(self) -> bool:
        return not any(self.daily.values())


def _counter_value(raw: object) -> int:
    try:
        return max(0, int(str(raw))) if raw is not None else 0
    except ValueError:
        return 0


async def read_carried_usage(redis: Redis, user_id: UUID) -> CarriedUsage:
    """Today's daily counters for *user_id*."""
    day = utc_today()
    keys = [daily_key(prefix, user_id, day) for prefix in DAILY_COUNTER_PREFIXES]
    values = [_counter_value(raw) for raw in await redis.mget(keys)]
    daily = {
        prefix: used
        for prefix, used in zip(DAILY_COUNTER_PREFIXES, values, strict=True)
        if used > 0
    }
    return CarriedUsage(day=day.isoformat(), daily=daily)


async def apply_carried_usage(redis: Redis, user_id: UUID, carried: CarriedUsage) -> None:
    """Raise *user_id*'s counters to what was carried: max(existing, carried).

    Only on the same UTC day; anything older has already reset. Raise-only, like
    the DB usage heal, so neither can lower the other.
    """
    day = utc_today()
    if carried.day != day.isoformat():
        return
    for prefix, used in carried.daily.items():
        if prefix in DAILY_COUNTER_PREFIXES and used > 0:
            await raise_counter(redis, daily_key(prefix, user_id, day), used, ttl=DAILY_TTL)
