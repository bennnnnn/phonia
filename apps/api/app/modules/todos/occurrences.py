"""A dated to-do as a reminder channel read it: the copy a conditional write compares.

A channel reads a page of due to-dos, lets the read transaction go before the provider
call, and afterwards changes only the occurrence it sent. A to-do edited, completed or
moved in between no longer matches its copy and is left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.models.orm import TodoItem


@dataclass(frozen=True)
class TodoEmailSnapshot:
    id: UUID
    user_id: UUID
    content: str
    due_at: datetime | None
    recurrence_rule: str | None
    checked: bool
    email_sent_at: datetime | None

    @classmethod
    def from_todo(cls, todo: TodoItem) -> TodoEmailSnapshot:
        return cls(
            todo.id,
            todo.user_id,
            todo.content,
            todo.due_at,
            todo.recurrence_rule,
            todo.checked,
            todo.email_sent_at,
        )


@dataclass(frozen=True)
class TodoScheduleSnapshot:
    id: UUID
    user_id: UUID
    content: str
    due_at: datetime | None
    recurrence_rule: str | None
    checked: bool
    notification_sent_at: datetime | None

    @classmethod
    def from_todo(cls, todo: TodoItem) -> TodoScheduleSnapshot:
        return cls(
            todo.id,
            todo.user_id,
            todo.content,
            todo.due_at,
            todo.recurrence_rule,
            todo.checked,
            todo.notification_sent_at,
        )
