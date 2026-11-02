import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.background import periodic
from app.core.config import Settings
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
async def test_run_locked_cycle_skips_lock_when_disabled():
    redis = redis_mock()
    redis.set = AsyncMock(return_value=True)
    fn = AsyncMock()
    settings = Settings()

    with patch("app.background.periodic.get_redis_client", return_value=redis):
        await periodic.run_locked_cycle(
            name="test",
            lock_key="k",
            lock_ttl_seconds=60,
            enabled=False,
            fn=fn,
            settings=settings,
        )

    redis.set.assert_not_awaited()
    fn.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_periodic_does_not_spawn_when_disabled():
    settings = Settings()
    cycle = AsyncMock()
    await periodic.start_periodic(
        name="disabled-sched",
        interval_seconds=60,
        enabled=False,
        cycle=cycle,
        settings=settings,
    )
    assert "disabled-sched" not in periodic._tasks
    cycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_periodic_cancels_running_loop():
    settings = Settings()
    entered = asyncio.Event()

    async def hang(_settings: Settings) -> None:
        entered.set()
        await asyncio.Event().wait()

    await periodic.start_periodic(
        name="cancel-me",
        interval_seconds=60,
        enabled=True,
        cycle=hang,
        settings=settings,
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    await periodic.stop_periodic("cancel-me")
    assert "cancel-me" not in periodic._tasks
    assert "cancel-me" not in periodic._heartbeats


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_started_periodic_unhealthy_when_heartbeat_stale():
    settings = Settings()
    entered = asyncio.Event()

    async def hang(_settings: Settings) -> None:
        entered.set()
        await asyncio.Event().wait()

    await periodic.start_periodic(
        name="stale-hb",
        interval_seconds=60,
        enabled=True,
        cycle=hang,
        settings=settings,
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    try:
        assert periodic.is_periodic_alive("stale-hb") is True
        periodic._heartbeats["stale-hb"] = (
            time.monotonic() - periodic._HEARTBEAT_STALE_THRESHOLD_S - 1
        )
        assert periodic.is_periodic_alive("stale-hb") is False
        assert periodic.started_periodic_unhealthy() == ["stale-hb"]
    finally:
        await periodic.stop_periodic("stale-hb")
    assert periodic.started_periodic_unhealthy() == []


@pytest.mark.asyncio
async def test_periodic_heartbeat_never_set_is_alive_while_task_runs():
    settings = Settings()
    entered = asyncio.Event()

    async def hang(_settings: Settings) -> None:
        entered.set()
        await asyncio.Event().wait()

    await periodic.start_periodic(
        name="unset-hb",
        interval_seconds=60,
        enabled=True,
        cycle=hang,
        settings=settings,
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    try:
        periodic._heartbeats["unset-hb"] = 0.0
        assert periodic.is_periodic_alive("unset-hb") is True
    finally:
        await periodic.stop_periodic("unset-hb")


def test_lock_ttl_conventions():
    assert periodic.lock_ttl_hold_across_ticks(60) == 600
    assert periodic.lock_ttl_yield_next_tick(900) == 870
    assert periodic.lock_ttl_yield_next_tick(40) == 60
    assert periodic.lock_ttl_yield_next_tick(900) < 900
