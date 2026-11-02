"""Add custom_instructions and locale to users

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("custom_instructions", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("locale", sa.String(10), server_default="en", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "locale")
    op.drop_column("users", "custom_instructions")
