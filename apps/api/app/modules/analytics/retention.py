"""Fold product events past their retention into per-day counts, then delete them.

Every chat turn recorded two events and nothing deleted any: millions of rows a day at
scale, each updating two indexes, kept forever and copied into every branch. Each cycle
takes the oldest day past the retention: counts it into ``product_event_daily`` (once;
``product_event_rollup_days`` marks it), then deletes its rows in batches, a bounded
number per cycle so a backlog drains over several runs.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules.analytics.service import EVENT_NAMES
from app.repositories import product_events as events_repo

logger = logging.getLogger(__name__)


async def run_retention_pass(
    settings: Settings,
    *,
    keep_going: Callable[[], Awaitable[bool]],
    today: date | None = None,
) -> int:
    """Roll up and delete events older than the retention; returns rows deleted.

    ``keep_going`` is asked before each batch (the cycle's lock refresh): False stops.
    """
    today = today or datetime.now(UTC).date()
    cutoff = today - timedelta(days=max(1, settings.analytics_event_retention_days))
    batch = max(1, settings.analytics_retention_delete_batch)
    budget = max(batch, settings.analytics_retention_max_deletes_per_cycle)
    deleted = 0
    while deleted < budget:
        async with SessionLocal() as session:
            day = await events_repo.oldest_day(session, EVENT_NAMES)
        if day is None or day >= cutoff:
            break
        await _roll_up_once(day)
        while deleted < budget:
            if not await keep_going():
                return deleted
            async with SessionLocal() as session:
                removed = await events_repo.delete_day_batch(session, day, EVENT_NAMES, limit=batch)
                await session.commit()
            deleted += removed
            if removed < batch:
                break
    if deleted:
        logger.info("Product events rolled up and deleted rows=%s", deleted)
    return deleted


async def _roll_up_once(day: date) -> None:
    async with SessionLocal() as session:
        if await events_repo.is_rolled_up(session, day):
            return
        try:
            await events_repo.roll_up_day(session, day, EVENT_NAMES)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
