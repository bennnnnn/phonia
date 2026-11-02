"""Keep whether a reply was stopped, so "Generation stopped." survives a reload.

Revision ID: 0120_message_completion
Revises: 0119_product_event_rollup

The phone showed the stopped footer only from the live ``done`` frame; a reopened chat
lost it. ``messages.completion`` holds 'user_stop' or 'interrupted' for a reply that did
not finish, NULL otherwise. A nullable column and its check: an expand.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0120_message_completion"
down_revision: Union[str, None] = "0119_product_event_rollup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("completion", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "ck_messages_completion",
        "messages",
        "completion IS NULL OR completion IN ('interrupted', 'user_stop')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_completion", "messages", type_="check")
    op.drop_column("messages", "completion")
