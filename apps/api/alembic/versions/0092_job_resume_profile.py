"""Store a structured resume profile on My Job search profiles.

Revision ID: 0092_job_resume_profile
Revises: 0091_job_match_score
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0092_job_resume_profile"
down_revision: Union[str, None] = "0091_job_match_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_search_profiles",
        sa.Column("resume_profile", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_search_profiles", "resume_profile")
