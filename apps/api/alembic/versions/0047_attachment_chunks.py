"""Attachment text chunks for pgvector RAG

Revision ID: 0044_attachment_chunks
Revises: 0043
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0047_attachment_chunks"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "attachment_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "attachment_id",
            sa.Uuid(),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_id", sa.Uuid(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        f"ALTER TABLE attachment_chunks ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIM})"
    )
    op.create_index(
        "ix_attachment_chunks_user_chat",
        "attachment_chunks",
        ["user_id", "chat_id"],
    )
    op.create_index(
        "ix_attachment_chunks_attachment",
        "attachment_chunks",
        ["attachment_id"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_attachment_chunks_embedding "
        "ON attachment_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_attachment_chunks_embedding")
    op.drop_index("ix_attachment_chunks_attachment", table_name="attachment_chunks")
    op.drop_index("ix_attachment_chunks_user_chat", table_name="attachment_chunks")
    op.drop_table("attachment_chunks")
