"""Add employer logo and required-skill facts to job matches.

Revision ID: 0094_job_match_scan_fields
Revises: 0093_job_match_stages
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0094_job_match_scan_fields"
down_revision: Union[str, None] = "0093_job_match_stages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_matches",
        sa.Column("company_logo_url", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "job_matches",
        sa.Column(
            "required_skills",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.alter_column("job_matches", "required_skills", server_default=None)


def downgrade() -> None:
    op.drop_column("job_matches", "required_skills")
    op.drop_column("job_matches", "company_logo_url")
