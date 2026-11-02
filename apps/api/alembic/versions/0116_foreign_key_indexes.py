"""Index the five foreign keys that had none, so deletes stop scanning whole tables.

Revision ID: 0116_foreign_key_indexes
Revises: 0115_attachment_linked_at

Each ``ON DELETE SET NULL`` or ``CASCADE`` runs one lookup in the referencing table per
deleted row. Without an index led by the column, each lookup is a full scan: an account
delete ran one scan of ``memories`` per message and per fact, and a chat delete one scan
of ``memories``, ``todo_items`` and ``message_chunks``, all inside the 120 s statement
timeout. The nullable columns get partial indexes (``IS NOT NULL``), since a lookup never
asks for NULL. Adding indexes is an expand; the old release ignores them. They are built
CONCURRENTLY so writes keep flowing during the build.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0116_foreign_key_indexes"
down_revision: Union[str, None] = "0115_attachment_linked_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index, table, column, partial): partial when the column is nullable.
_INDEXES = (
    ("ix_memories_source_message", "memories", "source_message_id", True),
    ("ix_memories_source_chat", "memories", "source_chat_id", True),
    ("ix_memories_superseded_by", "memories", "superseded_by_id", True),
    ("ix_todo_items_chat", "todo_items", "chat_id", True),
    ("ix_message_chunks_chat", "message_chunks", "chat_id", False),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, column, partial in _INDEXES:
            op.create_index(
                name,
                table,
                [column],
                postgresql_where=sa.text(f"{column} IS NOT NULL") if partial else None,
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, _column, _partial in reversed(_INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
