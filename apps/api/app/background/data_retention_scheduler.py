"""Hourly: delete data nothing reads any more, a batch at a time.

- Chats never sent to, older than ``abandoned_draft_chat_hours``: the phone makes one on
  the first keystroke, and a killed app left a row the user could neither see nor delete.
- Daily usage rows older than ``usage_daily_retention_days``: quota reads today's row, and
  one row per user per active day was kept for ever.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.background.periodic import (
    CycleLock,
    lock_ttl_yield_next_tick,
    run_locked_cycle,
    start_periodic,
    stop_periodic,
)
from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules.conversation import service as conversation_service
from app.repositories import usage as usage_repo

logger = logging.getLogger(__name__)

_NAME = "data_retention"
LOCK_KEY = "recall:data_retention:lock"

_Delete = Callable[[AsyncSession, int], Awaitable[int]]


async def _delete_in_batches(
    settings: Settings, delete_batch: _Delete, keep_going: Callable[[], Awaitable[bool]]
) -> int:
    """Run ``delete_batch`` until a batch comes back short, the budget is spent or the lock
    is lost; each batch commits on its own."""
    batch = max(1, settings.data_retention_delete_batch)
    budget = max(batch, settings.data_retention_max_deletes_per_cycle)
    deleted = 0
    while deleted < budget and await keep_going():
        async with SessionLocal() as session:
            removed = await delete_batch(session, batch)
            await session.commit()
        deleted += removed
        if removed < batch:
            break
    return deleted


async def run_retention(settings: Settings, keep_going: Callable[[], Awaitable[bool]]) -> int:
    now = datetime.now(UTC)
    drafts_before = now - timedelta(hours=max(1, settings.abandoned_draft_chat_hours))
    usage_before = (now - timedelta(days=max(1, settings.usage_daily_retention_days))).date()
    drafts = await _delete_in_batches(
        settings,
        lambda session, limit: conversation_service.delete_abandoned_drafts(
            session, drafts_before, limit=limit
        ),
        keep_going,
    )
    usage = await _delete_in_batches(
        settings,
        lambda session, limit: usage_repo.delete_before(session, usage_before, limit=limit),
        keep_going,
    )
    if drafts or usage:
        logger.info("Data retention deleted drafts=%s usage_days=%s", drafts, usage)
    return drafts + usage


async def _retention_cycle(settings: Settings, lock: CycleLock) -> None:
    await run_retention(settings, lock.refresh)


async def run_data_retention_cycle(settings: Settings) -> None:
    await run_locked_cycle(
        name="data retention",
        lock_key=LOCK_KEY,
        lock_ttl_seconds=lock_ttl_yield_next_tick(settings.data_retention_interval_seconds),
        enabled=settings.data_retention_interval_seconds > 0,
        fn=_retention_cycle,
        settings=settings,
    )


async def start_data_retention_scheduler(settings: Settings) -> None:
    await start_periodic(
        name=_NAME,
        interval_seconds=settings.data_retention_interval_seconds,
        enabled=settings.data_retention_interval_seconds > 0,
        cycle=run_data_retention_cycle,
        settings=settings,
    )


async def stop_data_retention_scheduler() -> None:
    await stop_periodic(_NAME)
