"""Periodic push schedulers: to-do reminders every minute, Expo receipts every five."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.background.periodic import (
    CycleLock,
    lock_ttl_hold_across_ticks,
    run_locked_cycle,
    start_periodic,
    stop_periodic,
)
from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.gateways.expo_push_gateway import MAX_MESSAGES_PER_REQUEST
from app.modules.notifications import push as push_notifications
from app.modules.todos import advance_recurring_without_device
from app.repositories import push_tokens as push_repo

logger = logging.getLogger(__name__)

_NAME = "push"
LOCK_KEY = "recall:push:lock"
INTERVAL_SECONDS = 60
# Refreshed before every Expo request, so a live cycle keeps it however long it runs,
# and a crashed holder costs at most one tick. The fixed 600 s hold, never refreshed,
# let a slow cycle lose the lock to a peer that resent every to-do not marked yet.
LOCK_TTL_SECONDS = 2 * INTERVAL_SECONDS

_RECEIPTS_NAME = "push_receipts"
RECEIPTS_LOCK_KEY = "recall:push:receipts:lock"
RECEIPTS_INTERVAL_SECONDS = 300
RECEIPTS_LOCK_TTL_SECONDS = lock_ttl_hold_across_ticks(RECEIPTS_INTERVAL_SECONDS)


async def _push_cycle(settings: Settings, lock: CycleLock) -> None:
    redis = get_redis_client()
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        await push_notifications.log_aged_unsent_reminders(session, now=now)
        await advance_recurring_without_device(session, now=now)
    if not settings.server_todo_push_enabled:
        return
    sent = 0
    after = None
    for _ in range(push_notifications.MAX_PUSH_PAGES_PER_CYCLE):
        # A short-lived session per page; none is held across Expo HTTP.
        async with SessionLocal() as session:
            page = await push_notifications.collect_push_page(session, now=now, after=after)
        for start in range(0, len(page.messages), MAX_MESSAGES_PER_REQUEST):
            if not await lock.refresh():
                logger.warning("Push cycle lost its lock; stopping before the next send")
                return
            chunk = page.messages[start : start + MAX_MESSAGES_PER_REQUEST]
            sent += await _send_and_mark(settings, redis, chunk)
        if page.next_after is None:
            break
        after = page.next_after
    if sent:
        logger.info("Push cycle sent count=%s", sent)


async def _send_and_mark(
    settings: Settings, redis: Redis, chunk: list[push_notifications.OutboundPush]
) -> int:
    """Send one Expo request and mark its to-dos at once, before the next request.

    Marking only after the whole batch let a stopped worker (every deploy) or a lost
    lock leave accepted reminders unmarked, to go out again next cycle.
    """
    delivered, invalid_tokens, receipt_tickets = await push_notifications.dispatch_expo(
        chunk, settings
    )
    async with SessionLocal() as session:
        for expo_token in invalid_tokens:
            try:
                await push_repo.delete_by_token(session, expo_token)
                logger.info("Pruned invalid push token=%s", expo_token[:20])
            except Exception:
                logger.debug("Failed to prune push token", exc_info=True)
        if receipt_tickets:
            await push_notifications.enqueue_push_receipts(redis, receipt_tickets)
        await push_notifications.finalize_push_deliveries(session, chunk, delivered)
    return sum(1 for ok in delivered if ok)


async def run_push_cycle(settings: Settings) -> None:
    await run_locked_cycle(
        name="push",
        lock_key=LOCK_KEY,
        lock_ttl_seconds=LOCK_TTL_SECONDS,
        enabled=settings.push_enabled,
        fn=_push_cycle,
        settings=settings,
    )


async def _receipts_cycle(settings: Settings, _lock: CycleLock) -> None:
    async with SessionLocal() as session:
        await push_notifications.poll_deferred_push_receipts(session, get_redis_client())


async def run_push_receipts_cycle(settings: Settings) -> None:
    await run_locked_cycle(
        name="push receipts",
        lock_key=RECEIPTS_LOCK_KEY,
        lock_ttl_seconds=RECEIPTS_LOCK_TTL_SECONDS,
        enabled=settings.push_enabled,
        fn=_receipts_cycle,
        settings=settings,
    )


async def start_push_scheduler(settings: Settings) -> None:
    await start_periodic(
        name=_NAME,
        interval_seconds=INTERVAL_SECONDS,
        enabled=settings.push_enabled,
        cycle=run_push_cycle,
        settings=settings,
    )
    await start_periodic(
        name=_RECEIPTS_NAME,
        interval_seconds=RECEIPTS_INTERVAL_SECONDS,
        enabled=settings.push_enabled,
        cycle=run_push_receipts_cycle,
        settings=settings,
    )


async def stop_push_scheduler() -> None:
    await stop_periodic(_NAME)
    await stop_periodic(_RECEIPTS_NAME)
