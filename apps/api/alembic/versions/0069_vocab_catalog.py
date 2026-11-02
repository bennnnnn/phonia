"""Curated vocabulary catalog (decks + entries).

Revision ID: 0069_vocab_catalog
Revises: 0068_product_events
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0069_vocab_catalog"
down_revision: Union[str, None] = "0068_product_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vocab_decks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_language", sa.String(10), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="chapter"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("kind IN ('chapter', 'sat')", name="ck_vocab_decks_kind"),
        sa.UniqueConstraint("target_language", "slug", name="uq_vocab_decks_lang_slug"),
    )
    op.create_index(
        "ix_vocab_decks_language_sort",
        "vocab_decks",
        ["target_language", "sort_order"],
    )
    op.create_table(
        "vocab_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "deck_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vocab_decks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("deck_id", "content", name="uq_vocab_entries_deck_content"),
    )
    op.create_index(
        "ix_vocab_entries_deck_sort",
        "vocab_entries",
        ["deck_id", "sort_order"],
    )
    op.add_column(
        "project_items",
        sa.Column(
            "catalog_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vocab_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_items", "catalog_entry_id")
    op.drop_index("ix_vocab_entries_deck_sort", table_name="vocab_entries")
    op.drop_table("vocab_entries")
    op.drop_index("ix_vocab_decks_language_sort", table_name="vocab_decks")
    op.drop_table("vocab_decks")
