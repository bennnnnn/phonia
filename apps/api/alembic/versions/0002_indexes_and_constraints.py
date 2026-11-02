"""Add indexes and unique constraint for memory upsert

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── messages ──────────────────────────────────────────────────────────────
    # Primary lookup: all messages for a chat, ordered by time (covers list_recent,
    # list_all, get_last, get_last_user, delete_after, count_for_chat)
    op.create_index("ix_messages_chat_created", "messages", ["chat_id", "created_at"])

    # Covers get_last_user (chat_id + role filter)
    op.create_index("ix_messages_chat_role", "messages", ["chat_id", "role"])

    # ── chats ─────────────────────────────────────────────────────────────────
    # All chat lookups for a user (list_for_user, plus user-ownership checks)
    op.create_index("ix_chats_user_updated", "chats", ["user_id", "updated_at"])

    # ── memories ──────────────────────────────────────────────────────────────
    # All memories for a user
    op.create_index("ix_memories_user_updated", "memories", ["user_id", "updated_at"])

    # Unique constraint enables single-query ON CONFLICT upsert
    op.create_unique_constraint(
        "uq_memories_user_type_text",
        "memories",
        ["user_id", "type", "text"],
    )

    # ── usage_daily ───────────────────────────────────────────────────────────
    # PK is (user_id, date) — already indexed, nothing extra needed


def downgrade() -> None:
    op.drop_constraint("uq_memories_user_type_text", "memories", type_="unique")
    op.drop_index("ix_memories_user_updated", "memories")
    op.drop_index("ix_chats_user_updated", "chats")
    op.drop_index("ix_messages_chat_role", "messages")
    op.drop_index("ix_messages_chat_created", "messages")
