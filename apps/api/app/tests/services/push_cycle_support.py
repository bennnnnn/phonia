"""Test helper: one push cycle on a single session.

The scheduler (``background/push_scheduler.py``) runs collect → dispatch → finalize with its own
sessions and lock, page by page; this runs the same push-service steps on the test's session,
every page at once. Steps are read from the modules at call time, so ``patch.object`` on
``push_service`` or on this module reaches them.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.notifications import push as push_service
from app.modules.todos import advance_recurring_without_device

logger = logging.getLogger(push_service.__name__)


async def process_todo_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> list[push_service.OutboundPush]:
    """Every due reminder's messages, page after page (the scheduler sends per page)."""
    now = now or datetime.now(UTC)
    await advance_recurring_without_device(session, now=now)
    messages: list[push_service.OutboundPush] = []
    after: tuple[datetime, UUID] | None = None
    for _ in range(push_service.MAX_PUSH_PAGES_PER_CYCLE):
        page = await push_service.collect_push_page(session, now=now, after=after)
        messages.extend(page.messages)
        if page.next_after is None:
            break
        after = page.next_after
    return messages


async def collect_push_outbound(
    session: AsyncSession, settings: Settings, *, now: datetime | None = None
) -> list[push_service.OutboundPush]:
    """The cycle's collect step: the scheduler's push and server-push switches, then every page."""
    if not settings.push_enabled:
        return []
    now = now or datetime.now(UTC)
    await push_service.log_aged_unsent_reminders(session, now=now)
    if not settings.server_todo_push_enabled:
        return []
    return await process_todo_reminders(session, now=now)


async def run_push_cycle(session: AsyncSession, redis: Redis, settings: Settings) -> int:
    outbound = await collect_push_outbound(session, settings)
    if not outbound:
        return 0
    delivered, invalid_tokens, receipt_tickets = await push_service.dispatch_expo(
        outbound, settings
    )
    for token in invalid_tokens:
        try:
            await push_service.push_repo.delete_by_token(session, token)
            logger.info("Pruned invalid push token=%s", token[:20])
        except Exception:
            logger.debug("Failed to prune push token", exc_info=True)
    if receipt_tickets:
        await push_service.enqueue_push_receipts(redis, receipt_tickets)
    await push_service.finalize_push_deliveries(session, outbound, delivered)
    return len(outbound)
