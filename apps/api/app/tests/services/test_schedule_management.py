"""Schedule management regressions with real local SQL and no external services."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.types import DateTime, TypeDecorator

from app.models.orm import TodoItem, User
from app.modules.notifications import push
from app.modules.todos import actions, crud
from app.modules.todos import repository as todos_repo
from app.modules.todos.schemas import TodoActionItem


class _UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


@pytest.fixture
def schedule_sql():
    columns = [c for c in TodoItem.__table__.c if isinstance(c.type, DateTime)]
    original_types = [c.type for c in columns]
    for column in columns:
        column.type = _UTCDateTime()
    engine = create_engine("sqlite://")
    TodoItem.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync_session:
        session = AsyncMock(spec=AsyncSession)
        session.execute.side_effect = sync_session.execute
        session.commit.side_effect = sync_session.commit
        session.rollback.side_effect = sync_session.rollback
        session.refresh.side_effect = sync_session.refresh
        session.flush.side_effect = sync_session.flush
        session.add.side_effect = sync_session.add
        session.get.side_effect = lambda model, ident: (
            SimpleNamespace(timezone="UTC") if model is User else sync_session.get(model, ident)
        )
        yield sync_session, session
    engine.dispose()
    for column, original_type in zip(columns, original_types, strict=True):
        column.type = original_type


def _todo(sync_session, *, recurring=False, due=None):
    row = TodoItem(
        id=uuid4(),
        user_id=uuid4(),
        content="Call Mom",
        topic="Reminders",
        checked=False,
        due_at=due or datetime(2026, 9, 5, 8, tzinfo=UTC),
        recurrence_rule="daily" if recurring else None,
        notification_sent_at=datetime(2026, 9, 4, tzinfo=UTC),
        email_sent_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    sync_session.add(row)
    sync_session.commit()
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["patch_repeat", "chat"])
async def test_effective_reschedule_clears_delivery_markers(schedule_sql, path):
    sync_session, session = schedule_sql
    row = _todo(sync_session)
    user = SimpleNamespace(id=row.user_id, timezone="UTC")
    if path == "patch_repeat":
        await crud.update_todo(session, user, row.id, {"recurrence_rule": "weekdays"})
    else:
        await actions.apply_todo_actions(
            session,
            user_id=row.user_id,
            user_timezone="UTC",
            actions=[
                TodoActionItem(
                    action="set_due",
                    topic=row.topic,
                    content=row.content,
                    due_at=row.due_at + timedelta(days=3),
                )
            ],
        )
        await session.commit()  # the caller commits (code-health audit ARCH-07)
    sync_session.refresh(row)
    assert row.notification_sent_at is None
    assert row.email_sent_at is None


@pytest.mark.asyncio
async def test_equivalent_weekday_due_keeps_sent_markers(schedule_sql):
    sync_session, session = schedule_sql
    row = _todo(sync_session, due=datetime(2026, 9, 7, 8, tzinfo=UTC))
    row.recurrence_rule = "weekdays"
    sync_session.commit()
    await crud.update_todo(
        session,
        SimpleNamespace(id=row.user_id, timezone="UTC"),
        row.id,
        {"due_at": datetime(2026, 9, 5, 8, tzinfo=UTC)},
    )
    sync_session.refresh(row)
    assert row.notification_sent_at is not None
    assert row.email_sent_at is not None


@pytest.mark.asyncio
async def test_push_enabled_list_does_not_skip_undelivered_occurrence(schedule_sql):
    sync_session, session = schedule_sql
    due = datetime.now(UTC) - timedelta(minutes=1)
    row = _todo(sync_session, recurring=True, due=due)
    row.notification_sent_at = None
    sync_session.commit()
    listed, _cursor = await crud.list_todos_page(
        session,
        SimpleNamespace(
            id=row.user_id,
            timezone="UTC",
            push_notifications_enabled=True,
            push_reminders_enabled=True,
        ),
    )
    assert listed[0].due_at == due
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_catchup_cannot_overwrite_reschedule(schedule_sql):
    sync_session, session = schedule_sql
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    row = _todo(sync_session, recurring=True, due=now - timedelta(days=1))
    manual_due = now + timedelta(days=10)
    # Separate SQL writer updates the row after this session loaded its snapshot.
    sync_session.execute(
        update(TodoItem)
        .where(TodoItem.id == row.id)
        .values(due_at=manual_due)
        .execution_options(synchronize_session=False)
    )
    sync_session.commit()
    await crud.advance_past_recurring(session, [row], timezone="UTC", now=now)
    sync_session.refresh(row)
    assert row.due_at == manual_due


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["reschedule", "complete", "repeat"])
async def test_stale_push_does_not_mark_changed_schedule_sent(schedule_sql, change):
    sync_session, session = schedule_sql
    row = _todo(sync_session)
    row.notification_sent_at = None
    sync_session.commit()
    snapshot = SimpleNamespace(
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "user_id",
                "content",
                "checked",
                "due_at",
                "recurrence_rule",
                "notification_sent_at",
            )
        }
    )
    original_due = row.due_at
    if change == "reschedule":
        row.due_at += timedelta(days=3)
    elif change == "complete":
        row.checked = True
    else:
        row.recurrence_rule = "daily"
    sync_session.commit()
    await push.finalize_push_deliveries(
        session,
        [push.OutboundPush(message={}, todos=[snapshot])],
        [True],
        now=datetime(2026, 9, 5, 8, tzinfo=UTC),
    )
    sync_session.refresh(row)
    assert row.notification_sent_at is None
    if change == "repeat":
        assert row.due_at == original_due


@pytest.mark.asyncio
async def test_early_recurring_push_advances_from_delivered_occurrence(schedule_sql):
    sync_session, session = schedule_sql
    row = _todo(sync_session, recurring=True)
    row.notification_sent_at = None
    sync_session.commit()
    due = row.due_at
    await push.finalize_push_deliveries(
        session,
        [push.OutboundPush(message={}, todos=[row])],
        [True],
        now=due - timedelta(minutes=10),
    )
    sync_session.refresh(row)
    assert row.due_at == due + timedelta(days=1)
    assert row.notification_sent_at is None


@pytest.mark.asyncio
async def test_local_reminder_list_advances_and_returns_persisted_schedule(schedule_sql):
    sync_session, session = schedule_sql
    row = _todo(sync_session, recurring=True, due=datetime.now(UTC) - timedelta(days=4))
    items, _cursor = await crud.list_todos_page(
        session,
        SimpleNamespace(id=row.user_id, timezone="UTC", push_notifications_enabled=False),
    )
    assert items[0].due_at > datetime.now(UTC)
    sync_session.refresh(row)
    assert items[0].due_at == row.due_at
    assert row.notification_sent_at is None


@pytest.mark.asyncio
async def test_schedule_pages_are_owned_and_stable_for_equal_timestamps(schedule_sql):
    from uuid import UUID

    sync_session, session = schedule_sql
    owner_id = uuid4()
    created = datetime(2026, 9, 4, tzinfo=UTC)
    for number in [3, 2, 1, 0]:
        sync_session.add(
            TodoItem(
                id=UUID(f"abcdef00-0000-0000-0000-{number:012x}"),
                user_id=owner_id if number else uuid4(),
                content="Same time",
                topic="Reminders",
                checked=False,
                due_at=created,
                created_at=created,
            )
        )
    sync_session.commit()
    pages = [await todos_repo.list_for_user(session, owner_id, limit=1, offset=i) for i in range(3)]
    assert [page[0].id.int & 0xFF for page in pages] == [1, 2, 3]


@pytest.mark.asyncio
async def test_chat_weekday_reschedule_uses_effective_monday_due(schedule_sql):
    sync_session, session = schedule_sql
    row = _todo(sync_session, due=datetime(2026, 9, 7, 8, tzinfo=UTC))
    row.recurrence_rule = "weekdays"
    sync_session.commit()
    await actions.apply_todo_actions(
        session,
        user_id=row.user_id,
        user_timezone="UTC",
        actions=[
            TodoActionItem(
                action="set_due",
                topic=row.topic,
                content=row.content,
                due_at=datetime(2026, 9, 5, 8, tzinfo=UTC),
            )
        ],
    )
    sync_session.refresh(row)
    assert row.due_at == datetime(2026, 9, 7, 8, tzinfo=UTC)
    assert row.notification_sent_at is not None
