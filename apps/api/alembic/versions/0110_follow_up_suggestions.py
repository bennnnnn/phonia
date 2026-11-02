"""Users can turn the follow-up suggestions under a reply off.

Revision ID: 0110_follow_up_suggestions
Revises: 0109_trim_model_lineup

On for everyone, as it was; turning it off also skips the model call that writes them.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0110_follow_up_suggestions"
down_revision: Union[str, None] = "0109_trim_model_lineup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "follow_up_suggestions_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "follow_up_suggestions_enabled")
