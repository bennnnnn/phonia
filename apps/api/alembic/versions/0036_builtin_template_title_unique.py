"""Unique constraint on built-in template titles

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-30

`seed_templates` runs on every startup and is check-then-insert. With multiple
workers (or a restart racing an old process) two workers can both pass the
existence check and insert duplicate built-in templates. A partial unique index
on `title WHERE is_builtin` makes the second insert fail at the DB instead of
silently producing duplicates. User templates are unaffected — users may share
titles with builtins or with each other.

`seed_templates` catches the IntegrityError so a race no longer crashes startup.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop any existing duplicate builtins before adding the constraint, so the
    # index can be created cleanly on databases that already have dupes.
    op.execute(
        "DELETE FROM templates WHERE id IN ("
        "  SELECT id FROM templates t1 WHERE t1.is_builtin = true AND EXISTS ("
        "    SELECT 1 FROM templates t2 WHERE t2.is_builtin = true "
        "    AND t2.title = t1.title AND t2.id < t1.id"
        "  )"
        ")"
    )
    op.create_index(
        "ux_templates_builtin_title",
        "templates",
        ["title"],
        unique=True,
        postgresql_where="is_builtin = true",
    )


def downgrade() -> None:
    op.drop_index("ux_templates_builtin_title", table_name="templates")
