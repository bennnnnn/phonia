from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.modules.memory.topics import (
    AREA_SUMMARY_MAX,
    AREA_TITLE_MAX,
    TOPIC_KEY_MAX,
    TYPE_DEFAULT_TOPIC,
)

if TYPE_CHECKING:
    from app.models.orm.user import User


def _default_topic(context: DefaultExecutionContext) -> str:
    # SQLAlchemy leaves get_current_parameters unannotated.
    memory_type = context.get_current_parameters().get("type")  # type: ignore[no-untyped-call]
    return TYPE_DEFAULT_TOPIC.get(str(memory_type), "notes")


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_updated", "user_id", "updated_at"),
        Index("ix_memories_user_status", "user_id", "status"),
        Index("ix_memories_user_type_status", "user_id", "type", "status"),
        Index("ix_memories_user_topic_status", "user_id", "topic", "status"),
        # Message, chat and fact deletes (FK SET NULL): without these each deleted row
        # scanned the whole table (migration 0116).
        Index(
            "ix_memories_source_message",
            "source_message_id",
            postgresql_where=sql_text("source_message_id IS NOT NULL"),
        ),
        Index(
            "ix_memories_source_chat",
            "source_chat_id",
            postgresql_where=sql_text("source_chat_id IS NOT NULL"),
        ),
        Index(
            "ix_memories_superseded_by",
            "superseded_by_id",
            postgresql_where=sql_text("superseded_by_id IS NOT NULL"),
        ),
        CheckConstraint(
            "type IN ('profile', 'preference', 'project', 'fact', 'focus')",
            name="ck_memories_type",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded', 'muted')",
            name="ck_memories_status",
        ),
        CheckConstraint(
            "sensitivity IN ("
            "'normal', 'health', 'finance', 'legal', "
            "'relationship', 'identity', 'highly_sensitive'"
            ")",
            name="ck_memories_sensitivity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    # The memory document this fact belongs to (see topics.py). Inserts that
    # do not name one get the default for their type.
    topic: Mapped[str] = mapped_column(
        String(TOPIC_KEY_MAX),
        nullable=False,
        default=_default_topic,
        server_default="notes",
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default="active"
    )
    sensitivity: Mapped[str] = mapped_column(
        String, nullable=False, default="normal", server_default="normal"
    )
    importance: Mapped[float | None] = mapped_column(Numeric(3, 2))
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Neither vector copy is loaded with the row: recall ranks in SQL
    # (``repository.list_scored_for_user``), and a read of either raises instead of
    # quietly fetching ~50 KB a fact. ``embedding_json`` is no longer written; a later
    # contract migration drops it.
    embedding_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, deferred=True, deferred_raiseload=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True, deferred=True, deferred_raiseload=True
    )
    # Hash of the text this embedding was actually computed from — lets
    # extraction/consolidation detect "embedding is stale relative to text"
    # reliably across passes, not just within one call. See migration 0057.
    embedding_text_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chats.id", ondelete="SET NULL")
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="memories")


class MemoryArea(Base):
    """Title and summary of one area document (``area:<slug>`` facts)."""

    __tablename__ = "memory_areas"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_memory_areas_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(TOPIC_KEY_MAX), nullable=False)
    title: Mapped[str] = mapped_column(String(AREA_TITLE_MAX), nullable=False)
    summary: Mapped[str] = mapped_column(
        String(AREA_SUMMARY_MAX), nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
