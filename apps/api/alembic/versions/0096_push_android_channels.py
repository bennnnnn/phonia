"""Remember which installs created the split Android notification channels.

Revision ID: 0096_push_android_channels
Revises: 0095_job_match_bookmarks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0096_push_android_channels"
down_revision: Union[str, None] = "0095_job_match_bookmarks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "push_tokens",
        sa.Column("android_channels", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("push_tokens", "android_channels")
