"""Index the drawer's and the gallery's pages and the hourly retention deletes.

Revision ID: 0123_list_and_retention_indexes
Revises: 0122_todo_due_set_at

- The drawer's dated chats (unpinned, unarchived) and its archived chats page newest
  first by ``(updated_at, id)``; the indexes led by ``(user_id, updated_at)`` and
  ``(user_id, archived)`` left a sort of every such chat. Each page now has a partial
  index in its own predicate (a btree reads backwards for the newest first).
- The gallery pages a user's attachments by ``(created_at, id)`` over an index of
  ``user_id`` alone. ``(user_id, created_at, id)`` serves it, and the FK cascade the
  old index served, so ``ix_attachments_user`` (its prefix) goes.
- The hourly retention deletes (abandoned drafts by ``chats.created_at``, old
  ``usage_daily`` rows by ``date``) scanned the whole table.

Indexes only: an expand, and dropping a prefix index breaks no query of the previous
release. Built and dropped CONCURRENTLY so writes keep flowing.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0123_list_and_retention_indexes"
down_revision: Union[str, None] = "0122_todo_due_set_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CREATE = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chats_user_recent "
    "ON chats (user_id, updated_at, id) WHERE pinned IS false AND archived IS false",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chats_user_archived_recent "
    "ON chats (user_id, updated_at, id) WHERE archived IS true",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chats_created ON chats (created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_usage_daily_date ON usage_daily (date)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attachments_user_created "
    "ON attachments (user_id, created_at, id)",
)
_NEW_INDEXES = (
    "ix_attachments_user_created",
    "ix_usage_daily_date",
    "ix_chats_created",
    "ix_chats_user_archived_recent",
    "ix_chats_user_recent",
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for statement in _CREATE:
            op.execute(statement)
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_attachments_user")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attachments_user ON attachments (user_id)"
        )
        for name in _NEW_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
