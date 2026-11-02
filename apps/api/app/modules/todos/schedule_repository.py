"""Conditional writes for delayed recurring To-do catch-up and delivery results."""

from datetime import datetime
from typing import Any, cast

from sqlalchemy import and_, case, func, or_, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.orm import TodoItem
from app.modules.todos.occurrences import TodoScheduleSnapshot


def _matches(snapshot: TodoScheduleSnapshot) -> ColumnElement[bool]:
    return and_(
        TodoItem.id == snapshot.id,
        TodoItem.user_id == snapshot.user_id,
        TodoItem.content == snapshot.content,
        TodoItem.due_at == snapshot.due_at,
        TodoItem.recurrence_rule == snapshot.recurrence_rule,
        TodoItem.checked == snapshot.checked,
        TodoItem.notification_sent_at == snapshot.notification_sent_at,
    )


async def update_schedule_if_current(
    session: AsyncSession, snapshot: TodoScheduleSnapshot, **fields: Any
) -> bool:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(TodoItem)
            .where(_matches(snapshot))
            .values(**fields)
            .execution_options(synchronize_session=False)
        ),
    )
    return result.rowcount > 0


async def advance_schedules_if_current(
    session: AsyncSession, advances: list[tuple[TodoScheduleSnapshot, datetime]]
) -> None:
    """Advance a fetched page in one statement without overwriting changed rows."""
    if not advances:
        return
    await session.execute(
        update(TodoItem)
        .where(or_(*(_matches(snapshot) for snapshot, _ in advances)))
        .values(
            due_at=case({snapshot.id: due for snapshot, due in advances}, value=TodoItem.id),
            due_set_at=func.now(),
            notification_sent_at=None,
            email_sent_at=None,
        )
        .execution_options(synchronize_session=False)
    )
