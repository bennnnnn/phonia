"""Add ON DELETE CASCADE for core user-owned tables

Revision ID: 0052_user_owned_cascades
Revises: 0051_drop_part_of_speech
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0052_user_owned_cascades"
down_revision: Union[str, None] = "0051_drop_part_of_speech"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, constraint_name) — Postgres default names from early migrations.
_USER_FKS: list[tuple[str, str]] = [
    ("chats", "chats_user_id_fkey"),
    ("messages", "messages_user_id_fkey"),
    ("memories", "memories_user_id_fkey"),
    ("usage_daily", "usage_daily_user_id_fkey"),
    ("todo_items", "todo_items_user_id_fkey"),
    ("suggestions", "suggestions_user_id_fkey"),
    ("projects", "projects_user_id_fkey"),
    ("project_items", "project_items_user_id_fkey"),
]


def upgrade() -> None:
    for table, constraint in _USER_FKS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, constraint in _USER_FKS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "users",
            ["user_id"],
            ["id"],
        )
