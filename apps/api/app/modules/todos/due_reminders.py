"""Which dated to-dos a reminder channel owes now: one query for push and email.

Both channels used to write their own copy of the same window, join and checks,
with email's recurring-row filter the one deliberate difference, so a change to
what "due" means had to be made twice. The candidates come in pages ordered by
``(due_at, id)`` over a partial index per channel (migration 0117), so a minute's
cycle reads only rows in the reminder window and stops at its bound; the rest
come next cycle.

What a send changes is here too (``mark_reminder_pushed``, ``mark_reminder_emailed``):
notifications delivers and never writes a to-do row itself (code-health audit ARCH-05).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, false, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.orm import PushToken, TodoItem, User
from app.modules.todos.crud import advance_past_recurring
from app.modules.todos.email_repository import mark_email_sent_if_current
from app.modules.todos.occurrences import TodoEmailSnapshot, TodoScheduleSnapshot
from app.modules.todos.recurrence import is_recurrence_rule, next_recurring_due, snap_first_due
from app.modules.todos.schedule_repository import update_schedule_if_current
from app.services.reminder_timing import (
    MAX_REMINDER_LEAD_MINUTES,
    OVERDUE_MAX_HOURS,
    QuietHours,
    in_quiet_hours,
    reminder_at,
)
from app.services.time_context import normalize_due_at


@dataclass(frozen=True, slots=True)
class ReminderChannel:
    """What one channel marks when it sends, and who has asked for it."""

    name: str
    sent_at: InstrumentedAttribute[datetime | None]
    opted_in: tuple[ColumnElement[bool], ...]
    include_recurring: bool


PUSH_REMINDERS = ReminderChannel(
    name="push",
    sent_at=TodoItem.notification_sent_at,
    opted_in=(
        User.push_notifications_enabled.is_(True),
        User.push_reminders_enabled.is_(True),
        # A user with no device token is left out here: everyone who denied the OS
        # permission sat in every minute's scan for 48 hours.
        select(PushToken.id).where(PushToken.user_id == TodoItem.user_id).exists(),
    ),
    include_recurring=True,
)
# A recurring to-do moves to its next occurrence when pushed; email does not send them.
EMAIL_REMINDERS = ReminderChannel(
    name="email",
    sent_at=TodoItem.email_sent_at,
    opted_in=(User.email_reminders_enabled.is_(True), User.email != ""),
    include_recurring=False,
)

PageKey = tuple[datetime, UUID]


async def due_reminder_page(
    session: AsyncSession,
    channel: ReminderChannel,
    *,
    now: datetime,
    after: PageKey | None = None,
    limit: int = 500,
) -> list[tuple[TodoItem, User]]:
    """Open dated to-dos in the window ``[now - 48 h, now + the longest lead]`` the channel
    has not sent, ordered by ``(due_at, id)`` and starting after ``after``.

    ``checked == false()`` renders ``checked = false``, the predicate the partial index
    has; ``IS false`` might not let the planner use it.
    """
    stmt = (
        select(TodoItem, User)
        .join(User, User.id == TodoItem.user_id)
        .where(
            TodoItem.checked == false(),
            TodoItem.due_at.isnot(None),
            channel.sent_at.is_(None),
            TodoItem.due_at >= now - timedelta(hours=OVERDUE_MAX_HOURS),
            TodoItem.due_at <= now + timedelta(minutes=MAX_REMINDER_LEAD_MINUTES),
            *channel.opted_in,
        )
        .order_by(TodoItem.due_at, TodoItem.id)
        .limit(limit)
    )
    if not channel.include_recurring:
        stmt = stmt.where(TodoItem.recurrence_rule.is_(None))
    if after is not None:
        stmt = stmt.where(tuple_(TodoItem.due_at, TodoItem.id) > tuple_(*after))
    return [(todo, user) for todo, user in (await session.execute(stmt)).all()]


def reminder_page_key(rows: list[tuple[TodoItem, User]]) -> PageKey | None:
    """Where the next page starts: after the last row of this one."""
    if not rows:
        return None
    last = rows[-1][0]
    if last.due_at is None:
        return None
    return last.due_at, last.id


def reminder_instant(todo: TodoItem, user: User) -> datetime | None:
    """When ``todo``'s reminder goes out for ``user``: the to-do list's ``notify_at``, which
    the phone schedules its own alert at, and the moment push and email send. None: never.
    """
    if todo.checked or todo.due_at is None:
        return None
    return reminder_at(
        todo.due_at,
        set_at=todo.due_set_at,
        lead_minutes=user.reminder_lead_minutes,
        quiet=QuietHours.of(user),
    )


def preview_instant(
    user: User, due_at: datetime, recurrence_rule: str | None, *, now: datetime
) -> datetime | None:
    """The ``notify_at`` a to-do due at ``due_at`` gets if it is saved at ``now``: the due
    time as a save stores it (the user's zone for a time with none, a weekday repeat's first
    weekday), set now. The to-do editor shows it before the to-do is saved.
    """
    due = normalize_due_at(due_at, user.timezone)
    if due is not None and is_recurrence_rule(recurrence_rule):
        due = snap_first_due(due, recurrence_rule, timezone=user.timezone)
    return reminder_instant(TodoItem(checked=False, due_at=due, due_set_at=now), user)


def is_due_now(todo: TodoItem, user: User, *, now: datetime) -> bool:
    """The to-do's reminder instant has come and it is not yet 48 hours overdue.

    The instant already waits out quiet hours; ``now`` is checked too, so a cycle that runs
    late (a worker that was down) does not send one at night.
    """
    at = reminder_instant(todo, user)
    if at is None or todo.due_at is None or at > now:
        return False
    if todo.due_at < now - timedelta(hours=OVERDUE_MAX_HOURS):
        return False
    return not in_quiet_hours(user, now=now)


async def tokenless_recurring_overdue(
    session: AsyncSession, *, now: datetime, limit: int = 500
) -> list[tuple[TodoItem, User]]:
    """Overdue recurring to-dos of push users with no device, which push skips.

    Each is moved to its next occurrence so it neither waits forever nor fires late.
    """
    has_token = select(PushToken.id).where(PushToken.user_id == TodoItem.user_id).exists()
    stmt = (
        select(TodoItem, User)
        .join(User, User.id == TodoItem.user_id)
        .where(
            TodoItem.checked == false(),
            TodoItem.due_at.isnot(None),
            TodoItem.notification_sent_at.is_(None),
            TodoItem.recurrence_rule.isnot(None),
            TodoItem.due_at >= now - timedelta(hours=OVERDUE_MAX_HOURS),
            TodoItem.due_at <= now,
            User.push_notifications_enabled.is_(True),
            User.push_reminders_enabled.is_(True),
            ~has_token,
        )
        .order_by(TodoItem.due_at, TodoItem.id)
        .limit(limit)
    )
    return [(todo, user) for todo, user in (await session.execute(stmt)).all()]


async def aged_out_unsent(
    session: AsyncSession, channel: ReminderChannel, *, now: datetime, window: timedelta
) -> int:
    """How many of the channel's reminders crossed the 48 h overdue line unsent in ``window``.

    Only users the channel reaches count, so a row that aged out is a delivery failure.
    """
    cutoff = now - timedelta(hours=OVERDUE_MAX_HOURS)
    raw = await session.scalar(
        select(func.count())
        .select_from(TodoItem)
        .join(User, User.id == TodoItem.user_id)
        .where(
            TodoItem.checked == false(),
            TodoItem.due_at.isnot(None),
            channel.sent_at.is_(None),
            TodoItem.due_at < cutoff,
            TodoItem.due_at >= cutoff - window,
            *channel.opted_in,
        )
    )
    return raw if isinstance(raw, int) else 0


async def mark_reminder_pushed(session: AsyncSession, todo: TodoItem, *, now: datetime) -> bool:
    """After a push for ``todo`` went out; no commit. Whether the to-do changed.

    A recurring to-do moves to its next occurrence, any other is stamped sent. Only the
    occurrence that was read changes: one edited or completed meanwhile is left alone.
    """
    snapshot = TodoScheduleSnapshot.from_todo(todo)
    rule, due = snapshot.recurrence_rule, snapshot.due_at
    if is_recurrence_rule(rule) and due is not None:
        user_row = await session.get(User, snapshot.user_id)
        timezone = user_row.timezone if user_row is not None else None
        # A lead-time notification already consumed this occurrence, even
        # when its due time is still in the future.
        nxt = next_recurring_due(due, rule, now=max(now, due), timezone=timezone)
        return await update_schedule_if_current(
            session,
            snapshot,
            due_at=nxt,
            due_set_at=func.now(),
            notification_sent_at=None,
            email_sent_at=None,
        )
    # A delivery is not a change to the to-do: updated_at stays.
    return await update_schedule_if_current(
        session, snapshot, notification_sent_at=now, updated_at=TodoItem.updated_at
    )


async def mark_reminder_emailed(
    session: AsyncSession, occurrence: TodoEmailSnapshot, *, sent_at: datetime
) -> bool:
    """After the reminder email for ``occurrence`` went out; no commit. Whether it was stamped.

    Push keeps its own marker; a to-do changed since it was read is left alone.
    """
    return await mark_email_sent_if_current(session, occurrence, sent_at)


async def advance_recurring_without_device(session: AsyncSession, *, now: datetime) -> int:
    """Move push users' overdue recurring to-dos to their next occurrence when they have no
    device to push to; commits. How many moved.

    Push skips these users, so each would otherwise wait forever or fire late.
    """
    rows = [
        (todo, user)
        for todo, user in await tokenless_recurring_overdue(session, now=now)
        if is_recurrence_rule(todo.recurrence_rule) and is_due_now(todo, user, now=now)
    ]
    if not rows:
        return 0
    by_timezone: dict[str | None, list[TodoItem]] = defaultdict(list)
    for todo, user in rows:
        by_timezone[user.timezone if isinstance(user.timezone, str) else None].append(todo)
    for timezone, items in by_timezone.items():
        await advance_past_recurring(session, items, timezone=timezone, now=now)
    return len(rows)
