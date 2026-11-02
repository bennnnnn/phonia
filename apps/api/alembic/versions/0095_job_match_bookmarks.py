"""Separate job bookmarks from application stages.

Revision ID: 0095_job_match_bookmarks
Revises: 0094_job_match_scan_fields
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0095_job_match_bookmarks"
down_revision: Union[str, None] = "0094_job_match_scan_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_matches",
        sa.Column("is_saved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Keep the legacy status during the compatibility window. Existing mobile
    # builds still derive their Saved tab entirely from status == "saved";
    # modern clients opt into the independent is_saved representation.
    op.execute("UPDATE job_matches SET is_saved = true WHERE status = 'saved'")
    op.alter_column("job_matches", "is_saved", server_default=None)


def downgrade() -> None:
    op.drop_column("job_matches", "is_saved")
