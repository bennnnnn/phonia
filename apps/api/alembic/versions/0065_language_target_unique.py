"""Allow one active language project per target language

Revision ID: 0065_language_target_unique
Revises: 0064_message_chunks

The 0055 index enforced one active language project per user. Multi-language
Learning needs one row per (user, target_language); trivia stays one-per-user.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0065_language_target_unique"
down_revision: Union[str, None] = "0064_message_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_projects_user_kind_active", table_name="projects")
    op.create_index(
        "uq_projects_user_language_target_active",
        "projects",
        ["user_id", "target_language"],
        unique=True,
        postgresql_where=sa.text("kind = 'language' AND archived = false"),
    )
    op.create_index(
        "uq_projects_user_trivia_active",
        "projects",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'trivia' AND archived = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_projects_user_trivia_active", table_name="projects")
    op.drop_index("uq_projects_user_language_target_active", table_name="projects")
    op.create_index(
        "uq_projects_user_kind_active",
        "projects",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind IN ('language', 'trivia') AND archived = false"),
    )
