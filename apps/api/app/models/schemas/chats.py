from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import normalize_stored_chat_title
from app.models.schemas.common import MessageFeedback, MessageRole
from app.models.schemas.text import UserText


class ChatRename(BaseModel):
    title: UserText = Field(min_length=1, max_length=80)


class PinUpdate(BaseModel):
    pinned: bool


# The most chats one bulk request may name; the phone sends a longer selection in parts.
BULK_CHAT_LIMIT = 200


class ChatBulkAction(BaseModel):
    """Delete many chats in one request (the drawer's selection)."""

    action: Literal["delete"]
    chat_ids: list[UUID] = Field(min_length=1, max_length=BULK_CHAT_LIMIT)


class ChatBulkOut(BaseModel):
    """The chats the action changed: the user's own, still there. Any other id was skipped."""

    changed: list[UUID]


class FeedbackUpdate(BaseModel):
    feedback: MessageFeedback | None = None


class EmailDraftUpdate(BaseModel):
    """Structured EmailCard fields — rewritten into the first ```email fence only."""

    to: UserText | None = Field(default=None, max_length=320)
    subject: UserText | None = Field(default=None, max_length=300)
    body: UserText = Field(default="", max_length=20_000)

    @field_validator("to", "subject", mode="before")
    @classmethod
    def blank_header_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    pinned: bool = False
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def sanitize_title(self) -> Self:
        self.title = normalize_stored_chat_title(self.title)
        return self


class ChatListOut(BaseModel):
    pinned: list[ChatOut] = Field(default_factory=list)
    today: list[ChatOut] = Field(default_factory=list)
    yesterday: list[ChatOut] = Field(default_factory=list)
    last_7_days: list[ChatOut] = Field(default_factory=list)
    this_month: list[ChatOut] = Field(default_factory=list)
    older: list[ChatOut] = Field(default_factory=list)
    # The dated groups page by keyset: pass it back as ``cursor`` for older chats.
    next_cursor: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: MessageRole
    content: str
    model: str | None
    feedback: MessageFeedback | None = None
    # A reply that did not finish: stopped by the user, or cut off.
    completion: Literal["interrupted", "user_stop"] | None = None
    related_prompts: list[str] | None = None
    created_at: datetime


class MessagePageOut(BaseModel):
    messages: list[MessageOut]
    # Older messages precede the page.
    has_more: bool
    # Newer messages follow it: a page read ``around`` or ``after`` a message.
    has_more_after: bool = False


class ChatMessageRequest(BaseModel):
    """A message or regenerate body."""

    client_timezone: UserText | None = Field(default=None, max_length=64)
    # Cap the body — without it a client can push a multi-MB prompt that
    # bloats the DB row and memory-extraction job. 32k chars is well beyond
    # any realistic chat turn. UserText: a NUL used to fail the background
    # user-row insert only after the reply streamed, so the turn went unbilled.
    content: UserText = Field(default="", max_length=32_000)
    # Cap per turn — unbounded lists let a client force huge DB/RAG work.
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)
    # The phone's name for this message, the same on every send of it (a resend
    # after a dead socket, the SSE fallback, Retry): the server runs one turn per
    # name (``modules/chat/client_message.py``). Regenerate ignores it.
    client_message_id: UUID | None = None


class SearchResultItem(BaseModel):
    match_type: Literal["message", "title"] = "message"
    message_id: UUID | None = None
    chat_id: UUID
    chat_title: str | None
    content: str
    role: str
    created_at: datetime

    @model_validator(mode="after")
    def sanitize_chat_title(self) -> Self:
        self.chat_title = normalize_stored_chat_title(self.chat_title)
        return self
