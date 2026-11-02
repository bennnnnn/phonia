"""Add todo_items.recurrence_rule for Schedule repeats.

Revision ID: 0074_todo_recurrence
Revises: 0073_attachment_filename

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0074_todo_recurrence"
down_revision: Union[str, None] = "0073_attachment_filename"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RULES = ("daily", "weekdays", "weekly", "monthly")


def upgrade() -> None:
    op.add_column(
        "todo_items",
        sa.Column("recurrence_rule", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_todo_recurrence_rule",
        "todo_items",
        "recurrence_rule IS NULL OR recurrence_rule IN "
        f"({', '.join(repr(rule) for rule in _RULES)})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_todo_recurrence_rule", "todo_items", type_="check")
    op.drop_column("todo_items", "recurrence_rule")
