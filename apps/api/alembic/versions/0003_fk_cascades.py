"""FK cascade rules and confidence precision

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("messages_chat_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_chat_id_fkey",
        "messages",
        "chats",
        ["chat_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("memories_source_chat_id_fkey", "memories", type_="foreignkey")
    op.create_foreign_key(
        "memories_source_chat_id_fkey",
        "memories",
        "chats",
        ["source_chat_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "memories",
        "confidence",
        existing_type=sa.Numeric(),
        type_=sa.Numeric(3, 2),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "memories",
        "confidence",
        existing_type=sa.Numeric(3, 2),
        type_=sa.Numeric(),
        existing_nullable=True,
    )

    op.drop_constraint("memories_source_chat_id_fkey", "memories", type_="foreignkey")
    op.create_foreign_key(
        "memories_source_chat_id_fkey",
        "memories",
        "chats",
        ["source_chat_id"],
        ["id"],
    )

    op.drop_constraint("messages_chat_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_chat_id_fkey",
        "messages",
        "chats",
        ["chat_id"],
        ["id"],
    )
