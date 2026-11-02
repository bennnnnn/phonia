import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Estimated provider spend (USD) from catalog prices * raw tokens — not
    # quota-weighted. Accumulated per day for cost dashboards / abuse checks.
    est_cost_usd: Mapped[float] = mapped_column(
        Numeric(14, 6), nullable=False, server_default="0", default=0
    )


class ProductEventDaily(Base):
    """Per-day counts of product events past their retention (``modules/analytics/retention``).

    One row per UTC day and bucket (event name, platform, app version, properties):
    how many events, and from how many accounts. No user ids.
    """

    __tablename__ = "product_event_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), primary_key=True)
    app_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    properties: Mapped[dict[str, str]] = mapped_column(JSONB, primary_key=True)
    events: Mapped[int] = mapped_column(Integer, nullable=False)
    users: Mapped[int] = mapped_column(Integer, nullable=False)


class ProductEventRollupDay(Base):
    """A UTC day whose events were counted into ``product_event_daily``.

    Written in the counting transaction, so a cycle stopped while deleting that day's
    rows only deletes the rest next time; it never counts the day again.
    """

    __tablename__ = "product_event_rollup_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    rolled_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductEvent(Base):
    __tablename__ = "product_events"
    __table_args__ = (
        Index("ix_product_events_name_recorded", "name", "recorded_at"),
        Index("ix_product_events_user_recorded", "user_id", "recorded_at"),
        CheckConstraint(
            "name IN "
            "('paywall_viewed', 'purchase_started', 'purchase_succeeded', "
            "'purchase_failed', 'push_permission', 'chat_ttft', 'chat_turn_outcome')",
            name="ck_product_events_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    installation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
