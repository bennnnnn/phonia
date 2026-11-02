"""Add sort_order to todo items for list ordering

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-27
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todo_items", sa.Column("sort_order", sa.Integer(), nullable=True))
    op.create_index(
        "ix_todo_user_topic_sort",
        "todo_items",
        ["user_id", "topic", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_todo_user_topic_sort", table_name="todo_items")
    op.drop_column("todo_items", "sort_order")
