"""Users can turn web search off.

Revision ID: 0111_web_search_setting
Revises: 0110_follow_up_suggestions

On for everyone, as it was. Off stops every search and photo lookup for that user's
turns: each one sends the question to an outside search service.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0111_web_search_setting"
down_revision: Union[str, None] = "0110_follow_up_suggestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "web_search_enabled")
