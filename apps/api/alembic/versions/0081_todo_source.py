"""Persist Gmail provenance on confirmed Schedule reminders.

Revision ID: 0081_todo_source
Revises: 0080_retire_legacy_vocab

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).

Disconnecting Gmail deletes suggested_reminders, so the prompt-trust split
cannot key off those rows. Stamp source=gmail on the todo at confirm time.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0081_todo_source"
down_revision: Union[str, None] = "0080_retire_legacy_vocab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "todo_items",
        sa.Column("source", sa.String(length=16), server_default="user", nullable=False),
    )
    op.create_check_constraint(
        "ck_todo_items_source",
        "todo_items",
        "source IN ('user', 'gmail')",
    )
    op.execute(
        """
        UPDATE todo_items AS t
        SET source = 'gmail'
        FROM suggested_reminders AS s
        WHERE s.todo_id = t.id AND s.status = 'added'
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_todo_items_source", "todo_items", type_="check")
    op.drop_column("todo_items", "source")
