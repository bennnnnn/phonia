"""Index the per-minute reminder scans by due time.

Revision ID: 0117_reminder_due_indexes
Revises: 0116_foreign_key_indexes

The push and email reminder cycles look for open dated to-dos due in a window
around now, across every user. The only dated index led with ``user_id``, so
each minute walked every open dated to-do of every user. These partial indexes
hold only rows a channel has not sent yet, ordered by ``(due_at, id)`` for the
cycles' keyset pages. Adding indexes is an expand; built CONCURRENTLY so writes
keep flowing.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0117_reminder_due_indexes"
down_revision: Union[str, None] = "0116_foreign_key_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (
    (
        "ix_todo_push_due",
        "checked = false AND notification_sent_at IS NULL AND due_at IS NOT NULL",
    ),
    (
        "ix_todo_email_due",
        "checked = false AND email_sent_at IS NULL AND recurrence_rule IS NULL "
        "AND due_at IS NOT NULL",
    ),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, predicate in _INDEXES:
            op.create_index(
                name,
                "todo_items",
                ["due_at", "id"],
                postgresql_where=sa.text(predicate),
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _predicate in reversed(_INDEXES):
            op.drop_index(
                name, table_name="todo_items", postgresql_concurrently=True, if_exists=True
            )
