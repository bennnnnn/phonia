"""Reminder writes from chat that wait for the user's tap.

Inside ``recording()`` the To-do repository writes nothing. ``create``,
``update`` and ``delete_by_id`` add a ``PlannedWrite`` here and hand back an
unsaved row, so the reminder rules run unchanged and the reply can show what
they would do. ``proposals.confirm_proposal`` makes the writes on the tap.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from app.modules.todos.models import TodoItem

WriteKind = Literal["create", "update", "delete"]

# Columns copied onto the unsaved row an update hands back.
_ROW_FIELDS = (
    "id",
    "user_id",
    "chat_id",
    "content",
    "topic",
    "checked",
    "due_at",
    "recurrence_rule",
    "sort_order",
    "notification_sent_at",
    "email_sent_at",
    "source",
    "created_at",
    "updated_at",
    "due_set_at",
)
_CREATE_FIELDS = (
    "content",
    "topic",
    "chat_id",
    "due_at",
    "recurrence_rule",
    "sort_order",
)


@dataclass
class PlannedWrite:
    """One row write. ``due_at``, ``repeat`` and ``topic`` are the row after it."""

    kind: WriteKind
    todo_id: UUID
    title: str
    fields: dict[str, Any] = field(default_factory=dict)
    due_at: datetime | None = None
    repeat: str | None = None
    topic: str | None = None


_planned: ContextVar[list[PlannedWrite] | None] = ContextVar("todo_planned_writes", default=None)


@contextmanager
def recording() -> Iterator[list[PlannedWrite]]:
    """Record To-do writes made inside this block instead of making them."""
    writes: list[PlannedWrite] = []
    token = _planned.set(writes)
    try:
        yield writes
    finally:
        _planned.reset(token)


def planned() -> list[PlannedWrite] | None:
    """The writes being recorded, or None when writes go to the database."""
    return _planned.get()


def _find(writes: list[PlannedWrite], kind: WriteKind, todo_id: UUID) -> PlannedWrite | None:
    return next((w for w in writes if w.kind == kind and w.todo_id == todo_id), None)


def _after(write: PlannedWrite, row: Any) -> None:
    write.due_at = getattr(row, "due_at", None)
    write.repeat = getattr(row, "recurrence_rule", None)
    write.topic = getattr(row, "topic", None)


def plan_create(writes: list[PlannedWrite], todo: TodoItem) -> TodoItem:
    now = datetime.now(UTC)
    todo.id = uuid4()
    todo.checked = False
    todo.created_at = now
    todo.updated_at = now
    todo.due_set_at = now
    write = PlannedWrite(
        kind="create",
        todo_id=todo.id,
        title=todo.content,
        fields={name: getattr(todo, name) for name in _CREATE_FIELDS},
    )
    _after(write, todo)
    writes.append(write)
    return todo


def plan_update(writes: list[PlannedWrite], todo: Any, changes: dict[str, Any]) -> Any:
    created = _find(writes, "create", todo.id)
    if created is not None:
        # A row planned this turn: fold the change into its create.
        for key, value in changes.items():
            setattr(todo, key, value)
            if key in _CREATE_FIELDS:
                created.fields[key] = value
        _after(created, todo)
        return todo
    row = TodoItem(**{name: getattr(todo, name, None) for name in _ROW_FIELDS})
    for key, value in changes.items():
        setattr(row, key, value)
    write = _find(writes, "update", todo.id)
    if write is None:
        write = PlannedWrite(kind="update", todo_id=todo.id, title=str(todo.content or ""))
        writes.append(write)
    write.fields.update(changes)
    _after(write, row)
    return row


def plan_delete(writes: list[PlannedWrite], todo_id: UUID, todo: Any | None) -> bool:
    created = _find(writes, "create", todo_id)
    if created is not None:
        writes.remove(created)
        return True
    if todo is None:
        return False
    writes[:] = [w for w in writes if w.todo_id != todo_id]
    write = PlannedWrite(kind="delete", todo_id=todo_id, title=str(todo.content or ""))
    _after(write, todo)
    writes.append(write)
    return True
