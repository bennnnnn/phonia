"""Allow multiple trivia questions per topic category

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_project_quiz_topic", "project_quiz_questions", type_="unique")
    op.create_index(
        "uq_project_quiz_vocab_topic",
        "project_quiz_questions",
        ["project_id", "topic_normalized"],
        unique=True,
        postgresql_where=sa.text("quiz_kind = 'vocab'"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_quiz_vocab_topic", table_name="project_quiz_questions")
    op.create_unique_constraint(
        "uq_project_quiz_topic",
        "project_quiz_questions",
        ["project_id", "topic_normalized"],
    )
