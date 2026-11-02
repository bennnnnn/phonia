"""Unique project item per list word.

Revision ID: 0075_item_list_unique
Revises: 0074_todo_recurrence

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)``.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0075_item_list_unique"
down_revision: Union[str, None] = "0074_todo_recurrence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM project_items AS a
        USING project_items AS b
        WHERE a.project_id = b.project_id
          AND a.list_title = b.list_title
          AND a.content = b.content
          AND a.created_at > b.created_at
        """
    )
    op.execute(
        """
        DELETE FROM project_items AS a
        USING project_items AS b
        WHERE a.project_id = b.project_id
          AND a.list_title = b.list_title
          AND a.content = b.content
          AND a.id > b.id
        """
    )
    op.create_index(
        "uq_project_items_project_list_content",
        "project_items",
        ["project_id", "list_title", "content"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_project_items_project_list_content", table_name="project_items")
