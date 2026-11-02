"""Record when the user last removed or changed memory by hand.

Revision ID: 0098_memory_edited_at
Revises: 0097_memory_documents

The one-time history scan reads old chat lines. `users.memory_edited_at` lets it
skip every line written before the user's last hand edit, so a fact they
deleted or rewrote cannot come back from an older chat.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0098_memory_edited_at"
down_revision: Union[str, None] = "0097_memory_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("memory_edited_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "memory_edited_at")
