"""Add user location label from device geocoding

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-28
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("location", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "location")
