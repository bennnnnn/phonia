"""Periodic cleanup of attachment rows never linked to a chat message."""

from __future__ import annotations

from app.background.periodic import (
    CycleLock,
    lock_ttl_yield_next_tick,
    run_locked_cycle,
    start_periodic,
    stop_periodic,
)
from app.core.config import Settings
from app.modules.attachments import lifecycle as attachment_lifecycle

_NAME = "attachment_orphan_reaper"
LOCK_KEY = "recall:attachment_orphan_reaper:lock"


async def _reaper_cycle(settings: Settings, _lock: CycleLock) -> None:
    await attachment_lifecycle.reap_orphan_attachments(settings)


async def run_orphan_reaper_cycle(settings: Settings) -> None:
    interval = settings.attachment_orphan_reaper_interval_seconds
    await run_locked_cycle(
        name="attachment orphan reaper",
        lock_key=LOCK_KEY,
        lock_ttl_seconds=lock_ttl_yield_next_tick(interval),
        enabled=settings.attachments_enabled,
        fn=_reaper_cycle,
        settings=settings,
    )


async def start_orphan_reaper(settings: Settings) -> None:
    interval = settings.attachment_orphan_reaper_interval_seconds
    await start_periodic(
        name=_NAME,
        interval_seconds=interval,
        enabled=settings.attachments_enabled,
        cycle=run_orphan_reaper_cycle,
        settings=settings,
    )


async def stop_orphan_reaper() -> None:
    await stop_periodic(_NAME)
