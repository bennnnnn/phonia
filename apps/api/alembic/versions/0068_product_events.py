"""Add privacy-safe product analytics events.

Revision ID: 0068_product_events
Revises: 0067_suggested_reminder_sender
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0068_product_events"
down_revision: Union[str, None] = "0067_suggested_reminder_sender"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EVENT_NAMES = (
    "paywall_viewed",
    "purchase_started",
    "purchase_succeeded",
    "purchase_failed",
    "push_permission",
)


def upgrade() -> None:
    op.create_table(
        "product_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=20), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column("installation_id", sa.String(length=128), nullable=True),
        sa.Column("client_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"name IN {tuple(_EVENT_NAMES)!r}",
            name="ck_product_events_name",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_events_name_recorded",
        "product_events",
        ["name", "recorded_at"],
    )
    op.create_index(
        "ix_product_events_user_recorded",
        "product_events",
        ["user_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_events_user_recorded", table_name="product_events")
    op.drop_index("ix_product_events_name_recorded", table_name="product_events")
    op.drop_table("product_events")
