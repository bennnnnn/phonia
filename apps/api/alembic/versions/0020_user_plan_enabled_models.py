"""Add user plan and enabled model preferences

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-28
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan", sa.String(), server_default="free", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("enabled_models", JSONB(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE users SET default_model = 'auto' "
            "WHERE default_model IN ('free-chat', 'smart-chat')"
        )
    )


def downgrade() -> None:
    op.drop_column("users", "enabled_models")
    op.drop_column("users", "plan")
