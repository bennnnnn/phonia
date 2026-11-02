"""projects daily_goal for vocabulary pacing

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("daily_goal", sa.Integer(), nullable=True))
    op.execute(
        sa.text("UPDATE projects SET daily_goal = 10 WHERE kind IN ('language', 'vocabulary')")
    )


def downgrade() -> None:
    op.drop_column("projects", "daily_goal")
