"""Add usage_daily.est_cost_usd for per-day dollar cost telemetry

Revision ID: 0061_usage_daily_est_cost_usd
Revises: 0060_user_rc_last_event_at_ms

Accumulate estimated provider spend (catalog prices * raw tokens) so we can
answer "what did user X cost this month?" and validate quota multipliers.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0061_usage_daily_est_cost_usd"
down_revision: Union[str, None] = "0060_user_rc_last_event_at_ms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usage_daily",
        sa.Column(
            "est_cost_usd",
            sa.Numeric(precision=14, scale=6),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("usage_daily", "est_cost_usd")
