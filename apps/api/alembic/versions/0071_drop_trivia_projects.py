"""Remove general-knowledge trivia projects.

Revision ID: 0071_drop_trivia_projects
Revises: 0070_refresh_vocab_catalog
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0071_drop_trivia_projects"
down_revision: Union[str, None] = "0070_refresh_vocab_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM projects WHERE kind = 'trivia'")
    op.drop_index("uq_projects_user_trivia_active", table_name="projects")
    op.drop_constraint("ck_projects_kind", "projects", type_="check")
    op.create_check_constraint("ck_projects_kind", "projects", "kind IN ('language')")


def downgrade() -> None:
    op.drop_constraint("ck_projects_kind", "projects", type_="check")
    op.create_check_constraint("ck_projects_kind", "projects", "kind IN ('language', 'trivia')")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_projects_user_trivia_active
        ON projects (user_id)
        WHERE kind = 'trivia' AND archived = false
        """
    )
