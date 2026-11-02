"""Execute email reminder eligibility and finalization against offline SQL."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import JSON, DateTime, create_engine, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeDecorator

from app.core.config import Settings
from app.models.orm import TodoItem, User
from app.modules.notifications import reminder_email

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


class _UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


@pytest.fixture
def email_sql():
    columns = [
        column
        for table in [TodoItem.__table__, User.__table__]
        for column in table.c
        if isinstance(column.type, DateTime | JSONB)
    ]
    original = [column.type for column in columns]
    for column in columns:
        column.type = JSON() if isinstance(column.type, JSONB) else _UTCDateTime()
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    TodoItem.__table__.create(engine)
    try:
        with Session(engine, expire_on_commit=False) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.execute.side_effect = sync_session.execute
            session.commit.side_effect = sync_session.commit
            session.rollback.side_effect = sync_session.rollback
            yield sync_session, session
    finally:
        engine.dispose()
        for column, old in zip(columns, original, strict=True):
            column.type = old


def _rows(sync_session, *, count=1):
    user = User(
        id=uuid4(), email=f"{uuid4()}@example.com", name="Ada", email_reminders_enabled=True
    )
    sync_session.add(user)
    rows = [
        TodoItem(
            id=uuid4(),
            user_id=user.id,
            content=f"Call Mom {index}",
            topic="Reminders",
            checked=False,
            due_at=NOW + timedelta(minutes=5),
            recurrence_rule=None,
            # Set well before its lead window, so the lead time applies.
            created_at=NOW - timedelta(hours=2),
            updated_at=NOW - timedelta(hours=2),
            due_set_at=NOW - timedelta(hours=2),
        )
        for index in range(count)
    ]
    sync_session.add_all(rows)
    sync_session.commit()
    return user, rows


@pytest.mark.asyncio
async def test_only_one_shot_reminders_are_selected_for_email(email_sql):
    sync_session, session = email_sql
    _, rows = _rows(sync_session, count=5)
    for row, rule in zip(rows[1:], ["daily", "weekdays", "weekly", "monthly"], strict=True):
        row.recurrence_rule = rule
    sync_session.commit()
    expected_content = rows[0].content
    with patch.object(
        reminder_email.tx_email, "send_todo_reminder", AsyncMock(return_value=True)
    ) as send:
        count = await reminder_email.process_todo_reminder_emails(session, Settings(), now=NOW)
    assert count == 1
    assert [call.kwargs["content"] for call in send.await_args_list] == [expected_content]
    for row in rows[1:]:
        sync_session.refresh(row)
        assert row.email_sent_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["reschedule", "complete", "repeat", "content", "sent", "delete"]
)
async def test_late_email_cannot_stamp_a_changed_occurrence(email_sql, change):
    sync_session, session = email_sql
    _, rows = _rows(sync_session)
    row = rows[0]
    row_id = row.id
    delivered_content = row.content

    async def send(*args, **kwargs):
        current = sync_session.get(TodoItem, row_id)
        if change == "reschedule":
            current.due_at += timedelta(days=1)
        elif change == "complete":
            current.checked = True
        elif change == "repeat":
            current.recurrence_rule = "daily"
        elif change == "content":
            current.content = "Edited reminder"
        elif change == "sent":
            current.email_sent_at = NOW - timedelta(minutes=1)
        else:
            sync_session.delete(current)
        sync_session.commit()
        return True

    with patch.object(
        reminder_email.tx_email, "send_todo_reminder", AsyncMock(side_effect=send)
    ) as sender:
        await reminder_email.process_todo_reminder_emails(session, Settings(), now=NOW)
    assert sender.await_args.kwargs["content"] == delivered_content
    current = sync_session.get(TodoItem, row_id)
    if change == "delete":
        assert current is None
    else:
        sync_session.refresh(current)
        assert current.email_sent_at == (NOW - timedelta(minutes=1) if change == "sent" else None)


@pytest.mark.asyncio
async def test_one_shot_push_marker_does_not_block_email_finalization(email_sql):
    sync_session, session = email_sql
    _, rows = _rows(sync_session)
    row_id = rows[0].id

    async def send(*args, **kwargs):
        sync_session.execute(
            update(TodoItem).where(TodoItem.id == row_id).values(notification_sent_at=NOW)
        )
        sync_session.commit()
        return True

    with patch.object(reminder_email.tx_email, "send_todo_reminder", AsyncMock(side_effect=send)):
        assert await reminder_email.process_todo_reminder_emails(session, Settings(), now=NOW) == 1
    sync_session.refresh(rows[0])
    assert rows[0].notification_sent_at == NOW
    assert rows[0].email_sent_at == NOW


@pytest.mark.asyncio
async def test_email_provider_runs_without_a_read_transaction(email_sql):
    sync_session, session = email_sql
    _rows(sync_session)
    transactions = []

    async def send(*args, **kwargs):
        transactions.append(sync_session.in_transaction())
        return True

    with patch.object(reminder_email.tx_email, "send_todo_reminder", AsyncMock(side_effect=send)):
        await reminder_email.process_todo_reminder_emails(session, Settings(), now=NOW)
    assert transactions == [False]


@pytest.mark.asyncio
@pytest.mark.parametrize("run_cycle", [False, True])
async def test_failed_email_commit_recovers_session_and_continues_batch(email_sql, run_cycle):
    sync_session, session = email_sql
    user, rows = _rows(sync_session, count=2)
    email = user.email
    attempts = []
    failed = False

    def commit():
        nonlocal failed
        if not failed:
            failed = True
            # A real integrity failure puts the ORM session into failed state.
            sync_session.add(User(email=email, name="Duplicate"))
        sync_session.commit()

    async def send(*args, **kwargs):
        attempts.append(kwargs["content"])
        session.commit.side_effect = commit
        return True

    with (
        patch.object(reminder_email.tx_email, "send_todo_reminder", AsyncMock(side_effect=send)),
        patch.object(reminder_email, "datetime", wraps=datetime) as clock,
    ):
        clock.now.return_value = NOW
        if run_cycle:
            settings = Settings(email_enabled=True, email_reminders_scheduler_enabled=True)
            count = await reminder_email.run_email_reminder_cycle(session, settings)
        else:
            count = await reminder_email.process_todo_reminder_emails(session, Settings(), now=NOW)
    assert len(attempts) == 2
    assert count == 1
    assert sync_session.is_active
    session.rollback.assert_awaited()
    for row in rows:
        sync_session.refresh(row)
    assert sum(row.email_sent_at is not None for row in rows) == 1
