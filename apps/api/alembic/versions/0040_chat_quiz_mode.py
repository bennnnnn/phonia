"""chat quiz_mode for exam vs chat tutor sessions

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("quiz_mode", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("chats", "quiz_mode")
