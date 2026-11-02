"""Store the Gmail sender on suggested reminders

Revision ID: 0067_suggested_reminder_sender
Revises: 0066_learning_path

Used by chat nudges and the Reminders list so a suggestion shows who it
came from (Amazon, OpenTable, …) without re-fetching the message.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0067_suggested_reminder_sender"
down_revision: Union[str, None] = "0066_learning_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "suggested_reminders",
        sa.Column("source_sender", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("suggested_reminders", "source_sender")
