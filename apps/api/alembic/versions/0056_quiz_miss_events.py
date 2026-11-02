"""Append-only quiz miss event log for accurate day-attribution history

Revision ID: 0056_quiz_miss_events
Revises: 0055_project_kind_unique_active
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_quiz_miss_events"
down_revision: Union[str, None] = "0055_project_kind_unique_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_miss_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("project_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_quiz_miss_events_item_occurred",
        "quiz_miss_events",
        ["item_id", "occurred_at"],
    )
    op.create_index("ix_quiz_miss_events_user", "quiz_miss_events", ["user_id"])
    # Best-effort one-row backfill from the existing single-column history so
    # currently-open misses show up in the event log right away. Older misses
    # that column already overwrote are unrecoverable — acceptable for a backfill.
    op.execute(
        """
        INSERT INTO quiz_miss_events (id, item_id, user_id, occurred_at)
        SELECT gen_random_uuid(), id, user_id, last_incorrect_at
        FROM project_items
        WHERE last_incorrect_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_miss_events_user", table_name="quiz_miss_events")
    op.drop_index("ix_quiz_miss_events_item_occurred", table_name="quiz_miss_events")
    op.drop_table("quiz_miss_events")
