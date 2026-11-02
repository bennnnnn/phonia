"""Language learning fields on projects and vocab cards on project_items

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-27
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("target_language", sa.String(10), nullable=False, server_default="en"),
    )
    op.add_column(
        "projects",
        sa.Column("native_language", sa.String(10), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("level", sa.String(20), nullable=False, server_default="level1"),
    )

    op.add_column("project_items", sa.Column("part_of_speech", sa.String(30), nullable=True))
    op.add_column("project_items", sa.Column("definition", sa.Text(), nullable=True))
    op.add_column("project_items", sa.Column("example_sentence", sa.Text(), nullable=True))
    op.add_column(
        "project_items",
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
    )
    op.add_column(
        "project_items",
        sa.Column("mastered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_items",
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_items",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_items",
        sa.Column("pronunciation_url", sa.String(500), nullable=True),
    )
    op.create_index(
        "ix_project_items_status_review",
        "project_items",
        ["project_id", "status", "last_reviewed_at"],
    )

    op.execute(
        sa.text(
            "UPDATE project_items SET status = 'mastered', mastered_at = updated_at "
            "WHERE mastered = true"
        )
    )
    op.execute(
        sa.text(
            "UPDATE project_items SET example_sentence = note "
            "WHERE example_sentence IS NULL AND note IS NOT NULL"
        )
    )
    op.execute(sa.text("UPDATE projects SET kind = 'language' WHERE kind = 'vocabulary'"))


def downgrade() -> None:
    op.drop_index("ix_project_items_status_review", table_name="project_items")
    op.drop_column("project_items", "pronunciation_url")
    op.drop_column("project_items", "review_count")
    op.drop_column("project_items", "last_reviewed_at")
    op.drop_column("project_items", "mastered_at")
    op.drop_column("project_items", "status")
    op.drop_column("project_items", "example_sentence")
    op.drop_column("project_items", "definition")
    op.drop_column("project_items", "part_of_speech")
    op.drop_column("projects", "level")
    op.drop_column("projects", "native_language")
    op.drop_column("projects", "target_language")
