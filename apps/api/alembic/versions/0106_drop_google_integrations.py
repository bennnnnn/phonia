"""Drop the Google Calendar and Gmail integrations.

Revision ID: 0106_drop_google_integrations
Revises: 0105_push_types_and_voice

Removes the Calendar and Gmail connections (with their stored refresh tokens),
the Gmail suggested reminders, and the two push switches that only served
calendar nudges and email suggestions. A to-do confirmed from Gmail stays a
to-do and becomes the user's own; ``user`` is the only source left.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0106_drop_google_integrations"
down_revision: Union[str, None] = "0105_push_types_and_voice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS suggested_reminders CASCADE")
    op.execute("DROP TABLE IF EXISTS user_gmail_connections CASCADE")
    op.execute("DROP TABLE IF EXISTS user_calendar_connections CASCADE")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS push_email_suggestions_enabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS push_calendar_enabled")
    op.execute("UPDATE todo_items SET source = 'user' WHERE source = 'gmail'")
    op.execute("ALTER TABLE todo_items DROP CONSTRAINT IF EXISTS ck_todo_items_source")
    op.execute(
        "ALTER TABLE todo_items ADD CONSTRAINT ck_todo_items_source CHECK (source IN ('user'))"
    )


def downgrade() -> None:
    """The integrations are gone. Restoring these tables does not bring them back."""
