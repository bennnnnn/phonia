"""The signed-in user and app the HTTP tests share."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.models.orm import User


def api_user(**kw: Any) -> MagicMock:
    """A ``User`` with every column the account endpoints read; any can be given."""
    u = MagicMock(spec=User)
    u.id = kw.get("id", uuid4())
    u.email = kw.get("email", "test@recall.local")
    u.name = kw.get("name", "Tester")
    u.avatar_url = None
    u.default_model = "auto"
    u.plan = kw.get("plan", "free")
    u.enabled_models = kw.get("enabled_models", None)
    u.response_tone = kw.get("response_tone", "funny")
    u.emoji_use = kw.get("emoji_use", "some")
    u.memory_enabled = True
    u.memory_include_sensitive = False
    u.locale = kw.get("locale", "en")
    u.timezone = kw.get("timezone", "UTC")
    u.location = kw.get("location", None)
    u.location_enabled = kw.get("location_enabled", bool(kw.get("location")))
    u.custom_instructions = kw.get("custom_instructions", None)
    u.age = kw.get("age", None)
    u.country = kw.get("country", None)
    u.job = kw.get("job", None)
    u.push_notifications_enabled = kw.get("push_notifications_enabled", True)
    u.push_reminders_enabled = kw.get("push_reminders_enabled", True)
    u.tts_voice = kw.get("tts_voice", None)
    u.email_reminders_enabled = kw.get("email_reminders_enabled", False)
    u.reminder_lead_minutes = kw.get("reminder_lead_minutes", 10)
    u.quiet_hours_enabled = kw.get("quiet_hours_enabled", False)
    u.quiet_hours_start_minute = kw.get("quiet_hours_start_minute", 1320)
    u.quiet_hours_end_minute = kw.get("quiet_hours_end_minute", 420)
    u.ai_data_consent_at = kw.get("ai_data_consent_at", None)
    u.google_sub = kw.get("google_sub", "google-sub")
    u.apple_sub = kw.get("apple_sub", None)
    u.created_at = datetime(2024, 1, 1)
    return u


def app_with_user(user: User) -> FastAPI:
    """The app with ``user`` signed in."""
    from app.core.deps import get_current_user, get_settings_dep

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    # Pin live-talk minutes so a local operator .env cannot change the
    # remaining/limit assertions.
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        monthly_live_talk_minutes=0,
        monthly_live_talk_minutes_plus=0,
        monthly_live_talk_minutes_pro=60,
    )
    return app
