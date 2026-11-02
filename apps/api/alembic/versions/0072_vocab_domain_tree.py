"""Add domain on vocab decks and refresh the catalog tree.

Revision ID: 0072_vocab_domain_tree
Revises: 0071_drop_trivia_projects
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0072_vocab_domain_tree"
down_revision: Union[str, None] = "0071_drop_trivia_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vocab_decks",
        sa.Column("domain", sa.String(200), nullable=False, server_default=""),
    )
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE project_items SET catalog_entry_id = NULL"))
    conn.execute(sa.text("DELETE FROM vocab_entries"))
    conn.execute(sa.text("DELETE FROM vocab_decks"))


def downgrade() -> None:
    op.drop_column("vocab_decks", "domain")
