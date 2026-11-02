"""Record when a user agreed to their data going to outside AI services.

Revision ID: 0112_ai_data_consent
Revises: 0111_web_search_setting

Null for everyone, new and existing: each account is asked once, after sign-in and
before its first chat, and the answer follows the account to every device.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0112_ai_data_consent"
down_revision: Union[str, None] = "0111_web_search_setting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable with no default: a metadata-only change, no table rewrite.
    op.add_column(
        "users",
        sa.Column("ai_data_consent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "ai_data_consent_at")
