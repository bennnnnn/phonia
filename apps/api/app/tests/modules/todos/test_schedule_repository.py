"""PostgreSQL coverage for conditional dated To-do persistence and ownership."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.orm import TodoItem
from app.modules.todos.occurrences import TodoScheduleSnapshot
from app.modules.todos.schedule_repository import (
    advance_schedules_if_current,
    update_schedule_if_current,
)
from app.repositories import users as users_repo


async def _new_todo(session):
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    todo = TodoItem(
        user_id=user.id,
        content="Call Mom",
        topic="Reminders",
        checked=False,
        due_at=datetime(2026, 9, 5, 8, tzinfo=UTC),
        recurrence_rule="daily",
    )
    session.add(todo)
    await session.flush()
    return todo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["current", "due", "checked", "repeat", "content", "sent", "delete", "owner"]
)
async def test_delayed_delivery_only_updates_owned_unchanged_occurrence(db_session, change):
    todo = await _new_todo(db_session)
    snapshot = TodoScheduleSnapshot.from_todo(todo)
    if change == "due":
        todo.due_at += timedelta(days=4)
    elif change == "checked":
        todo.checked = True
    elif change == "repeat":
        todo.recurrence_rule = "weekdays"
    elif change == "content":
        todo.content = "Call Dad"
    elif change == "sent":
        todo.notification_sent_at = datetime(2026, 9, 5, 7, 50, tzinfo=UTC)
    elif change == "delete":
        await db_session.delete(todo)
    elif change == "owner":
        snapshot = replace(snapshot, user_id=uuid4())
    await db_session.flush()
    next_due = snapshot.due_at + timedelta(days=1)
    assert await update_schedule_if_current(
        db_session,
        snapshot,
        due_at=next_due,
        notification_sent_at=None,
    ) is (change == "current")
    if change == "delete":
        assert await db_session.get(TodoItem, snapshot.id) is None
        return
    await db_session.refresh(todo)
    if change == "current":
        assert todo.due_at == next_due
    elif change == "due":
        assert todo.due_at == snapshot.due_at + timedelta(days=4)
    else:
        assert todo.due_at == snapshot.due_at


@pytest.mark.asyncio
async def test_batch_catchup_advances_only_unchanged_snapshots(db_session):
    current = await _new_todo(db_session)
    edited = await _new_todo(db_session)
    deleted = await _new_todo(db_session)
    snapshots = [TodoScheduleSnapshot.from_todo(todo) for todo in [current, edited, deleted]]
    manual_due = edited.due_at + timedelta(days=4)
    edited.due_at = manual_due
    await db_session.delete(deleted)
    await db_session.flush()
    await advance_schedules_if_current(
        db_session,
        [(snapshot, snapshot.due_at + timedelta(days=1)) for snapshot in snapshots],
    )
    await db_session.refresh(current)
    await db_session.refresh(edited)
    assert current.due_at == snapshots[0].due_at + timedelta(days=1)
    assert edited.due_at == manual_due
    assert await db_session.get(TodoItem, snapshots[2].id) is None
