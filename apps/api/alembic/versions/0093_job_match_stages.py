"""Application stages (interviewing/offer/rejected) + notes on job matches.

Revision ID: 0093_job_match_stages
Revises: 0092_job_resume_profile
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0093_job_match_stages"
down_revision: Union[str, None] = "0092_job_resume_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_STATUSES = "('new', 'saved', 'applied', 'hidden')"
_NEW_STATUSES = "('new', 'saved', 'applied', 'interviewing', 'offer', 'rejected', 'hidden')"


def upgrade() -> None:
    op.add_column("job_matches", sa.Column("notes", sa.Text(), nullable=True))
    op.drop_constraint("ck_job_matches_status", "job_matches", type_="check")
    op.create_check_constraint(
        "ck_job_matches_status",
        "job_matches",
        f"status IN {_NEW_STATUSES}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_matches_status", "job_matches", type_="check")
    op.create_check_constraint(
        "ck_job_matches_status",
        "job_matches",
        f"status IN {_OLD_STATUSES}",
    )
    op.drop_column("job_matches", "notes")
