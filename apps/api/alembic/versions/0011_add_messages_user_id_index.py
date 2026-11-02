"""Add ix_messages_user_id index for search performance

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-26
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_user_id ON messages (user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_user_id")
