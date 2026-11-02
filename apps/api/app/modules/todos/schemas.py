"""Request and response schemas for to-dos with optional due dates."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.schemas.page import Page
from app.models.schemas.text import UserText

# The longest to-do text; the chat and voice readers cut a title to it too.
TODO_TEXT_MAX_CHARS = 1000

RecurrenceRule = Literal["daily", "weekdays", "weekly", "monthly"]


class TodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, title="TodoOut")

    id: UUID
    content: str
    topic: str
    checked: bool
    due_at: datetime | None = None
    recurrence_rule: RecurrenceRule | None = None
    sort_order: int | None = None
    chat_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    # When its reminder goes out (the user's lead time, after their quiet hours), the moment
    # push sends it and the one the phone schedules its own alert at; null: none.
    notify_at: datetime | None = None

    @field_validator("recurrence_rule", mode="before")
    @classmethod
    def _coerce_recurrence_rule(cls, value: object) -> RecurrenceRule | None:
        if value in ("daily", "weekdays", "weekly", "monthly"):
            return value
        return None


class ReminderPreviewOut(BaseModel):
    model_config = ConfigDict(title="ReminderPreviewOut")

    # When the reminder of a to-do with that due time would go out if saved now; null: none.
    notify_at: datetime | None = None


class TodoPageOut(Page[TodoOut]):
    # Asked for recent completed rows only: the first page says whether older ones exist.
    older_completed: bool = False


class TodoCreate(BaseModel):
    model_config = ConfigDict(title="TodoCreate")

    content: UserText = Field(min_length=1, max_length=TODO_TEXT_MAX_CHARS)
    topic: UserText = Field(default="General", min_length=1, max_length=200)
    chat_id: UUID | None = None
    due_at: datetime | None = None
    recurrence_rule: RecurrenceRule | None = None

    @field_validator("content")
    @classmethod
    def content_cannot_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content cannot be blank")
        return value

    @model_validator(mode="after")
    def recurrence_needs_due(self) -> Self:
        if self.recurrence_rule is not None and self.due_at is None:
            raise ValueError("recurrence_rule requires due_at")
        return self


class TodoUpdate(BaseModel):
    model_config = ConfigDict(title="TodoUpdate")

    content: UserText | None = Field(default=None, min_length=1, max_length=TODO_TEXT_MAX_CHARS)
    topic: UserText | None = Field(default=None, min_length=1, max_length=200)
    checked: bool | None = None
    due_at: datetime | None = None
    recurrence_rule: RecurrenceRule | None = None
    sort_order: int | None = Field(default=None, ge=0)

    @field_validator("content", "topic", "checked")
    @classmethod
    def supplied_value_cannot_be_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("content")
    @classmethod
    def content_cannot_be_blank(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("content cannot be blank")
        return value

    @model_validator(mode="after")
    def recurrence_needs_due(self) -> Self:
        if (
            self.recurrence_rule is not None
            and "due_at" in self.model_fields_set
            and self.due_at is None
        ):
            raise ValueError("recurrence_rule requires due_at")
        return self


class TodoActionItem(BaseModel):
    model_config = ConfigDict(title="TodoActionItem")

    action: Literal[
        "add",
        "complete",
        "uncheck",
        "delete",
        "set_due",
        "clear_due",
    ]
    # Creates may omit a topic; the server selects General or Reminders from due_at.
    topic: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=TODO_TEXT_MAX_CHARS)
    due_at: datetime | None = None
    recurrence_rule: RecurrenceRule | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if not self.content.strip():
            raise ValueError("content is required for this action")
        if self.action == "set_due" and self.due_at is None:
            raise ValueError("set_due requires due_at")
        if self.recurrence_rule is not None and self.due_at is None:
            raise ValueError("recurrence_rule requires due_at")
        if self.action == "add":
            return self
        if not self.topic.strip():
            raise ValueError("topic is required for this action")
        return self
