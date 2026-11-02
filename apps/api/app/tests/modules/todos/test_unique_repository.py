"""Postgres unique index on open dated reminders (migration 0084)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.todos import repository as todos_repo
from app.repositories import users as users_repo


async def _user_and_due(session):
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    due = datetime(2026, 9, 8, 15, tzinfo=UTC)
    return user, due


@pytest.mark.asyncio
async def test_open_dated_same_content_and_due_is_unique(db_session):
    user, due = await _user_and_due(db_session)
    await todos_repo.create(
        db_session,
        user_id=user.id,
        content="Call mom",
        topic="Reminders",
        due_at=due,
    )
    with pytest.raises(IntegrityError):
        await todos_repo.create(
            db_session,
            user_id=user.id,
            content="CALL MOM",
            topic="Reminders",
            due_at=due,
        )


@pytest.mark.asyncio
async def test_same_title_different_due_is_allowed(db_session):
    user, due = await _user_and_due(db_session)
    await todos_repo.create(
        db_session,
        user_id=user.id,
        content="Call mom",
        topic="Reminders",
        due_at=due,
    )
    other = await todos_repo.create(
        db_session,
        user_id=user.id,
        content="Call mom",
        topic="Reminders",
        due_at=due + timedelta(days=1),
    )
    assert other.id is not None


@pytest.mark.asyncio
async def test_checked_duplicate_open_dated_is_allowed(db_session):
    user, due = await _user_and_due(db_session)
    done = await todos_repo.create(
        db_session,
        user_id=user.id,
        content="Call mom",
        topic="Reminders",
        due_at=due,
    )
    await todos_repo.update(db_session, done, checked=True)
    again = await todos_repo.create(
        db_session,
        user_id=user.id,
        content="Call mom",
        topic="Reminders",
        due_at=due,
    )
    assert again.id != done.id


@pytest.mark.asyncio
async def test_open_dated_unique_is_per_user(db_session):
    user_a, due = await _user_and_due(db_session)
    user_b, _ = await _user_and_due(db_session)
    await todos_repo.create(
        db_session,
        user_id=user_a.id,
        content="Call mom",
        topic="Reminders",
        due_at=due,
    )
    other = await todos_repo.create(
        db_session,
        user_id=user_b.id,
        content="Call mom",
        topic="Reminders",
        due_at=due,
    )
    assert other.id is not None
