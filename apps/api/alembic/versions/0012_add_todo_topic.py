"""Add topic column to todo_items

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-27
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "todo_items",
        sa.Column("topic", sa.String(length=200), server_default="General", nullable=False),
    )
    op.execute("UPDATE todo_items SET topic = 'General' WHERE topic IS NULL")
    op.create_index("ix_todo_user_topic", "todo_items", ["user_id", "topic"])


def downgrade() -> None:
    op.drop_index("ix_todo_user_topic", table_name="todo_items")
    op.drop_column("todo_items", "topic")
