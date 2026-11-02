"""project_quiz_questions — pre-generated daily exam batches

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_quiz_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("project_item_id", sa.Uuid(), nullable=True),
        sa.Column("quiz_date", sa.Date(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("quiz_kind", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("topic_normalized", sa.String(length=200), nullable=False),
        sa.Column("part_of_speech", sa.String(length=30), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("choices", postgresql.JSONB(), nullable=False),
        sa.Column("correct_letter", sa.String(length=1), nullable=False),
        sa.Column("reference_definition", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("answered_modality", sa.String(length=16), nullable=True),
        sa.Column("user_answer_text", sa.Text(), nullable=True),
        sa.Column("user_answer_letter", sa.String(length=1), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_item_id"], ["project_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "quiz_date",
            "sequence",
            name="uq_project_quiz_date_seq",
        ),
        sa.UniqueConstraint(
            "project_id",
            "project_item_id",
            name="uq_project_quiz_item",
        ),
        sa.UniqueConstraint(
            "project_id",
            "topic_normalized",
            name="uq_project_quiz_topic",
        ),
    )
    op.create_index(
        "ix_project_quiz_project_date",
        "project_quiz_questions",
        ["project_id", "quiz_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_quiz_project_date", table_name="project_quiz_questions")
    op.drop_table("project_quiz_questions")
