"""Add user timezone for local-time-aware prompts

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-27
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
