"""Add IPA, part of speech, and simple gloss on catalog words and items.

Revision ID: 0077_vocab_word_gloss
Revises: 0076_tone_default_casual
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0077_vocab_word_gloss"
down_revision: Union[str, None] = "0076_tone_default_casual"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vocab_entries", sa.Column("ipa", sa.String(length=80), nullable=True))
    op.add_column(
        "vocab_entries",
        sa.Column("part_of_speech", sa.String(length=30), nullable=True),
    )
    op.add_column("vocab_entries", sa.Column("simple_gloss", sa.Text(), nullable=True))
    op.add_column("project_items", sa.Column("ipa", sa.String(length=80), nullable=True))
    op.add_column(
        "project_items",
        sa.Column("part_of_speech", sa.String(length=30), nullable=True),
    )
    op.add_column("project_items", sa.Column("simple_gloss", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_items", "simple_gloss")
    op.drop_column("project_items", "part_of_speech")
    op.drop_column("project_items", "ipa")
    op.drop_column("vocab_entries", "simple_gloss")
    op.drop_column("vocab_entries", "part_of_speech")
    op.drop_column("vocab_entries", "ipa")
