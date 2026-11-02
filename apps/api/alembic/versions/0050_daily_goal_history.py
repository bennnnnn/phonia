"""Track per-day daily goal changes on learning projects

Revision ID: 0050_daily_goal_history
Revises: 0049_last_incorrect_at
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_daily_goal_history"
down_revision: Union[str, None] = "0049_last_incorrect_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("daily_goal_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "daily_goal_history")
