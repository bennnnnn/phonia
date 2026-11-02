"""Quiz attempt counters on project items

Revision ID: 0048_project_item_quiz_counters
Revises: 0047_attachment_chunks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0048_project_item_quiz_counters"
down_revision: Union[str, None] = "0047_attachment_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_items",
        sa.Column("quiz_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "project_items",
        sa.Column("quiz_correct", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("project_items", "quiz_correct")
    op.drop_column("project_items", "quiz_attempts")
