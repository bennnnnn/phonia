import logging
from datetime import datetime
from typing import Literal, Self, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.models.schemas.common import (
    MemoryOpKind,
    MemorySensitivity,
    MemoryStatus,
    MemoryType,
)
from app.models.schemas.text import UserText
from app.modules.memory.topics import parse_topic, topic_memory_type

_logger = logging.getLogger(__name__)

MEMORY_TEXT_MAX_LENGTH = 4000
# A persisted section may include the server's "As of YYYY-MM-DD: " prefix.


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: MemoryType
    topic: str = "notes"
    text: str
    confidence: float | None
    status: MemoryStatus = "active"
    sensitivity: MemorySensitivity = "normal"
    importance: float | None = None
    last_confirmed_at: datetime | None = None
    source_chat_id: UUID | None = None
    source_chat_title: str | None = None
    source_message_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class MemoryUpdate(BaseModel):
    text: UserText | None = Field(default=None, min_length=1, max_length=MEMORY_TEXT_MAX_LENGTH)
    # "superseded" is the server's own state: a fact set to it vanished for good.
    status: Literal["active", "muted"] | None = None


class MemorySectionItem(BaseModel):
    """Legacy whole-section rewrite (pair-merge still uses summary + confidence)."""

    type: MemoryType
    summary: str = Field(default="", max_length=MEMORY_TEXT_MAX_LENGTH)
    confidence: float = Field(ge=0.0, le=1.0)


_MEMORY_TYPES = frozenset(get_args(MemoryType))
# Words models use for a type that is not one ("goal" is what the goals topic stores).
_TYPE_WORDS = {"goal": "focus", "projects": "project", "preferences": "preference"}


def _op_type(raw: object, topic: object) -> str:
    """The op's type: as given when valid, else its topic's, else what the word means."""
    word = raw.strip().casefold() if isinstance(raw, str) else ""
    if word in _MEMORY_TYPES:
        return word
    named = parse_topic(topic) if isinstance(topic, str) else None
    if named is not None:
        return topic_memory_type(named)
    as_topic = parse_topic(word)
    return _TYPE_WORDS.get(word) or (topic_memory_type(as_topic) if as_topic else "fact")


class MemoryFactOp(BaseModel):
    op: MemoryOpKind
    # Missing or unknown ("goal") follows the topic, so the fact is not dropped.
    type: MemoryType = "fact"
    text: str = Field(default="", max_length=MEMORY_TEXT_MAX_LENGTH)
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: MemorySensitivity = "normal"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    match_text: str | None = Field(default=None, max_length=MEMORY_TEXT_MAX_LENGTH)
    # The memory document (topics.py). Unknown keys fall back to the type's
    # default, and long titles are trimmed, so neither fails the whole op.
    topic: str | None = None
    topic_title: str | None = None
    topic_summary: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _typed(cls, data: object) -> object:
        if isinstance(data, dict):
            return {**data, "type": _op_type(data.get("type"), data.get("topic"))}
        return data


MEMORY_REPLY_MAX_LENGTH = 400


class MemoryFactUpdateResult(BaseModel):
    ops: list[MemoryFactOp] = Field(default_factory=list)
    # A direct memory edit also says, in a sentence, what changed.
    reply: str = Field(default="", max_length=MEMORY_REPLY_MAX_LENGTH)
    # Ops the model wrote that did not validate (salvage_partial): never in the schema.
    _dropped: int = PrivateAttr(default=0)

    @property
    def dropped(self) -> int:
        return self._dropped

    @classmethod
    def salvage_partial(cls, data: dict[str, object]) -> Self | None:
        """The ops that validate (and the reply), when the model's whole reply does not.

        ``gateways/structured_completion`` asks any schema that has this.
        """
        raw_ops = data.get("ops")
        if not isinstance(raw_ops, list):
            return None
        valid: list[MemoryFactOp] = []
        for item in raw_ops:
            if not isinstance(item, dict):
                continue
            try:
                valid.append(MemoryFactOp.model_validate(item))
            except Exception:
                _logger.debug("Skipping invalid memory fact op", exc_info=True)
        raw_reply = data.get("reply")
        reply = raw_reply.strip()[:MEMORY_REPLY_MAX_LENGTH] if isinstance(raw_reply, str) else ""
        if not valid and not reply:
            return None
        result = cls(ops=valid, reply=reply)
        result._dropped = len(raw_ops) - len(valid)
        return result


class MemoryDocumentOut(BaseModel):
    """One memory document: every fact with the same topic."""

    key: str
    group: Literal["you", "topics", "areas"]
    title: str
    summary: str
    updated_at: datetime | None
    facts: list[MemoryOut]


class MemoryDocumentsOut(BaseModel):
    documents: list[MemoryDocumentOut]
    # True while memory reads the user's recent chats for the first time.
    scanning: bool = False


MEMORY_INSTRUCTION_MAX_LENGTH = 500


class MemoryInstructIn(BaseModel):
    instruction: UserText = Field(min_length=1, max_length=MEMORY_INSTRUCTION_MAX_LENGTH)
    # The document the user is looking at, if any.
    topic: UserText | None = Field(default=None, max_length=64)


class MemoryInstructOut(BaseModel):
    reply: str
    applied: int
    # Edits the model proposed that could not be read or did not land.
    dropped: int = 0
    documents: list[MemoryDocumentOut]
