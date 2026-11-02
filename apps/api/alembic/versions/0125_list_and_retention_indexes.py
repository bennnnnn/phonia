"""Index the drawer's and the gallery's pages and the hourly retention deletes.

Revision ID: 0125_list_and_retention_indexes
Revises: 0124_drop_removed_features

- The drawer's dated (unpinned) chats page newest first by ``(updated_at, id)``; the
  index led by ``(user_id, updated_at)`` left a sort of every such chat. The page now
  has a partial index in its own predicate (a btree reads backwards for the newest
  first). Phonia has no chat archive (0123), so there is no archived page to index.
- The gallery pages a user's attachments by ``(created_at, id)`` over an index of
  ``user_id`` alone. ``(user_id, created_at, id)`` serves it, and the FK cascade the
  old index served, so ``ix_attachments_user`` (its prefix) goes.
- The hourly retention deletes (abandoned drafts by ``chats.created_at``, old
  ``usage_daily`` rows by ``date``) scanned the whole table.

Indexes only: an expand, and dropping a prefix index breaks no query of the previous
release. Built and dropped CONCURRENTLY so writes keep flowing.

A CONCURRENTLY build that fails (a timeout, a deadlock, a deploy stopped midway) leaves
an INVALID index of that name, which ``IF NOT EXISTS`` would skip on the next run while
the planner never uses it. Each build first drops an invalid index of its name, and the
old attachments index goes only once its replacement is valid.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0125_list_and_retention_indexes"
down_revision: Union[str, None] = "0124_drop_removed_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CREATE = (
    (
        "ix_chats_user_recent",
        "ON chats (user_id, updated_at, id) WHERE pinned IS false",
    ),
    ("ix_chats_created", "ON chats (created_at)"),
    ("ix_usage_daily_date", "ON usage_daily (date)"),
    ("ix_attachments_user_created", "ON attachments (user_id, created_at, id)"),
)
_OLD_ATTACHMENTS_INDEX = ("ix_attachments_user", "ON attachments (user_id)")
_REPLACES_OLD = "ix_attachments_user_created"


def _index_valid(name: str) -> bool | None:
    """None when there is no such index; else whether Postgres may use it."""
    return (
        op.get_bind()
        .execute(
            sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"),
            {"name": name},
        )
        .scalar()
    )


def _build(name: str, definition: str) -> None:
    """Build an index, replacing an invalid one a failed earlier build left."""
    if _index_valid(name) is False:
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} {definition}")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, definition in _CREATE:
            _build(name, definition)
        # The FK cascade keeps an index to use: the old one stays until the new is valid.
        if _index_valid(_REPLACES_OLD):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_OLD_ATTACHMENTS_INDEX[0]}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _build(*_OLD_ATTACHMENTS_INDEX)
        for name, _definition in reversed(_CREATE):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
