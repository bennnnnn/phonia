"""Enforce at most one active language/trivia project per user at the DB level

Revision ID: 0055_project_kind_unique_active
Revises: 0054_user_profile_fields
Create Date: 2026-07-12

FEATURES.md documents at most one English vocabulary (language) project and
one trivia project per user, but the only guard was an in-memory snapshot
check inside apply_project_actions (services/projects.py). Two near-concurrent
project-sync jobs (at-least-once job redelivery, see core/jobs.py) could both
pass that check before either commits and create duplicates.

Defensively archive any pre-existing active duplicates first (keeping the
most recently updated one per user+kind active) so the new partial unique
index can be created without failing on data that predates this constraint,
same pattern as 0053's stray-value cleanup before adding CHECK constraints.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_project_kind_unique_active"
down_revision: Union[str, None] = "0054_user_profile_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE projects p
        SET archived = true
        WHERE kind IN ('language', 'trivia')
          AND archived = false
          AND EXISTS (
            SELECT 1 FROM projects p2
            WHERE p2.user_id = p.user_id
              AND p2.kind = p.kind
              AND p2.archived = false
              AND (p2.updated_at, p2.id) > (p.updated_at, p.id)
          )
        """
    )
    op.create_index(
        "uq_projects_user_kind_active",
        "projects",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind IN ('language', 'trivia') AND archived = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_projects_user_kind_active", table_name="projects")
