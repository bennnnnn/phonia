"""Add optional project_id to todo_items

Revision ID: 0045
Revises: 0043
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "todo_items",
        sa.Column("project_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_todo_items_project_id",
        "todo_items",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_todo_items_user_project", "todo_items", ["user_id", "project_id"])


def downgrade() -> None:
    op.drop_index("ix_todo_items_user_project", table_name="todo_items")
    op.drop_constraint("fk_todo_items_project_id", "todo_items", type_="foreignkey")
    op.drop_column("todo_items", "project_id")
