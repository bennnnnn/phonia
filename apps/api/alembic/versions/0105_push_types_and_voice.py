"""Per-kind push switches and a chosen voice.

Revision ID: 0105_push_types_and_voice
Revises: 0104_drop_job_search

Reminders, email suggestions and calendar nudges each get a switch under the
master push switch (all on, so nobody loses a notification they had). The
voice is shared by read-aloud and live talk; null keeps the server default.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0105_push_types_and_voice"
down_revision: Union[str, None] = "0104_drop_job_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PUSH_KINDS = (
    "push_reminders_enabled",
    "push_email_suggestions_enabled",
    "push_calendar_enabled",
)


def upgrade() -> None:
    for column in _PUSH_KINDS:
        op.add_column(
            "users",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    op.add_column("users", sa.Column("tts_voice", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tts_voice")
    for column in reversed(_PUSH_KINDS):
        op.drop_column("users", column)
