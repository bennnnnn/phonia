"""Add SM-2 spaced repetition fields to project_items

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_items",
        sa.Column(
            "ease_factor",
            sa.Float(),
            nullable=False,
            server_default="2.5",
        ),
    )
    op.add_column(
        "project_items",
        sa.Column(
            "interval_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "project_items",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_project_items_project_due_at",
        "project_items",
        ["project_id", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_items_project_due_at", table_name="project_items")
    op.drop_column("project_items", "due_at")
    op.drop_column("project_items", "interval_days")
    op.drop_column("project_items", "ease_factor")
