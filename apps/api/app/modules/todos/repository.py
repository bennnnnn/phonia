from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import TodoItem
from app.modules.todos import write_log

DEFAULT_TOPIC = "General"
OPEN_CONTENT_DUE_UNIQUE = "uq_todo_open_content_due"


def is_open_content_due_conflict(exc: BaseException) -> bool:
    """True when INSERT/UPDATE hit the open dated (user, title, due) unique."""
    orig = getattr(exc, "orig", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if constraint == OPEN_CONTENT_DUE_UNIQUE:
        return True
    blob = f"{exc} {orig if orig is not None else ''}".lower()
    return OPEN_CONTENT_DUE_UNIQUE in blob


async def list_due_soon(
    session: AsyncSession,
    user_id: UUID,
    *,
    before_utc: datetime,
) -> list[TodoItem]:
    """Open todos with due_at at or before *before_utc*, soonest first."""
    result = await session.execute(
        select(TodoItem)
        .where(
            TodoItem.user_id == user_id,
            TodoItem.checked.is_(False),
            TodoItem.due_at.isnot(None),
            TodoItem.due_at <= before_utc,
        )
        .order_by(TodoItem.due_at.asc())
        .limit(5)
    )
    return list(result.scalars().all())


async def list_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int = 1000,
    offset: int = 0,
    populate_existing: bool = False,
) -> list[TodoItem]:
    result = await session.execute(
        select(TodoItem)
        .where(TodoItem.user_id == user_id)
        .order_by(
            TodoItem.topic.asc(),
            TodoItem.sort_order.asc().nulls_last(),
            TodoItem.checked.asc(),
            TodoItem.created_at.desc(),
            TodoItem.id.asc(),
        )
        .limit(limit)
        .offset(offset)
        .execution_options(populate_existing=populate_existing)
    )
    return list(result.scalars().all())


async def list_after_id(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor: UUID | None = None,
    completed_since: datetime | None = None,
) -> list[TodoItem]:
    """Traverse immutable IDs so edits cannot move rows across page boundaries.

    With ``completed_since``, completed rows last changed before it are left out.
    """
    statement = select(TodoItem).where(TodoItem.user_id == user_id)
    if completed_since is not None:
        statement = statement.where(
            or_(TodoItem.checked.is_(False), TodoItem.updated_at >= completed_since)
        )
    if cursor is not None:
        statement = statement.where(TodoItem.id > cursor)
    result = await session.execute(statement.order_by(TodoItem.id.asc()).limit(limit))
    return list(result.scalars().all())


async def has_completed_before(session: AsyncSession, user_id: UUID, before: datetime) -> bool:
    """The user has a completed row last changed before ``before``."""
    statement = select(
        exists().where(
            TodoItem.user_id == user_id,
            TodoItem.checked.is_(True),
            TodoItem.updated_at < before,
        )
    )
    return bool((await session.execute(statement)).scalar())


async def list_by_ids(session: AsyncSession, user_id: UUID, ids: list[UUID]) -> list[TodoItem]:
    """Reload a selected page after schedule writes without filling deleted slots."""
    result = await session.execute(
        select(TodoItem)
        .where(TodoItem.user_id == user_id, TodoItem.id.in_(ids))
        .order_by(TodoItem.id.asc())
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def next_sort_order(
    session: AsyncSession, user_id: UUID, topic: str, *, list_only: bool = True
) -> int:
    normalized = topic.strip() or DEFAULT_TOPIC
    stmt = select(func.max(TodoItem.sort_order)).where(
        TodoItem.user_id == user_id,
        TodoItem.topic == normalized,
    )
    if list_only:
        stmt = stmt.where(TodoItem.due_at.is_(None))
    result = await session.execute(stmt)
    current = result.scalar()
    return int(current or 0) + 1


async def get_by_id(session: AsyncSession, todo_id: UUID, user_id: UUID) -> TodoItem | None:
    result = await session.execute(
        select(TodoItem).where(TodoItem.id == todo_id, TodoItem.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_open_dated_duplicate(
    session: AsyncSession,
    user_id: UUID,
    *,
    content: str,
    due_at: datetime,
) -> TodoItem | None:
    """Open reminder with the same case-insensitive title and due instant."""
    result = await session.execute(
        select(TodoItem).where(
            TodoItem.user_id == user_id,
            func.lower(TodoItem.content) == content.strip().lower(),
            TodoItem.due_at == due_at,
            TodoItem.checked.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    content: str,
    topic: str = DEFAULT_TOPIC,
    chat_id: UUID | None = None,
    due_at: datetime | None = None,
    recurrence_rule: str | None = None,
    sort_order: int | None = None,
    commit: bool = True,
) -> TodoItem:
    normalized_topic = topic.strip() or DEFAULT_TOPIC
    resolved_sort = sort_order
    if resolved_sort is None and due_at is None:
        resolved_sort = await next_sort_order(session, user_id, normalized_topic)
    todo = TodoItem(
        user_id=user_id,
        content=content.strip(),
        topic=normalized_topic,
        chat_id=chat_id,
        due_at=due_at,
        recurrence_rule=recurrence_rule,
        sort_order=resolved_sort,
    )
    planned = write_log.planned()
    if planned is not None:
        return write_log.plan_create(planned, todo)
    session.add(todo)
    if commit:
        await session.commit()
        await session.refresh(todo)
    else:
        await session.flush()
    return todo


async def update(
    session: AsyncSession, todo: TodoItem, *, commit: bool = True, **fields: Any
) -> TodoItem:
    if "due_at" in fields and fields["due_at"] != todo.due_at:
        fields["notification_sent_at"] = None
        fields["email_sent_at"] = None
        # Its reminder instant reads when the time was set; no other edit moves it.
        fields["due_set_at"] = datetime.now(UTC)
    changes: dict[str, Any] = {}
    for key, value in fields.items():
        if hasattr(todo, key):
            if key == "topic" and isinstance(value, str):
                value = value.strip() or DEFAULT_TOPIC
            changes[key] = value
    planned = write_log.planned()
    if planned is not None:
        return cast(TodoItem, write_log.plan_update(planned, todo, changes))
    for key, value in changes.items():
        setattr(todo, key, value)
    if commit:
        await session.commit()
        await session.refresh(todo)
    return todo


async def delete_by_id(
    session: AsyncSession, todo_id: UUID, user_id: UUID, *, commit: bool = True
) -> bool:
    planned = write_log.planned()
    if planned is not None:
        todo = await get_by_id(session, todo_id, user_id)
        return write_log.plan_delete(planned, todo_id, todo)
    result = cast(
        CursorResult[Any],
        await session.execute(
            delete(TodoItem).where(TodoItem.id == todo_id, TodoItem.user_id == user_id)
        ),
    )
    if commit:
        await session.commit()
    return result.rowcount > 0


async def delete_all_for_user(session: AsyncSession, user_id: UUID) -> None:
    """Every to-do of the user; no commit."""
    await session.execute(delete(TodoItem).where(TodoItem.user_id == user_id))
