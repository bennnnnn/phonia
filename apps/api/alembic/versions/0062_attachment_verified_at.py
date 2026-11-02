"""Add attachments.verified_at so reads skip a second full-object download

Revision ID: 0062_attachment_verified_at
Revises: 0061_usage_daily_est_cost_usd

Verification is idempotent after the presigned PUT is consumed. Recording the
outcome on the row lets /file and /url presign without pulling the object
through the API on every view.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0062_attachment_verified_at"
down_revision: Union[str, None] = "0061_usage_daily_est_cost_usd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachments", "verified_at")
