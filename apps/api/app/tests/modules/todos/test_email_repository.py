"""PostgreSQL coverage for email occurrence finalization and ownership."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.orm import TodoItem
from app.modules.todos.email_repository import mark_email_sent_if_current
from app.modules.todos.occurrences import TodoEmailSnapshot
from app.repositories import users as users_repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["current", "push", "due", "checked", "repeat", "content", "sent", "delete", "owner", "id"],
)
async def test_email_finalization_only_stamps_owned_unchanged_occurrence(db_session, change):
    user = await users_repo.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    now = datetime(2026, 9, 5, 8, tzinfo=UTC)
    todo = TodoItem(
        user_id=user.id,
        content="Call Mom",
        topic="Reminders",
        checked=False,
        due_at=now + timedelta(minutes=5),
    )
    db_session.add(todo)
    await db_session.flush()
    snapshot = TodoEmailSnapshot.from_todo(todo)
    if change == "due":
        todo.due_at += timedelta(days=1)
    elif change == "checked":
        todo.checked = True
    elif change == "repeat":
        todo.recurrence_rule = "daily"
    elif change == "content":
        todo.content = "Call Dad"
    elif change == "sent":
        todo.email_sent_at = now - timedelta(minutes=1)
    elif change == "push":
        todo.notification_sent_at = now
    elif change == "delete":
        await db_session.delete(todo)
    elif change == "owner":
        snapshot = replace(snapshot, user_id=uuid4())
    elif change == "id":
        snapshot = replace(snapshot, id=uuid4())
    await db_session.flush()

    accepted = change in ("current", "push")
    assert await mark_email_sent_if_current(db_session, snapshot, now) is accepted
    if change == "delete":
        assert await db_session.get(TodoItem, snapshot.id) is None
        return
    await db_session.refresh(todo)
    expected_marker = now if accepted else now - timedelta(minutes=1) if change == "sent" else None
    assert todo.email_sent_at == expected_marker
    assert todo.notification_sent_at == (now if change == "push" else None)
    assert todo.content == ("Call Dad" if change == "content" else snapshot.content)
    assert todo.checked is (change == "checked")
    assert todo.recurrence_rule == ("daily" if change == "repeat" else None)
    assert todo.due_at == snapshot.due_at + (timedelta(days=1) if change == "due" else timedelta())
