"""Partial unique on open dated reminders + list cursor index.

Revision ID: 0084_todo_open_due_uq
Revises: 0083_search_lib_hidden

Open rows with the same title and due instant should not double-insert when
chat's in-memory skip races a concurrent create. Do not unique on title
alone — two "Call mom" reminders on different days are valid.

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0084_todo_open_due_uq"
down_revision: Union[str, None] = "0083_search_lib_hidden"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM todo_items AS a
        USING todo_items AS b
        WHERE a.checked = false
          AND b.checked = false
          AND a.due_at IS NOT NULL
          AND b.due_at IS NOT NULL
          AND a.user_id = b.user_id
          AND lower(a.content) = lower(b.content)
          AND a.due_at = b.due_at
          AND (
            a.created_at > b.created_at
            OR (a.created_at = b.created_at AND a.id > b.id)
          )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_todo_open_content_due
        ON todo_items (user_id, lower(content), due_at)
        WHERE checked = false AND due_at IS NOT NULL
        """
    )
    op.create_index("ix_todo_user_id", "todo_items", ["user_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_todo_user_id", table_name="todo_items")
    op.execute("DROP INDEX IF EXISTS uq_todo_open_content_due")
