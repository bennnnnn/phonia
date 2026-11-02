"""Track last incorrect quiz attempt timestamp on project items

Revision ID: 0049_last_incorrect_at
Revises: 0048_project_item_quiz_counters
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049_last_incorrect_at"
down_revision: Union[str, None] = "0048_project_item_quiz_counters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_items",
        sa.Column("last_incorrect_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_items", "last_incorrect_at")
