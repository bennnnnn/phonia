"""Add chat summary columns for history compression

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "chats",
        sa.Column("summary_message_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chats", "summary_message_count")
    op.drop_column("chats", "summary")
