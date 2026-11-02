"""Add users.rc_last_event_at_ms for RevenueCat webhook ordering

Revision ID: 0060_user_rc_last_event_at_ms
Revises: 0059_attachment_source

Persist the last processed RC event_timestamp_ms so a late EXPIRATION
cannot downgrade a subscriber who already renewed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0060_user_rc_last_event_at_ms"
down_revision: Union[str, None] = "0059_attachment_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("rc_last_event_at_ms", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "rc_last_event_at_ms")
