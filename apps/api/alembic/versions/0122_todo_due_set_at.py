"""When a to-do's due time was last set, apart from any other edit.

Revision ID: 0122_todo_due_set_at
Revises: 0121_emoji_use

A to-do's reminder instant (``services/reminder_timing.reminder_at``) reads when its time
was set: one set inside its own lead window goes out when due, not at once. It read
``updated_at``, which every edit moves, so a title edit, a reorder or an uncheck inside
the lead window, after the reminder had gone out, moved it to the due time, and a phone
without push alerted twice. ``due_set_at`` changes only with ``due_at``. Existing rows
start at ``updated_at``, which keeps every instant where it is. A column with a server
default: an expand.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0122_todo_due_set_at"
down_revision: Union[str, None] = "0121_emoji_use"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "todo_items",
        sa.Column(
            "due_set_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("UPDATE todo_items SET due_set_at = updated_at")


def downgrade() -> None:
    op.drop_column("todo_items", "due_set_at")
