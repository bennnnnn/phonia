from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.modules.billing.entitlements import setting_name
from app.services import quota as quota_service
from app.services.quota import counters
from app.services.quota import tokens as quota_tokens
from app.services.quota.tokens import _usage_key
from app.tests.fakes import redis_mock

# Every read of today, here and in the quota code, sees one fixed day (quota_clock).
pytestmark = pytest.mark.usefixtures("quota_clock")


@pytest.fixture
def settings() -> Settings:
    return Settings(daily_token_limit=100_000, daily_token_limit_pro=500_000)


def _pro_user() -> MagicMock:
    user = MagicMock()
    user.plan = "pro"
    return user


def _free_user() -> MagicMock:
    user = MagicMock()
    user.plan = "free"
    return user


def _plus_user() -> MagicMock:
    user = MagicMock()
    user.plan = "plus"
    return user


def test_daily_limit_for_user(settings):
    assert quota_service.daily_limit_for_user(_free_user(), settings) == 100_000
    assert quota_service.daily_limit_for_user(_pro_user(), settings) == 500_000


def test_quota_exceeded_message(settings):
    """Free is told it can upgrade; paid plans are not. Plan names stay in the app."""
    assert "Upgrade" in quota_service.quota_exceeded_message(_free_user())
    for user in (_plus_user(), _pro_user()):
        assert "Upgrade" not in quota_service.quota_exceeded_message(user)
    for user in (_free_user(), _plus_user(), _pro_user()):
        assert "Pro" not in quota_service.quota_exceeded_message(user)


@pytest.mark.parametrize(
    "plan, tokens, stt, tts, images",
    [("free", 100_000, 0, 0, 3), ("plus", 500_000, 200, 100, 10), ("pro", 500_000, 200, 100, 15)],
)
def test_per_plan_daily_caps(plan, tokens, stt, tts, images):
    user = MagicMock()
    user.plan = plan
    # The built-in defaults, not a developer's .env overrides.
    settings = Settings(_env_file=None)
    assert quota_service.daily_limit_for_user(user, settings) == tokens
    assert counters.limit("speech_transcription", user, settings) == stt
    assert counters.limit("speech_tts", user, settings) == tts
    assert counters.limit("image_generation", user, settings) == images


@pytest.mark.parametrize(
    "used, requested, reserved",
    [
        (0, 1000, 1000),
        (99_000, 2000, 1000),  # what is left
        (100_000, 1, 0),
        (100_500, 1000, 0),  # over (the limit fell with a downgrade): nothing, no charge
    ],
)
@pytest.mark.asyncio
async def test_quota_enforced(fake_redis, settings, used, requested, reserved):
    key = _usage_key("u1", quota_service.utc_today())
    if used:
        await fake_redis.set(key, used)
    limit = quota_service.daily_limit_for_user(_free_user(), settings)
    result = await quota_service.reserve_usage_up_to(fake_redis, "u1", requested, daily_limit=limit)
    assert result == reserved
    assert int(await fake_redis.get(key) or 0) == used + reserved


def _racing_settle(redis, settle) -> list[bool]:
    """Run ``settle`` once, right after the reserve reads today's total and before it takes."""
    ran: list[bool] = []
    pipeline = redis.pipeline

    def racing_pipeline(*args, **kwargs):
        pipe = pipeline(*args, **kwargs)
        read = pipe.get

        async def read_then_settle(*a, **k):
            value = await read(*a, **k)
            if not ran:
                ran.append(True)
                await settle()
            return value

        pipe.get = read_then_settle
        return pipe

    redis.pipeline = racing_pipeline
    return ran


@pytest.mark.asyncio
async def test_a_settle_landing_inside_a_reserve_is_never_lost(fake_redis):
    """Turn A held 20k of a full day and used 15k: its settle gives 5k back and clips at
    the limit. Turn B's reserve used to take, then give its excess back: a settle in
    between was clipped away, and the user kept 5k of quota that had been used."""
    key = _usage_key("u1", quota_service.utc_today())
    await fake_redis.set(key, 100_000, ex=counters.DAILY_TTL)

    async def a_settles():
        await quota_service.adjust_usage(fake_redis, "u1", 20_000, 15_000, daily_limit=100_000)

    ran = _racing_settle(fake_redis, a_settles)

    granted = await quota_service.reserve_usage_up_to(fake_redis, "u1", 10_000, daily_limit=100_000)

    assert ran == [True]
    # B ran before A's settle (nothing left: 0) or after it (5k): both add up.
    assert granted in (0, 5_000)
    assert int(await fake_redis.get(key)) == 95_000 + granted


@pytest.mark.asyncio
async def test_a_write_between_the_read_and_the_take_is_read_again(fake_redis):
    """Turn A's settle (it used 5k more than it held) lands after turn B read 10k of
    room: B takes the 5k now left, never 10k past the limit."""
    key = _usage_key("u1", quota_service.utc_today())
    await fake_redis.set(key, 90_000, ex=counters.DAILY_TTL)

    async def a_settles():
        await quota_service.adjust_usage(fake_redis, "u1", 20_000, 25_000, daily_limit=100_000)

    ran = _racing_settle(fake_redis, a_settles)

    granted = await quota_service.reserve_usage_up_to(fake_redis, "u1", 10_000, daily_limit=100_000)

    assert ran == [True]
    assert granted == 5_000
    assert int(await fake_redis.get(key)) == 100_000


@pytest.mark.asyncio
async def test_a_reserve_that_never_wins_its_watch_fails_closed(fake_redis, monkeypatch):
    key = _usage_key("u1", quota_service.utc_today())
    await fake_redis.set(key, 0, ex=counters.DAILY_TTL)
    monkeypatch.setattr(quota_tokens, "_WATCHED_RESERVE_ATTEMPTS", 3)
    pipeline = fake_redis.pipeline

    def always_raced(*args, **kwargs):
        pipe = pipeline(*args, **kwargs)
        read = pipe.get

        async def read_then_write(*a, **k):
            value = await read(*a, **k)
            await fake_redis.incrby(key, 1)
            return value

        pipe.get = read_then_write
        return pipe

    fake_redis.pipeline = always_raced

    with pytest.raises(RedisUnavailableError):
        await quota_service.reserve_usage_up_to(fake_redis, "u1", 10, daily_limit=100)
    assert int(await fake_redis.get(key)) == 3  # only the racing writes


@pytest.mark.asyncio
async def test_reserve_usage_up_to_sets_the_ttl_once_and_keeps_it(fake_redis):
    key = _usage_key("u1", quota_service.utc_today())
    assert await quota_service.reserve_usage_up_to(fake_redis, "u1", 10, daily_limit=100) == 10
    assert 0 < await fake_redis.ttl(key) <= counters.DAILY_TTL

    await fake_redis.expire(key, 60)
    assert await quota_service.reserve_usage_up_to(fake_redis, "u1", 10, daily_limit=100) == 10
    assert await fake_redis.ttl(key) <= 60


@pytest.mark.parametrize("turns", [2, 30])
@pytest.mark.asyncio
async def test_reserve_usage_up_to_concurrent_turns_split_what_is_left(fake_redis, turns):
    import asyncio

    key = _usage_key("u1", quota_service.utc_today())
    await fake_redis.set(key, 9_000)

    taken = await asyncio.gather(
        *(
            quota_service.reserve_usage_up_to(fake_redis, "u1", 700, daily_limit=10_000)
            for _ in range(turns)
        )
    )

    assert sum(taken) == min(1_000, 700 * turns)
    assert int(await fake_redis.get(key)) == 9_000 + sum(taken)


@pytest.mark.asyncio
async def test_record_usage_increments(fake_redis):
    total = await quota_tokens.record_usage(fake_redis, "u1", 500)
    assert total == 500
    total = await quota_tokens.record_usage(fake_redis, "u1", 200)
    assert total == 700


@pytest.mark.asyncio
async def test_record_usage_caps_overshoot_at_daily_limit(fake_redis):
    """A turn whose actual > reserved delta must not push the daily counter
    past the limit — otherwise subsequent reserve_usage_up_to calls under-report
    remaining quota and the user keeps getting turns past the cap."""
    await fake_redis.set(_usage_key("u1", quota_service.utc_today()), 99_500)
    total = await quota_tokens.record_usage(fake_redis, "u1", 2000, daily_limit=100_000)
    assert total == 100_000  # clipped, not 101_500
    assert await quota_service.get_daily_usage(fake_redis, "u1") == 100_000


@pytest.mark.asyncio
async def test_adjust_usage_caps_overshoot(fake_redis):
    await fake_redis.set(_usage_key("u1", quota_service.utc_today()), 99_000)
    # reserved 1000, actual 5000 → delta +4000 would push to 103_000; clip.
    total = await quota_service.adjust_usage(
        fake_redis, "u1", reserved=1000, actual=5000, daily_limit=100_000
    )
    assert total == 100_000


@pytest.mark.asyncio
async def test_record_usage_without_limit_does_not_cap(fake_redis):
    """Backward compat: callers that don't pass daily_limit get the raw total
    (no clipping) — existing callers (e.g. admin tooling) aren't affected."""
    await fake_redis.set(_usage_key("u1", quota_service.utc_today()), 99_500)
    total = await quota_tokens.record_usage(fake_redis, "u1", 2000)
    assert total == 101_500


@pytest.mark.asyncio
async def test_reserve_and_adjust(fake_redis, settings):
    limit = quota_service.daily_limit_for_user(_free_user(), settings)
    reserved = 1000
    assert (
        await quota_service.reserve_usage_up_to(fake_redis, "u1", reserved, daily_limit=limit)
        == reserved
    )
    await quota_service.adjust_usage(fake_redis, "u1", reserved, 700)
    assert await quota_service.get_daily_usage(fake_redis, "u1") == 700


@pytest.mark.asyncio
async def test_refund_usage(fake_redis):
    await quota_tokens.record_usage(fake_redis, "u1", 500)
    await quota_service.refund_usage(fake_redis, "u1", 200)
    assert await quota_service.get_daily_usage(fake_redis, "u1") == 300


@pytest.mark.asyncio
async def test_refund_usage_floor_preserves_ttl(fake_redis):
    await quota_tokens.record_usage(fake_redis, "u1", 50)
    key = _usage_key("u1", quota_service.utc_today())
    ttl_before = await fake_redis.ttl(key)
    assert ttl_before > 0
    await quota_service.refund_usage(fake_redis, "u1", 100)  # floors at 0
    assert await quota_service.get_daily_usage(fake_redis, "u1") == 0
    assert await fake_redis.ttl(key) == ttl_before


@pytest.mark.asyncio
async def test_has_daily_usage_key(fake_redis):
    assert await quota_service.has_daily_usage_key(fake_redis, "u1") is False
    await fake_redis.set("usage:u1:2026-01-01", 100)
    assert await quota_service.has_daily_usage_key(fake_redis, "u1", day=date(2026, 1, 1)) is True


@pytest.mark.asyncio
async def test_seed_usage_from_db_skips_db_when_redis_key_warm(fake_redis):
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.modules.chat.turn_settle import seed_usage_from_db

    session = AsyncMock()
    user_id = uuid4()
    # Redis already at 500 — skip Neon entirely (heal-on-every-turn was a
    # round-trip on the send path).
    await fake_redis.set(f"usage:{user_id}:{quota_service.utc_today().isoformat()}", 500)
    with (
        patch(
            "app.repositories.usage.get_total_for_date", AsyncMock(return_value=500)
        ) as get_total,
    ):
        await seed_usage_from_db(fake_redis, session, user_id)
        get_total.assert_not_awaited()
    # Redis unchanged (no drift)
    assert (
        int(await fake_redis.get(f"usage:{user_id}:{quota_service.utc_today().isoformat()}")) == 500
    )


@pytest.mark.asyncio
async def test_seed_usage_from_db_does_not_heal_warm_redis(fake_redis):
    """Warm Redis skips Neon even if the counter is below the DB total."""
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.modules.chat.turn_settle import seed_usage_from_db

    session = AsyncMock()
    user_id = uuid4()
    key = f"usage:{user_id}:{quota_service.utc_today().isoformat()}"
    await fake_redis.set(key, 200)
    with patch(
        "app.repositories.usage.get_total_for_date", AsyncMock(return_value=500)
    ) as get_total:
        await seed_usage_from_db(fake_redis, session, user_id)
    get_total.assert_not_awaited()
    assert int(await fake_redis.get(key)) == 200


@pytest.mark.asyncio
async def test_heal_usage_drift_raises_stale_redis_to_db_total(fake_redis):
    await fake_redis.set(f"usage:u1:{quota_service.utc_today().isoformat()}", 200)
    await quota_service.heal_usage_drift(fake_redis, "u1", 500)
    assert int(await fake_redis.get(f"usage:u1:{quota_service.utc_today().isoformat()}")) == 500


@pytest.mark.asyncio
async def test_heal_usage_drift_does_not_lower_live_redis(fake_redis):
    await fake_redis.set(f"usage:u1:{quota_service.utc_today().isoformat()}", 800)
    await quota_service.heal_usage_drift(fake_redis, "u1", 500)
    assert int(await fake_redis.get(f"usage:u1:{quota_service.utc_today().isoformat()}")) == 800


@pytest.mark.asyncio
async def test_seed_usage_from_db_heals_when_flag_set(fake_redis):
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.modules.chat.turn_settle import seed_usage_from_db

    session = AsyncMock()
    user_id = uuid4()
    key = f"usage:{user_id}:{quota_service.utc_today().isoformat()}"
    await fake_redis.set(key, 200)
    await quota_service.mark_usage_needs_heal(fake_redis, str(user_id))
    with patch(
        "app.repositories.usage.get_total_for_date", AsyncMock(return_value=500)
    ) as get_total:
        await seed_usage_from_db(fake_redis, session, user_id)
    get_total.assert_awaited_once()
    assert int(await fake_redis.get(key)) == 500
    assert await quota_service.usage_needs_heal(fake_redis, str(user_id)) is False


@pytest.mark.asyncio
async def test_seed_usage_if_missing_seeds_from_db_when_key_absent(fake_redis):
    """After a Redis flush the counter is gone; seeding restores the DB total."""
    day = quota_service.utc_today().isoformat()
    await quota_service.seed_usage_if_missing(fake_redis, "u1", 12_000)
    assert int(await fake_redis.get(f"usage:u1:{day}")) == 12_000


@pytest.mark.asyncio
async def test_seed_usage_if_missing_does_not_overwrite_live_counter(fake_redis):
    """SET NX must never overwrite a live (non-zero) counter — no double-count."""
    day = quota_service.utc_today().isoformat()
    await fake_redis.set(f"usage:u1:{day}", 3_000)
    await quota_service.seed_usage_if_missing(fake_redis, "u1", 12_000)
    # Live counter wins; the DB total is NOT applied.
    assert int(await fake_redis.get(f"usage:u1:{day}")) == 3_000


@pytest.mark.asyncio
async def test_seed_usage_if_missing_noop_when_db_total_zero(fake_redis):
    day = quota_service.utc_today().isoformat()
    await quota_service.seed_usage_if_missing(fake_redis, "u1", 0)
    assert await fake_redis.get(f"usage:u1:{day}") is None


# ── Per-feature daily counters ───────────────────────────────────────────────

# Counter -> its Redis key prefix and refund rule, named independently of the table.
_COUNTER_KEYS = [
    ("image_upload", "imgup"),
    ("speech_transcription", "speech"),
    ("speech_tts", "tts"),
    ("tavily_search", "tavily"),
    ("image_generation", "imggen"),
    ("image_search", "imgsearch"),
]
_REFUNDABLE = [pair for pair in _COUNTER_KEYS if pair[0] != "tavily_search"]


def _capped(counter, cap, plan="pro"):
    return Settings(**{setting_name(counters.COUNTERS[counter].allowance, plan): cap})


def _today_key(prefix, user_id):
    return f"{prefix}:{user_id}:{quota_service.utc_today().isoformat()}"


@pytest.mark.parametrize("counter, prefix", _COUNTER_KEYS)
@pytest.mark.asyncio
async def test_counter_reserve_stops_at_the_plan_cap(fake_redis, quota_clock, counter, prefix):
    user = _pro_user()
    user.id = uuid4()
    settings = _capped(counter, 2)
    # A reserve returns the day it charged, for a refund of that slot to pass back.
    assert await counters.reserve(counter, fake_redis, user, settings) == quota_clock.day
    assert await counters.reserve(counter, fake_redis, user, settings) == quota_clock.day
    assert await counters.reserve(counter, fake_redis, user, settings) is None
    key = f"{prefix}:{user.id}:2026-10-16"
    assert await fake_redis.get(key) == "2"
    assert await fake_redis.ttl(key) == 48 * 60 * 60


@pytest.mark.parametrize("counter, prefix", _COUNTER_KEYS)
@pytest.mark.parametrize("left_without_ttl", [None, "1"])
@pytest.mark.asyncio
async def test_counter_reserve_always_leaves_a_ttl(
    fake_redis, quota_clock, counter, prefix, left_without_ttl
):
    """INCR and EXPIRE are one transaction: no failed EXPIRE can leave a charge forever.

    The standalone EXPIRE a reserve used to send fails here, and a counter
    an older reserve left without a TTL gets one.
    """
    user = _pro_user()
    user.id = uuid4()
    key = f"{prefix}:{user.id}:2026-10-16"
    if left_without_ttl is not None:
        await fake_redis.set(key, left_without_ttl)
    fake_redis.expire = AsyncMock(side_effect=RedisConnectionError("blip"))
    assert await counters.reserve(counter, fake_redis, user, _capped(counter, 5)) == quota_clock.day
    assert await fake_redis.get(key) == str(int(left_without_ttl or 0) + 1)
    assert await fake_redis.ttl(key) == 48 * 60 * 60


@pytest.mark.parametrize("counter", ["speech_transcription", "speech_tts", "image_generation"])
@pytest.mark.asyncio
async def test_counter_reserve_refuses_a_plan_without_it(counter):
    user = _free_user()
    user.id = uuid4()
    redis = redis_mock()
    assert await counters.reserve(counter, redis, user, _capped(counter, 0, "free")) is None
    assert redis.mock_calls == []


@pytest.mark.parametrize("counter, prefix", _REFUNDABLE)
@pytest.mark.asyncio
async def test_counter_refund_gives_the_slot_back(fake_redis, counter, prefix):
    user = _pro_user()
    user.id = uuid4()
    settings = _capped(counter, 1)
    day = await counters.reserve(counter, fake_redis, user, settings)
    assert day
    await counters.refund(counter, fake_redis, user.id, day=day)
    assert await fake_redis.get(_today_key(prefix, user.id)) == "0"
    assert await counters.reserve(counter, fake_redis, user, settings)


@pytest.mark.parametrize("counter, prefix", _REFUNDABLE)
@pytest.mark.parametrize("next_day_uses", [0, 1])
@pytest.mark.asyncio
async def test_counter_refund_after_midnight_returns_the_slot_to_its_day(
    fake_redis, quota_clock, counter, prefix, next_day_uses
):
    """A request reserved at 23:59 that fails after midnight refunds the day it was charged.

    Refunding the next day instead gave a free use there (when it had uses)
    or created it at -1 and floored it to a 0 with no TTL (when it had none).
    """
    user = _pro_user()
    user.id = uuid4()
    settings = _capped(counter, 5)
    day = await counters.reserve(counter, fake_redis, user, settings)
    quota_clock.day = quota_clock.next_day
    for _ in range(next_day_uses):
        assert await counters.reserve(counter, fake_redis, user, settings)
    await counters.refund(counter, fake_redis, user.id, day=day)
    day_key, next_key = (f"{prefix}:{user.id}:2026-10-{n}" for n in (16, 17))
    assert await fake_redis.get(day_key) == "0"
    assert 0 < await fake_redis.ttl(day_key) <= 48 * 60 * 60
    assert await fake_redis.get(next_key) == (str(next_day_uses) if next_day_uses else None)


@pytest.mark.parametrize("counter, prefix", _REFUNDABLE)
@pytest.mark.parametrize(
    "reserves, expired, refunds, left",
    [
        (0, False, 2, None),  # a refund without its reserve creates nothing
        (1, True, 1, None),  # the day's counter expired: nothing to give back
        (1, False, 2, "0"),  # a double refund floors at 0
        (2, False, 1, "1"),
    ],
)
@pytest.mark.asyncio
async def test_counter_refund_only_lowers_a_live_counter(
    fake_redis, quota_clock, counter, prefix, reserves, expired, refunds, left
):
    user = _pro_user()
    user.id = uuid4()
    key = f"{prefix}:{user.id}:2026-10-16"
    for _ in range(reserves):
        assert await counters.reserve(counter, fake_redis, user, _capped(counter, 5))
    if expired:
        await fake_redis.delete(key)
    for _ in range(refunds):
        await counters.refund(counter, fake_redis, user.id, day=quota_clock.day)
    assert await fake_redis.get(key) == left
    if left is not None:
        assert 0 < await fake_redis.ttl(key) <= 48 * 60 * 60


@pytest.mark.parametrize(
    "refund",
    [
        lambda r, uid: counters.refund("speech_tts", r, uid),
        lambda r, uid: counters.refund("image_upload", r, uid),
        lambda r, uid: quota_service.refund_usage(r, str(uid), 50),
        lambda r, uid: quota_service.release_live_talk_seconds(r, uid, seconds=60),
    ],
    ids=["daily counter", "upload counter", "token budget", "live talk month"],
)
@pytest.mark.asyncio
async def test_no_refund_creates_a_counter(fake_redis, refund):
    """Each refund path leaves a missing counter missing, never a 0 with no TTL."""
    user_id = uuid4()
    await refund(fake_redis, user_id)
    await refund(fake_redis, user_id)
    assert await fake_redis.keys("*") == []


@pytest.mark.asyncio
async def test_counter_refund_is_one_script_when_redis_runs_lua():
    """Real Redis checks, lowers and floors in one EVAL; nothing else is sent."""
    redis = redis_mock()
    user_id = uuid4()
    await counters.refund("image_search", redis, user_id, day=date(2026, 10, 16))
    script, numkeys, key, amount = redis.eval.await_args.args
    assert (numkeys, key, amount) == (1, f"imgsearch:{user_id}:2026-10-16", "1")
    assert "EXISTS" in script and "KEEPTTL" in script
    assert [call[0] for call in redis.mock_calls] == ["eval"]


@pytest.mark.parametrize("counter, prefix", _REFUNDABLE)
@pytest.mark.asyncio
async def test_counter_refund_floor_keeps_the_ttl(fake_redis, counter, prefix):
    user_id = uuid4()
    key = _today_key(prefix, user_id)
    await fake_redis.set(key, 0, ex=600)
    await counters.refund(counter, fake_redis, user_id)
    assert await fake_redis.get(key) == "0"
    assert 0 < await fake_redis.ttl(key) <= 600


@pytest.mark.asyncio
async def test_tavily_searches_are_neither_refunded_nor_announced(fake_redis):
    """Past the cap a turn falls back to DuckDuckGo; a reserved search stays spent."""
    with pytest.raises(ValueError, match="not refunded"):
        await counters.refund("tavily_search", fake_redis, uuid4())
    with pytest.raises(ValueError, match="without a message"):
        counters.limit_message("tavily_search", _free_user())


@pytest.mark.parametrize(
    "counter, free_upgrades",
    [
        ("image_upload", True),
        ("speech_transcription", False),
        ("speech_tts", False),
        ("image_generation", True),
        ("image_search", True),
    ],
)
def test_counter_limit_message_offers_upgrade_only_on_free(counter, free_upgrades):
    free = counters.limit_message(counter, _free_user())
    assert ("Upgrade" in free) is free_upgrades
    for user in (_plus_user(), _pro_user()):
        paid = counters.limit_message(counter, user)
        assert "Upgrade" not in paid
        if not free_upgrades:
            assert paid == free


@pytest.mark.parametrize("counter, prefix", _COUNTER_KEYS)
@pytest.mark.asyncio
async def test_counter_reserve_fails_closed_when_redis_is_down(counter, prefix):
    pipe = MagicMock()
    pipe.execute = AsyncMock(side_effect=RedisConnectionError("down"))
    redis = MagicMock()
    redis.pipeline.return_value.__aenter__.return_value = pipe
    user = _pro_user()
    user.id = uuid4()
    with pytest.raises(RedisUnavailableError):
        await counters.reserve(counter, redis, user, _capped(counter, 5))
    redis.pipeline.assert_called_once_with(transaction=True)
    pipe.incrby.assert_called_once_with(_today_key(prefix, user.id), 1)
    pipe.expire.assert_called_once_with(_today_key(prefix, user.id), 48 * 60 * 60, nx=True)


# ── Live talk minutes ────────────────────────────────────────────────────────


def test_live_talk_allowance_is_monthly_minutes_per_plan():
    settings = Settings()
    assert quota_service.live_talk_allowance_seconds(_free_user(), settings) == 0
    assert quota_service.live_talk_allowance_seconds(_plus_user(), settings) == 0
    assert quota_service.live_talk_allowance_seconds(_pro_user(), settings) == 60 * 60


async def _reserve(redis, user_id, *, allowance=1000, max_session=600, min_session=60) -> int:
    return await quota_service.reserve_live_talk_seconds(
        redis,
        user_id,
        allowance_seconds=allowance,
        max_session_seconds=max_session,
        min_session_seconds=min_session,
    )


@pytest.mark.asyncio
async def test_live_talk_reserve_caps_a_session_and_stops_at_the_allowance(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    assert await _reserve(fake_redis, user_id) == 600
    assert await _reserve(fake_redis, user_id) == 400
    assert await _reserve(fake_redis, user_id) == 0
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == 1000


@pytest.mark.asyncio
async def test_live_talk_reserve_refuses_less_than_the_minimum_session(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    assert await _reserve(fake_redis, user_id, allowance=650) == 600
    assert await _reserve(fake_redis, user_id, allowance=650) == 0
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == 600


@pytest.mark.asyncio
async def test_live_talk_reserve_without_minutes_takes_nothing(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    assert await _reserve(fake_redis, user_id, allowance=0) == 0
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == 0


@pytest.mark.asyncio
async def test_parallel_live_talk_reserves_never_pass_the_allowance(fake_redis):
    """Two mints read the same balance; the one that lands past it gives back."""
    from uuid import uuid4

    user_id = uuid4()
    assert await _reserve(fake_redis, user_id) == 600

    class _StaleRead:
        """Answers GET with the balance before the first mint landed."""

        def __getattr__(self, name):
            return getattr(fake_redis, name)

        async def get(self, _key):
            return "0"

    assert await _reserve(_StaleRead(), user_id) == 400
    assert await _reserve(_StaleRead(), user_id) == 0
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == 1000


async def _reserve_started(redis, user_id, session_id, *, reserved, seconds_ago, month=None):
    from datetime import UTC, datetime

    started_ms = int(datetime.now(UTC).timestamp() * 1000) - seconds_ago * 1000
    month = month or quota_service.utc_month()
    await redis.incrby(f"livetalk_sec:{user_id}:{month}", reserved)
    await redis.set(f"livetalk_res:{user_id}:{session_id}", f"{reserved}:{started_ms}:{month}")


@pytest.mark.asyncio
async def test_live_talk_settle_charges_the_time_that_passed(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    await _reserve_started(fake_redis, user_id, "call-1", reserved=600, seconds_ago=90)
    charged = await quota_service.settle_live_talk_session(fake_redis, user_id, "call-1")
    assert charged is not None and 90 <= charged <= 92
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == charged


@pytest.mark.asyncio
async def test_live_talk_settle_never_refunds_past_the_reservation(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    await _reserve_started(fake_redis, user_id, "call-1", reserved=600, seconds_ago=5_000)
    assert await quota_service.settle_live_talk_session(fake_redis, user_id, "call-1") == 600
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == 600


@pytest.mark.asyncio
async def test_live_talk_settles_once_and_unreported_sessions_stay_charged(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    await _reserve_started(fake_redis, user_id, "call-1", reserved=600, seconds_ago=30)
    await _reserve_started(fake_redis, user_id, "call-2", reserved=300, seconds_ago=10)
    first = await quota_service.settle_live_talk_session(fake_redis, user_id, "call-1")
    assert first is not None
    assert await quota_service.settle_live_talk_session(fake_redis, user_id, "call-1") is None
    assert await quota_service.settle_live_talk_session(fake_redis, user_id, "unknown") is None
    # call-2 never reported its end: the full 300 seconds stay charged.
    assert await quota_service.live_talk_used_seconds(fake_redis, user_id) == first + 300


@pytest.mark.asyncio
async def test_live_talk_settle_refunds_the_month_it_was_reserved_in(fake_redis):
    from uuid import uuid4

    user_id = uuid4()
    await _reserve_started(
        fake_redis, user_id, "call-1", reserved=600, seconds_ago=60, month="2026-09"
    )
    await quota_service.settle_live_talk_session(fake_redis, user_id, "call-1")
    september = await quota_service.live_talk_used_seconds(fake_redis, user_id, month="2026-09")
    assert 60 <= september <= 62


def test_live_talk_minutes_renew_on_the_first_of_the_month():
    from datetime import UTC, datetime

    december = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    assert quota_service.next_month_start(december) == datetime(2027, 1, 1, tzinfo=UTC)
    assert quota_service.utc_month(december) == "2026-12"


@pytest.mark.asyncio
async def test_global_spend_unlimited_when_limit_zero(fake_redis):
    settings = Settings(daily_global_spend_usd=0)
    await quota_service.record_global_spend(fake_redis, 50.0)
    assert await quota_service.global_spend_exceeded(fake_redis, settings) is False


@pytest.mark.asyncio
async def test_global_spend_exceeded_after_recording(fake_redis):
    settings = Settings(daily_global_spend_usd=1.0)
    assert await quota_service.global_spend_exceeded(fake_redis, settings) is False
    await quota_service.record_global_spend(fake_redis, 0.4)
    assert await quota_service.global_spend_exceeded(fake_redis, settings) is False
    await quota_service.record_global_spend(fake_redis, 0.6)
    assert await quota_service.global_spend_exceeded(fake_redis, settings) is True


@pytest.mark.asyncio
async def test_global_spend_redis_error_fails_closed_as_unavailable():
    """Nothing spends while the meter is blind, and the outage is said as one: it returned
    True, the cap reached, so every gate answered its "paused" refusal."""
    settings = Settings(daily_global_spend_usd=10.0)

    class _Boom:
        async def get(self, _key: str) -> None:
            from redis.exceptions import RedisError

            raise RedisError("down")

    with pytest.raises(RedisUnavailableError):
        await quota_service.global_spend_exceeded(_Boom(), settings)
    # No cap, no read: an outage cannot stop what nothing limits.
    assert await quota_service.global_spend_exceeded(_Boom(), Settings()) is False


@pytest.mark.asyncio
async def test_record_voice_spend_counts_toward_global_cap(fake_redis):
    settings = Settings(daily_global_spend_usd=0.05)
    assert await quota_service.global_spend_exceeded(fake_redis, settings) is False
    await quota_service.record_voice_spend(fake_redis, 0.08)
    assert await quota_service.global_spend_exceeded(fake_redis, settings) is True


# ── Nothing to count, and Redis outages ──────────────────────────────────────


class _DownPipeline:
    """A MULTI that fails when it reaches Redis, as every command does here."""

    async def __aenter__(self) -> "_DownPipeline":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def __getattr__(self, _name: str) -> MagicMock:
        return MagicMock()

    async def execute(self) -> None:
        raise RedisConnectionError("down")


def _down_redis():
    redis = redis_mock()
    for name in ("get", "set", "exists", "delete", "incrby", "decrby", "expire", "eval"):
        getattr(redis, name).side_effect = RedisConnectionError("down")
    redis.pipeline = MagicMock(side_effect=lambda **_kwargs: _DownPipeline())
    return redis


@pytest.mark.parametrize(
    "call, expected",
    [
        (lambda r: quota_service.reserve_usage_up_to(r, "u1", 0, daily_limit=10), 0),
        (lambda r: quota_service.reserve_usage_up_to(r, "u1", 10, daily_limit=0), 0),
        (lambda r: quota_service.refund_usage(r, "u1", 0), None),
        (lambda r: quota_service.heal_usage_drift(r, "u1", 0), None),
        (lambda r: quota_service.release_live_talk_seconds(r, uuid4(), seconds=0), None),
    ],
)
@pytest.mark.asyncio
async def test_nothing_to_count_never_touches_redis(call, expected):
    redis = redis_mock()
    assert await call(redis) == expected
    assert redis.mock_calls == []


@pytest.mark.parametrize(
    "call, expected",
    [
        (lambda r: quota_service.mark_usage_needs_heal(r, "u1"), None),
        (lambda r: quota_service.usage_needs_heal(r, "u1"), False),
        (lambda r: quota_service.clear_usage_needs_heal(r, "u1"), None),
        (lambda r: quota_service.record_voice_spend(r, 0.01), None),
    ],
)
@pytest.mark.asyncio
async def test_bookkeeping_survives_a_redis_outage(call, expected):
    assert await call(_down_redis()) == expected


@pytest.mark.parametrize(
    "call",
    [
        lambda r: quota_service.reserve_usage_up_to(r, "u1", 10, daily_limit=100),
        lambda r: quota_service.reserve_live_talk_seconds(
            r, uuid4(), allowance_seconds=600, max_session_seconds=60, min_session_seconds=1
        ),
    ],
)
@pytest.mark.asyncio
async def test_reserves_fail_closed_when_redis_is_down(call):
    with pytest.raises(RedisUnavailableError):
        await call(_down_redis())


@pytest.mark.asyncio
async def test_heal_usage_drift_reraises_a_redis_outage():
    with pytest.raises(RedisConnectionError):
        await quota_service.heal_usage_drift(_down_redis(), "u1", 500)


@pytest.mark.asyncio
async def test_record_usage_never_goes_below_zero(fake_redis):
    assert await quota_tokens.record_usage(fake_redis, "u1", 50) == 50
    assert await quota_tokens.record_usage(fake_redis, "u1", -80) == 0
    assert await quota_service.get_daily_usage(fake_redis, "u1") == 0


@pytest.mark.asyncio
async def test_reset_daily_usage_clears_todays_counter(fake_redis):
    await quota_tokens.record_usage(fake_redis, "u1", 50)
    assert await quota_service.has_daily_usage_key(fake_redis, "u1") is True
    await quota_service.reset_daily_usage(fake_redis, "u1")
    assert await quota_service.has_daily_usage_key(fake_redis, "u1") is False


@pytest.mark.parametrize("raw", ["garbage", "600:abc:2026-03", "600:123"])
@pytest.mark.asyncio
async def test_live_talk_settle_ignores_a_malformed_reservation(fake_redis, raw):
    user_id = uuid4()
    await fake_redis.set(f"livetalk_res:{user_id}:call-1", raw)
    assert await quota_service.settle_live_talk_session(fake_redis, user_id, "call-1") is None
    assert await fake_redis.get(f"livetalk_res:{user_id}:call-1") is None


@pytest.mark.parametrize("usd", [0, -1.0])
@pytest.mark.asyncio
async def test_record_global_spend_of_nothing_only_reads_the_total(fake_redis, usd):
    await quota_service.record_global_spend(fake_redis, 0.002)
    assert await quota_service.record_global_spend(fake_redis, usd) == 2000


@pytest.mark.asyncio
async def test_read_carried_usage_skips_an_unreadable_counter(fake_redis):
    user_id = uuid4()
    today = quota_service.utc_today().isoformat()
    await fake_redis.set(f"tavily:{user_id}:{today}", "abc")
    await fake_redis.set(f"imgup:{user_id}:{today}", 2)
    carried = await quota_service.read_carried_usage(fake_redis, user_id)
    assert carried.daily == {"imgup": 2}


# ── quota service ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_usage_when_nothing_used(fake_redis):
    from app.services import quota as quota_service

    assert await quota_service.get_daily_usage(fake_redis, "u1") == 0


@pytest.mark.asyncio
async def test_record_usage_accumulates(fake_redis):
    from app.services import quota as quota_service
    from app.services.quota import tokens as quota_tokens

    await quota_tokens.record_usage(fake_redis, "u1", 500)
    await quota_tokens.record_usage(fake_redis, "u1", 300)
    assert await quota_service.get_daily_usage(fake_redis, "u1") == 800
