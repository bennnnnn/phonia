"""Add CHECK constraints on messages.role and messages.feedback

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-30

These columns are typed as free TEXT but only ever hold a fixed enum. A bad
code path or migration could write garbage that the read side then breaks on
quietly. Add CHECK constraints so the DB rejects invalid values at write time.
Existing data is normalised first so the constraint cannot fail to apply.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard against any pre-existing stray values before adding the constraint.
    op.execute(
        "UPDATE messages SET role = 'assistant' WHERE role NOT IN ('user', 'assistant', 'system')"
    )
    op.execute(
        "UPDATE messages SET feedback = NULL "
        "WHERE feedback IS NOT NULL AND feedback NOT IN ('up', 'down')"
    )
    op.create_check_constraint(
        "ck_messages_role",
        "messages",
        "role IN ('user', 'assistant', 'system')",
    )
    op.create_check_constraint(
        "ck_messages_feedback",
        "messages",
        "feedback IS NULL OR feedback IN ('up', 'down')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_feedback", "messages", type_="check")
    op.drop_constraint("ck_messages_role", "messages", type_="check")
