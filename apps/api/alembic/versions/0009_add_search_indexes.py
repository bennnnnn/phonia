"""Add pg_trgm search index on messages.content

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-26
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_messages_content_trgm "
        "ON messages USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_content_trgm")
