"""Track the text hash an embedding was computed from, for reliable staleness detection

Revision ID: 0057_memory_embedding_text_hash
Revises: 0056_quiz_miss_events

BUG FIX (was silent): extraction/consolidation only re-embed a memory section
when its text changed from the specific prior snapshot passed into that one
call, or when the embedding is NULL. If embed_text failed right after a text
change (provider hiccup), the embedding silently stayed paired with the OLD
text forever unless that section's text happened to change again later —
semantic search would misrank it with nothing to detect or self-heal it.
Storing the hash of the text an embedding was actually computed from lets
every future extraction/consolidation pass correctly recognize "this
embedding no longer matches this text" regardless of how many passes have
happened in between.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_memory_embedding_text_hash"
down_revision: Union[str, None] = "0056_quiz_miss_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("embedding_text_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("memories", "embedding_text_hash")
