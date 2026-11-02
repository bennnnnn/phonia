"""Delete legacy non-learning projects; allow only language + trivia kinds

Revision ID: 0058_drop_legacy_project_kinds
Revises: 0057_memory_embedding_text_hash

Product surface is English vocabulary + general knowledge (trivia) only.
Legacy kinds (programming, math, general, …) were remapped to ``general`` in
0053 and still surfaced on the home screen via the projects[0] fallback.
Delete those rows (items cascade; chats/todos SET NULL) and tighten the CHECK.

CAUTION: upgrade() irreversibly DELETEs projects whose kind is not
language/trivia. Downgrade cannot restore those rows. Confirm a DB backup
(or that prod has no needed legacy projects) before deploying this revision
to any environment that still has legacy kinds.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0058_drop_legacy_project_kinds"
down_revision: Union[str, None] = "0057_memory_embedding_text_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive: any pre-normalize "vocabulary" aliases → language first.
    op.execute("UPDATE projects SET kind = 'language' WHERE kind = 'vocabulary'")
    # Drop legacy programming / general / etc. Project items cascade; chats and
    # todos that pointed at them become project_id NULL.
    op.execute("DELETE FROM projects WHERE kind NOT IN ('language', 'trivia')")

    op.drop_constraint("ck_projects_kind", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_kind",
        "projects",
        "kind IN ('language', 'trivia')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_kind", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_kind",
        "projects",
        "kind IN ('language', 'trivia', 'general')",
    )
