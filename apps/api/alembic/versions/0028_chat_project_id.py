"""Add project_id to chats

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("project_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_chats_project_id",
        "chats",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_chats_user_project", "chats", ["user_id", "project_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_user_project", table_name="chats")
    op.drop_constraint("fk_chats_project_id", "chats", type_="foreignkey")
    op.drop_column("chats", "project_id")
