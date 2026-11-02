from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.orm.chat import Chat
    from app.modules.memory.models import Memory


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("plan IN ('free', 'plus', 'pro')", name="ck_users_plan"),
        CheckConstraint(
            "response_tone IN ('funny', 'professional', 'casual', 'soft')",
            name="ck_users_response_tone",
        ),
        CheckConstraint("emoji_use IN ('off', 'some', 'more')", name="ck_users_emoji_use"),
        CheckConstraint(
            "age IS NULL OR (age >= 13 AND age <= 120)",
            name="ck_users_age_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    apple_sub: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String)
    # A stored copy of the chosen model: enabled_models is the source, and
    # repositories/users.update rewrites this from it (schemas/auth.chosen_model_id).
    default_model: Mapped[str] = mapped_column(String, default="auto")
    plan: Mapped[str] = mapped_column(String, default="free", server_default="free")
    # Last processed RevenueCat webhook event_timestamp_ms — ignore older events.
    rc_last_event_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled_models: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    response_style: Mapped[str] = mapped_column(String, default="balanced")
    response_tone: Mapped[str] = mapped_column(String, default="casual", server_default="casual")
    # How many emoji replies use (Settings → Personalization): off, some or more.
    emoji_use: Mapped[str] = mapped_column(String, default="some", server_default="some")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Three tappable follow-up questions under a reply (Settings → Personalization).
    follow_up_suggestions_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    memory_include_sensitive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Web search and photo lookups (Settings → Data controls). Off: no search leaves the server.
    web_search_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # When memory last read the user's recent chats in one pass (history scan).
    memory_history_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the user last removed or changed saved memory by hand. The history
    # scan never reads lines written before it, so it cannot bring them back.
    memory_edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the user agreed to the disclosure of what goes to outside AI services
    # (model providers, voice, photo text, search). Null until they agree; the
    # phone shows that screen before the first chat.
    ai_data_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    push_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # Reminder pushes, under the master switch above.
    push_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # Read-aloud and live talk voice; None keeps the server default.
    tts_voice: Mapped[str | None] = mapped_column(String(16), nullable=True)
    email_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    reminder_lead_minutes: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    quiet_hours_start_minute: Mapped[int] = mapped_column(
        Integer, default=1320, server_default="1320"
    )
    quiet_hours_end_minute: Mapped[int] = mapped_column(Integer, default=420, server_default="420")
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="en", server_default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chats: Mapped[list[Chat]] = relationship(back_populates="user")
    memories: Mapped[list[Memory]] = relationship(back_populates="user")
