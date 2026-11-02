"""Drop part_of_speech from project items

Revision ID: 0051_drop_part_of_speech
Revises: 0050_daily_goal_history
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051_drop_part_of_speech"
down_revision: Union[str, None] = "0050_daily_goal_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("project_items", "part_of_speech")


def downgrade() -> None:
    op.add_column(
        "project_items",
        sa.Column("part_of_speech", sa.String(length=30), nullable=True),
    )
