"""Default new users to casual tone. Do not rewrite existing funny rows.

Revision ID: 0076_tone_default_casual
Revises: 0075_item_list_unique
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0076_tone_default_casual"
down_revision: Union[str, None] = "0075_item_list_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "response_tone",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default="casual",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "response_tone",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default="funny",
    )
