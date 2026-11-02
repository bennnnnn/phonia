"""Add archived flag to chats.

Revision ID: 0029
Revises: 0028
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_chats_user_archived", "chats", ["user_id", "archived"])


def downgrade() -> None:
    op.drop_index("ix_chats_user_archived", table_name="chats")
    op.drop_column("chats", "archived")
