"""Add (chat_id, created_at, id) index for stable message pagination

Revision ID: 0063_msg_chat_created_id_idx
Revises: 0062_attachment_verified_at

Message list/pagination queries order by (created_at DESC, id DESC) — the id
tiebreaker makes the sort stable when two messages share a millisecond
timestamp (see repositories/messages.py). The existing index
ix_messages_chat_created is (chat_id, created_at) only, so Postgres must
sort the id tiebreaker in memory. A composite (chat_id, created_at, id)
index serves both the ORDER BY and the tuple-cursor pagination filters in
one seek.

The original revision id (``0063_messages_chat_created_id_idx``, 33 chars)
exceeded the ``alembic_version.version_num`` column (``varchar(32)``), so the
``UPDATE alembic_version`` at the end of upgrade always raised
``StringDataRightTruncationError`` — the index was created but the version
row never advanced past 0062. ``if_not_exists`` / ``if_exists`` make this
migration safe to re-run on a DB that already hit that half-applied state.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0063_msg_chat_created_id_idx"
down_revision: Union[str, None] = "0062_attachment_verified_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_chat_created_id",
        "messages",
        ["chat_id", "created_at", "id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_chat_created_id",
        table_name="messages",
        if_exists=True,
    )
