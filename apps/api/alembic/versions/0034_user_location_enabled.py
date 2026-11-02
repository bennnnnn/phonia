"""User location_enabled toggle (device GPS opt-in)

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "location_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute(
        "UPDATE users SET location_enabled = true "
        "WHERE location IS NOT NULL AND btrim(location) <> ''"
    )


def downgrade() -> None:
    op.drop_column("users", "location_enabled")
