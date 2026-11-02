"""Chat-history message chunks.

Attachment rows live in the attachments module (``app.modules.attachments.models``).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MessageChunk(Base):
    __tablename__ = "message_chunks"
    __table_args__ = (
        # Also serves a message's chunks (``message_id`` leads).
        UniqueConstraint("message_id", "chunk_index", name="uq_message_chunks_message_index"),
        Index("ix_message_chunks_user_chat", "user_id", "chat_id"),
        # A search ranks the user's newest chunks (migration 0118); a global vector
        # index cannot serve a per-user search.
        Index("ix_message_chunks_user_created", "user_id", "created_at"),
        # A chat delete (FK CASCADE), migration 0116.
        Index("ix_message_chunks_chat", "chat_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Not loaded with the row (search ranks in SQL); ``embedding_json`` is no longer
    # written and a later contract migration drops it.
    embedding_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, deferred=True, deferred_raiseload=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True, deferred=True, deferred_raiseload=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
