"""Ordered language-learning path on projects

Revision ID: 0066_learning_path
Revises: 0065_language_target_unique

Stores chapter titles as JSONB. Existing language projects get distinct
list_titles in first-seen order, or a beginner starter path when empty.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0066_learning_path"
down_revision: Union[str, None] = "0065_language_target_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STARTER = [
    "Greetings",
    "Numbers",
    "Family",
    "Food",
    "Daily life",
    "Colors",
    "Time",
    "Travel",
]


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("learning_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE projects AS p
            SET learning_path = sub.titles
            FROM (
                SELECT project_id,
                       jsonb_agg(list_title ORDER BY first_seen) AS titles
                FROM (
                    SELECT project_id, list_title, MIN(created_at) AS first_seen
                    FROM project_items
                    WHERE btrim(list_title) <> ''
                      AND lower(btrim(list_title)) <> 'general'
                    GROUP BY project_id, list_title
                ) AS t
                GROUP BY project_id
            ) AS sub
            WHERE p.id = sub.project_id AND p.kind = 'language'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE projects
            SET learning_path = CAST(:path AS jsonb)
            WHERE kind = 'language' AND learning_path IS NULL
            """
        ),
        {"path": json.dumps(_STARTER)},
    )


def downgrade() -> None:
    op.drop_column("projects", "learning_path")
