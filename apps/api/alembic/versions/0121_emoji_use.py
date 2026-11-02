"""How many emoji replies use: none, a few (the default) or lots.

Revision ID: 0121_emoji_use
Revises: 0120_message_completion

Replies had no emoji unless the user wrote one. A fitting emoji beside a heading or a list
item's label makes a reply easier to scan, so every account starts at "some"; "off" is
the old behaviour. A column with a server default and its check: an expand.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0121_emoji_use"
down_revision: Union[str, None] = "0120_message_completion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("emoji_use", sa.String(), nullable=False, server_default="some"),
    )
    op.create_check_constraint(
        "ck_users_emoji_use", "users", "emoji_use IN ('off', 'some', 'more')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_emoji_use", "users", type_="check")
    op.drop_column("users", "emoji_use")
