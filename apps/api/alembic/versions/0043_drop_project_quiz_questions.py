"""Drop project_quiz_questions — dead exam-mode table

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-06

The exam-mode daily quiz backend (project_quiz_questions table +
/quiz/daily* endpoints + project_daily_quiz service) was unreachable from
the mobile app — all quiz launch paths use chat mode. The mobile exam UI
was removed in a prior change; this drops the now-orphaned table and its
indexes. The chat-mode quiz path (chats.quiz_mode, vocab_quiz fences,
apply_deterministic_quiz_answer) is untouched.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dropping the table cascades its indexes (ix_project_quiz_project_date,
    # uq_project_quiz_vocab_topic) and constraints.
    op.drop_table("project_quiz_questions")


def downgrade() -> None:
    # Recreate the table as it existed at 0042 (so the migration is
    # reversible). Data is NOT recovered — only the empty schema.
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
        sa.UniqueConstraint("project_id", "quiz_date", "sequence", name="uq_project_quiz_date_seq"),
        sa.UniqueConstraint("project_id", "project_item_id", name="uq_project_quiz_item"),
    )
    op.create_index(
        "ix_project_quiz_project_date",
        "project_quiz_questions",
        ["project_id", "quiz_date"],
    )
    op.create_index(
        "uq_project_quiz_vocab_topic",
        "project_quiz_questions",
        ["project_id", "topic_normalized"],
        unique=True,
        postgresql_where=sa.text("quiz_kind = 'vocab'"),
    )
