"""HTTP-facing todos CRUD (create/update/delete)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DomainError
from app.models.orm import TodoItem, User
from app.modules.conversation import history as chat_history
from app.modules.todos import repository as todos_repo
from app.modules.todos.occurrences import TodoScheduleSnapshot
from app.modules.todos.recurrence import (
    RecurrenceRule,
    completed_fields,
    is_recurrence_rule,
    next_recurring_due,
    snap_first_due,
)
from app.modules.todos.schedule_repository import advance_schedules_if_current
from app.services.time_context import normalize_due_at


class TodosError(DomainError):
    """A to-do refusal."""


def _duplicate() -> TodosError:
    """Another open to-do already has this title at this time (uq_todo_open_content_due)."""
    return TodosError(
        "You already have this to-do at that time.", status_code=409, code="todo_duplicate"
    )


def _reminder_pushes_on(user: User) -> bool:
    """Reminder pushes reach this user; when they do not, listing advances recurring ones."""
    return bool(user.push_notifications_enabled and user.push_reminders_enabled)


async def list_todos_page(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 1000,
    cursor: UUID | None = None,
    completed_since: datetime | None = None,
) -> tuple[list[TodoItem], UUID | None]:
    """A page of the user's to-dos; with ``completed_since``, older completed ones are left out."""
    user_id = user.id
    selected = await todos_repo.list_after_id(
        session, user_id, limit=limit + 1, cursor=cursor, completed_since=completed_since
    )
    items = selected[:limit]
    page_ids = [item.id for item in items]
    # Preserve this boundary even when catch-up races a deletion of the last row.
    next_cursor = page_ids[-1] if len(selected) > limit else None
    if not _reminder_pushes_on(user) and await advance_past_recurring(
        session, items, timezone=user.timezone
    ):
        items = await todos_repo.list_by_ids(session, user_id, page_ids)
    return items, next_cursor


async def has_older_completed(session: AsyncSession, user: User, since: datetime) -> bool:
    """The user has completed to-dos last changed before ``since`` (a page left them out)."""
    return await todos_repo.has_completed_before(session, user.id, since)


async def create_todo(
    session: AsyncSession,
    user: User,
    *,
    content: str,
    topic: str | None,
    chat_id: UUID | None,
    due_at: datetime | None,
    recurrence_rule: RecurrenceRule | None = None,
) -> TodoItem:
    if chat_id is not None:
        chat = await chat_history.get_chat(session, chat_id, user.id)
        if chat is None:
            raise TodosError("Chat not found", status_code=400)
    normalized_due = normalize_due_at(due_at, user.timezone)
    if normalized_due is not None and recurrence_rule:
        normalized_due = snap_first_due(normalized_due, recurrence_rule, timezone=user.timezone)
    if normalized_due is None:
        recurrence_rule = None
    # Read before the try: a rollback expires the user, and reading it then fails.
    user_id = user.id
    try:
        item = await todos_repo.create(
            session,
            user_id=user_id,
            content=content,
            topic=topic or todos_repo.DEFAULT_TOPIC,
            chat_id=chat_id,
            due_at=normalized_due,
            recurrence_rule=recurrence_rule,
        )
    except IntegrityError as exc:
        if not todos_repo.is_open_content_due_conflict(exc) or normalized_due is None:
            raise
        await session.rollback()
        existing = await todos_repo.get_open_dated_duplicate(
            session, user_id, content=content, due_at=normalized_due
        )
        if existing is None:
            raise _duplicate() from exc
        return existing
    return item


async def update_todo(
    session: AsyncSession,
    user: User,
    todo_id: UUID,
    fields: dict[str, Any],
) -> TodoItem:
    item = await todos_repo.get_by_id(session, todo_id, user.id)
    if not item:
        raise TodosError("Todo not found", status_code=404)
    patch = dict(fields)
    if "due_at" in patch:
        if patch["due_at"] is None:
            if is_recurrence_rule(patch.get("recurrence_rule")):
                raise TodosError("recurrence_rule requires due_at", status_code=422)
            # An undated item cannot recur. Clearing its date therefore clears
            # the repeat rule atomically instead of leaving an invalid pair.
            patch["recurrence_rule"] = None
        else:
            patch["due_at"] = normalize_due_at(patch["due_at"], user.timezone)
    rule = patch.get("recurrence_rule", item.recurrence_rule)
    due = patch["due_at"] if "due_at" in patch else item.due_at
    if is_recurrence_rule(rule) and due is None:
        raise TodosError("recurrence_rule requires due_at", status_code=422)
    if due is not None and is_recurrence_rule(rule):
        patch["due_at"] = snap_first_due(due, rule, timezone=user.timezone)
    patch = completed_fields(
        patch,
        due_at=patch.get("due_at", item.due_at),
        rule=rule,
        timezone=user.timezone,
        now=datetime.now(UTC),
    )
    try:
        return await todos_repo.update(session, item, **patch)
    except IntegrityError as exc:
        if not todos_repo.is_open_content_due_conflict(exc):
            raise
        await session.rollback()
        raise _duplicate() from exc


async def advance_past_recurring(
    session: AsyncSession,
    items: list[TodoItem],
    *,
    timezone: str | None,
    now: datetime | None = None,
) -> bool:
    """Move each overdue recurring item to its next occurrence; commits. Whether any moved.

    Only an item still as it was read moves (``advance_schedules_if_current``).
    """
    when = now or datetime.now(UTC)
    advances = []
    for item in items:
        rule = item.recurrence_rule
        if item.checked or item.due_at is None or not is_recurrence_rule(rule):
            continue
        if item.due_at > when:
            continue
        advances.append(
            (
                TodoScheduleSnapshot.from_todo(item),
                next_recurring_due(item.due_at, rule, now=when, timezone=timezone),
            )
        )
    if not advances:
        return False
    try:
        await advance_schedules_if_current(session, advances)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return True


async def delete_todo(session: AsyncSession, user: User, todo_id: UUID) -> None:
    deleted = await todos_repo.delete_by_id(session, todo_id, user.id)
    if not deleted:
        raise TodosError("Todo not found", status_code=404)
