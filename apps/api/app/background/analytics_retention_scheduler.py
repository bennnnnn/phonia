"""Hourly: fold product events past their retention into per-day counts and delete them."""

from __future__ import annotations

from app.background.periodic import (
    CycleLock,
    lock_ttl_yield_next_tick,
    run_locked_cycle,
    start_periodic,
    stop_periodic,
)
from app.core.config import Settings
from app.modules.analytics.retention import run_retention_pass

_NAME = "analytics_retention"
LOCK_KEY = "recall:analytics_retention:lock"


async def _retention_cycle(settings: Settings, lock: CycleLock) -> None:
    await run_retention_pass(settings, keep_going=lock.refresh)


async def run_analytics_retention_cycle(settings: Settings) -> None:
    await run_locked_cycle(
        name="analytics retention",
        lock_key=LOCK_KEY,
        lock_ttl_seconds=lock_ttl_yield_next_tick(settings.analytics_retention_interval_seconds),
        enabled=settings.analytics_event_retention_days > 0,
        fn=_retention_cycle,
        settings=settings,
    )


async def start_analytics_retention_scheduler(settings: Settings) -> None:
    await start_periodic(
        name=_NAME,
        interval_seconds=settings.analytics_retention_interval_seconds,
        enabled=settings.analytics_event_retention_days > 0,
        cycle=run_analytics_retention_cycle,
        settings=settings,
    )


async def stop_analytics_retention_scheduler() -> None:
    await stop_periodic(_NAME)
