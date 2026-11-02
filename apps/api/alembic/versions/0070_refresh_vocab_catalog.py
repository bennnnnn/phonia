"""Refresh curated vocabulary catalog (en/es wide groups).

Revision ID: 0070_refresh_vocab_catalog
Revises: 0069_vocab_catalog
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0070_refresh_vocab_catalog"
down_revision: Union[str, None] = "0069_vocab_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The vocabulary catalog seed lived in app code that no longer exists.
    # Clear any rows from 0069 so later revisions see empty decks.
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE project_items SET catalog_entry_id = NULL"))
    conn.execute(sa.text("DELETE FROM vocab_entries"))
    conn.execute(sa.text("DELETE FROM vocab_decks"))


def downgrade() -> None:
    pass
