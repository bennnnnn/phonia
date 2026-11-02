"""Attachment and attachment-chunk rows. Table names are unchanged."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# The original_filename column's width: the upload schema and every writer cut to it.
ORIGINAL_FILENAME_MAX_CHARS = 255


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_user", "user_id"),
        # Message delete (FK SET NULL) and per-message reads.
        Index(
            "ix_attachments_message",
            "message_id",
            postgresql_where=text("message_id IS NOT NULL"),
        ),
        # The orphan reaper's scan of unlinked rows by age.
        Index(
            "ix_attachments_unlinked_created",
            "created_at",
            postgresql_where=text("message_id IS NULL"),
        ),
        CheckConstraint(
            "source IN ('upload', 'generated', 'search')", name="ck_attachments_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="upload", default="upload"
    )
    original_filename: Mapped[str | None] = mapped_column(
        String(ORIGINAL_FILENAME_MAX_CHARS), nullable=True
    )
    # Set once bytes have been verified against the declared type/size.
    # Subsequent /file and /url reads skip the full-object download.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # False for send-clones of a Library item (same file, new chat) and for
    # reference-photo lookup copies (chat-only; not listed in Library).
    library_visible: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default="true",
    )
    # First time a message linked this row. An upload never linked is a composer
    # draft: kept out of Library and reaped; one whose chat was deleted stays.
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # JSON: via_ocr, max_pages, max_chars, page_capped, char_capped — set after index.
    index_coverage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttachmentChunk(Base):
    __tablename__ = "attachment_chunks"
    __table_args__ = (
        Index("ix_attachment_chunks_user_chat", "user_id", "chat_id"),
        Index("ix_attachment_chunks_attachment", "attachment_id"),
        # Chat delete (FK CASCADE) looks chunks up by chat alone.
        Index("ix_attachment_chunks_chat", "chat_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=True
    )
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
