"""Fold product events past their retention into per-day counts.

Revision ID: 0119_product_event_rollup
Revises: 0118_user_scoped_search_indexes

The phone records two events a chat turn and nothing ever deleted them. A worker cycle
now counts each UTC day older than the retention into ``product_event_daily`` (no user
ids), marks the day in ``product_event_rollup_days`` in the same transaction, and
deletes the day's rows in batches. New tables only: an expand.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0119_product_event_rollup"
down_revision: Union[str, None] = "0118_user_scoped_search_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_event_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("app_version", sa.String(length=32), nullable=False),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("events", sa.Integer(), nullable=False),
        sa.Column("users", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day", "name", "platform", "app_version", "properties"),
    )
    op.create_table(
        "product_event_rollup_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "rolled_up_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("product_event_rollup_days")
    op.drop_table("product_event_daily")
