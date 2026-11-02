"""Learning practice events and vocabulary classification.

Revision ID: 0079_learning_practice
Revises: 0078_attach_lib_visible
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0079_learning_practice"
down_revision = "0078_attach_lib_visible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_items", sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    for table in ("vocab_entries", "project_items"):
        op.add_column(
            table,
            sa.Column("vocabulary_kind", sa.String(30), nullable=False, server_default="word"),
        )
        op.add_column(table, sa.Column("verb_kind", sa.String(30), nullable=True))
        op.add_column(table, sa.Column("noun_kind", sa.String(30), nullable=True))
    op.create_table(
        "learning_practice_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("was_correct", sa.Boolean(), nullable=False),
        sa.Column("completes_word", sa.Boolean(), nullable=False),
        sa.Column("newly_mastered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "attempt_id", name="uq_learning_practice_user_attempt"),
        sa.CheckConstraint(
            "NOT completes_word OR was_correct", name="ck_learning_practice_completion"
        ),
        sa.CheckConstraint(
            "NOT newly_mastered OR completes_word", name="ck_learning_practice_new_mastery"
        ),
    )
    op.create_index(
        "ix_learning_practice_user_time",
        "learning_practice_events",
        ["user_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_learning_practice_project_time",
        "learning_practice_events",
        ["project_id", "occurred_at"],
    )
    op.create_index(
        "ix_learning_practice_item_time", "learning_practice_events", ["item_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("learning_practice_events")
    op.drop_column("project_items", "last_completed_at")
    for table in ("project_items", "vocab_entries"):
        for column in ("noun_kind", "verb_kind", "vocabulary_kind"):
            op.drop_column(table, column)
