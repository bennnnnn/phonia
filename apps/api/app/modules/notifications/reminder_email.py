"""Opt-in transactional email reminders for dated to-dos.

Runs on the worker scheduler only — never on the chat path. Welcome and Pro
receipt emails stay on the Redis jobs stream and are not gated by
``email_reminders_enabled``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.orm import User
from app.modules.notifications import transactional_email as tx_email
from app.modules.todos import (
    EMAIL_REMINDERS,
    TodoEmailSnapshot,
    due_reminder_page,
    is_due_now,
    mark_reminder_emailed,
    reminder_page_key,
)
from app.services.reminder_timing import reminder_title

logger = logging.getLogger(__name__)

# Due to-dos read per page, and pages per cycle; the rest come next minute.
EMAIL_PAGE_ROWS = 200
MAX_EMAIL_PAGES_PER_CYCLE = 10


@dataclass(frozen=True)
class _TodoEmailDelivery:
    occurrence: TodoEmailSnapshot
    email: str
    name: str | None
    locale: str
    title: str


async def _page_deliveries(
    session: AsyncSession, *, now: datetime, after: tuple[datetime, UUID] | None
) -> tuple[list[_TodoEmailDelivery], tuple[datetime, UUID] | None]:
    rows = await due_reminder_page(
        session, EMAIL_REMINDERS, now=now, after=after, limit=EMAIL_PAGE_ROWS
    )
    deliveries: list[_TodoEmailDelivery] = []
    for todo, user in rows:
        try:
            if todo.due_at is None or not is_due_now(todo, user, now=now):
                continue
            deliveries.append(
                _TodoEmailDelivery(
                    occurrence=TodoEmailSnapshot.from_todo(todo),
                    email=user.email,
                    name=user.name,
                    locale=user.locale,
                    title=reminder_title(is_overdue=todo.due_at < now, locale=user.locale),
                )
            )
        except Exception:
            logger.exception("Todo reminder email preparation failed todo_id=%s", todo.id)
    next_after = reminder_page_key(rows) if len(rows) >= EMAIL_PAGE_ROWS else None
    return deliveries, next_after


async def process_todo_reminder_emails(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
    keep_lock: Callable[[], Awaitable[bool]] | None = None,
) -> int:
    """Send the due reminder emails, a page at a time, marking each right after its send.

    ``keep_lock`` refreshes the cycle's lock before each send; once it fails, the cycle
    stops so a peer that took the lock does not send the same reminders.
    """
    now = now or datetime.now(UTC)
    sent = 0
    after: tuple[datetime, UUID] | None = None
    for _ in range(MAX_EMAIL_PAGES_PER_CYCLE):
        deliveries, after = await _page_deliveries(session, now=now, after=after)
        # This worker owns its session. Release the read transaction before provider IO;
        # every delivery is copied first because rollback expires ORM rows.
        await session.rollback()
        for delivery in deliveries:
            if keep_lock is not None and not await keep_lock():
                logger.warning("Email reminder cycle lost its lock; stopping")
                return sent
            sent += await _send_one(session, settings, delivery, now)
        if after is None:
            break
    return sent


async def _send_one(
    session: AsyncSession, settings: Settings, delivery: _TodoEmailDelivery, now: datetime
) -> int:
    occurrence = delivery.occurrence
    try:
        recipient = User(
            id=occurrence.user_id,
            email=delivery.email,
            name=delivery.name,
            locale=delivery.locale,
        )
        ok = await tx_email.send_todo_reminder(
            settings, recipient, title=delivery.title, content=occurrence.content
        )
        if not ok:
            return 0
        await mark_reminder_emailed(session, occurrence, sent_at=now)
        await session.commit()
        return 1
    except Exception:
        await session.rollback()
        logger.exception("Todo reminder email failed todo_id=%s", occurrence.id)
        return 0


async def run_email_reminder_cycle(
    session: AsyncSession,
    settings: Settings,
    *,
    keep_lock: Callable[[], Awaitable[bool]] | None = None,
) -> int:
    if not settings.email_enabled or not settings.email_reminders_scheduler_enabled:
        return 0
    now = datetime.now(UTC)
    return await process_todo_reminder_emails(session, settings, now=now, keep_lock=keep_lock)
