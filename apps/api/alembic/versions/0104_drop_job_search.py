"""Drop the My Job search product.

Revision ID: 0104_drop_job_search
Revises: 0103_remove_job_resume

Removes search profiles, matches, runs, notification outbox, and manual
allowances. Chat, memory, and reminder data stay.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0104_drop_job_search"
down_revision: Union[str, None] = "0103_remove_job_resume"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_notification_events CASCADE")
    op.execute("DROP TABLE IF EXISTS job_search_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS job_matches CASCADE")
    op.execute("DROP TABLE IF EXISTS job_manual_allowances CASCADE")
    op.execute("DROP TABLE IF EXISTS job_search_profiles CASCADE")


def downgrade() -> None:
    """The product is gone. Restoring these tables does not bring My Job back."""
