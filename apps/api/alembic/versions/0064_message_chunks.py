"""Message text chunks for chat-history pgvector RAG

Revision ID: 0064_message_chunks
Revises: 0063_msg_chat_created_id_idx
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0064_message_chunks"
down_revision: Union[str, None] = "0063_msg_chat_created_id_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "message_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_id", sa.Uuid(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("message_id", "chunk_index", name="uq_message_chunks_message_index"),
    )
    op.execute(
        f"ALTER TABLE message_chunks ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIM})"
    )
    op.create_index("ix_message_chunks_user", "message_chunks", ["user_id"])
    op.create_index("ix_message_chunks_user_chat", "message_chunks", ["user_id", "chat_id"])
    op.create_index("ix_message_chunks_message", "message_chunks", ["message_id"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_message_chunks_embedding "
        "ON message_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_message_chunks_embedding")
    op.drop_index("ix_message_chunks_message", table_name="message_chunks")
    op.drop_index("ix_message_chunks_user_chat", table_name="message_chunks")
    op.drop_index("ix_message_chunks_user", table_name="message_chunks")
    op.drop_table("message_chunks")
