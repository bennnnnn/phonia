"""Add fit score and experience requirement to job matches.

Revision ID: 0091_job_match_score
Revises: 0090_job_search
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0091_job_match_score"
down_revision: Union[str, None] = "0090_job_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_matches", sa.Column("experience", sa.String(length=120), nullable=True))
    op.add_column("job_matches", sa.Column("match_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_matches", "match_score")
    op.drop_column("job_matches", "experience")
