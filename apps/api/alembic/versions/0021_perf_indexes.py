"""Performance indexes for todos due dates and chat title search

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-28
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_todo_user_open_due "
        "ON todo_items (user_id, due_at) "
        "WHERE checked = false AND due_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chats_title_trgm "
        "ON chats USING gin (title gin_trgm_ops) "
        "WHERE title IS NOT NULL AND title <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chats_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_todo_user_open_due")
