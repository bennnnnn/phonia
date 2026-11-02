"""Live talk spend follows reserved time, and a session's saves follow it too."""

import math
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.services.quota import live_talk
from app.services.quota.spend import LIVE_TALK_SPEND_USD_PER_MINUTE, live_talk_spend_usd

_MINT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
_MINT_DAY = _MINT.date()


class _Clock(datetime):
    """``datetime`` whose ``now`` the test moves (live talk reads it at mint and end)."""

    current = _MINT

    @classmethod
    def now(cls, tz=None):
        return cls.current


@pytest.fixture
def clock(monkeypatch):
    _Clock.current = _MINT
    monkeypatch.setattr(live_talk, "datetime", _Clock)
    return _Clock


def _micro(seconds: int) -> int:
    return math.ceil(round(seconds * LIVE_TALK_SPEND_USD_PER_MINUTE / 60 * 1_000_000, 6))


async def _spent(fake_redis, day: date = _MINT_DAY) -> int:
    return int(await fake_redis.get(f"spend_musd:{day.isoformat()}") or 0)


@pytest.mark.parametrize("seconds", [60, 137, 900])
def test_live_talk_spend_usd_is_priced_per_minute(seconds: int) -> None:
    assert live_talk_spend_usd(seconds) == pytest.approx(
        seconds / 60 * LIVE_TALK_SPEND_USD_PER_MINUTE
    )
    assert live_talk_spend_usd(-5) == 0


@pytest.mark.parametrize(
    "reserved, budget",
    [(60, 12), (61, 13), (300, 60), (900, 180), (1, 12)],
)
def test_live_talk_save_budget_follows_reserved_time(reserved: int, budget: int) -> None:
    assert live_talk.live_talk_save_budget(reserved) == budget


@pytest.mark.parametrize("reserved", [60, 900])
async def test_record_live_talk_reservation_charges_reserved_minutes(
    fake_redis, clock, reserved: int
) -> None:
    await live_talk.record_live_talk_reservation(
        fake_redis, uuid4(), "call-1", reserved_seconds=reserved
    )

    assert await _spent(fake_redis) == _micro(reserved)


@pytest.mark.parametrize(
    "elapsed, charged",
    [
        (0, 0),
        (120, 120),
        (899, 899),
        (5_000, 900),  # never past the reservation
    ],
)
async def test_settle_live_talk_session_gives_back_unused_spend(
    fake_redis, clock, elapsed: int, charged: int
) -> None:
    user_id = uuid4()
    await live_talk.record_live_talk_reservation(
        fake_redis, user_id, "call-1", reserved_seconds=900
    )
    clock.current = _MINT + timedelta(seconds=elapsed)

    assert await live_talk.settle_live_talk_session(fake_redis, user_id, "call-1") == charged
    left = await _spent(fake_redis)
    assert _micro(charged) <= left <= _micro(charged) + 1
    # A second report changes nothing.
    assert await live_talk.settle_live_talk_session(fake_redis, user_id, "call-1") is None
    assert await _spent(fake_redis) == left


async def test_settle_after_midnight_gives_back_to_the_mint_day(fake_redis, clock) -> None:
    user_id = uuid4()
    clock.current = datetime(2026, 10, 16, 23, 59, tzinfo=UTC)
    await live_talk.record_live_talk_reservation(
        fake_redis, user_id, "call-1", reserved_seconds=900
    )
    clock.current = datetime(2026, 10, 17, 0, 1, tzinfo=UTC)

    await live_talk.settle_live_talk_session(fake_redis, user_id, "call-1")

    assert _micro(120) <= await _spent(fake_redis, date(2026, 10, 16)) <= _micro(120) + 1
    assert await _spent(fake_redis, date(2026, 10, 17)) == 0


async def test_a_session_never_reported_keeps_its_whole_spend(fake_redis, clock) -> None:
    await live_talk.record_live_talk_reservation(
        fake_redis, uuid4(), "call-1", reserved_seconds=900
    )

    assert await _spent(fake_redis) == _micro(900)


@pytest.mark.parametrize("reserved", [60, 300])
async def test_take_live_talk_save_stops_at_the_session_budget(
    fake_redis, clock, reserved: int
) -> None:
    user_id = uuid4()
    await live_talk.record_live_talk_reservation(
        fake_redis, user_id, "call-1", reserved_seconds=reserved
    )
    budget = live_talk.live_talk_save_budget(reserved)

    taken = [
        await live_talk.take_live_talk_save(fake_redis, user_id, "call-1") for _ in range(budget)
    ]

    assert all(taken)
    assert await live_talk.take_live_talk_save(fake_redis, user_id, "call-1") is False
    assert await fake_redis.ttl(f"livetalk_saves:{user_id}:call-1") > 0


@pytest.mark.parametrize("session_id", ["never-minted", "", "  "])
async def test_take_live_talk_save_refuses_a_session_without_saves(
    fake_redis, session_id: str
) -> None:
    user_id = uuid4()

    assert await live_talk.take_live_talk_save(fake_redis, user_id, session_id) is False
    assert await fake_redis.keys("livetalk_saves:*") == []
