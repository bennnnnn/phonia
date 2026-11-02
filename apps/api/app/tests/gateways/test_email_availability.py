"""No email provider in production means no email, said plainly.

``send_email``'s mock path returned True in every environment, so with
RESEND_API_KEY unset in production the reminder scheduler marked to-do emails
sent (``email_sent_at``) that never went out, welcome and receipt emails were
dropped silently, and the app kept offering the email-reminder switch.
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.background import email_reminder_scheduler, periodic
from app.background.email_reminder_scheduler import LOCK_KEY
from app.core.config import Settings
from app.gateways import email_gateway
from app.models.schemas import UserOut


@pytest.mark.parametrize(
    "environment, key, enabled, can_send",
    [
        ("production", "", True, False),
        ("staging", "", True, False),
        ("production", "re_live", True, True),
        ("development", "", True, True),  # logged as a mock
        ("test", "", True, True),
        ("production", "re_live", False, False),
    ],
)
def test_can_send(environment: str, key: str, enabled: bool, can_send: bool) -> None:
    settings = Settings(environment=environment, resend_api_key=key, email_enabled=enabled)
    assert email_gateway.can_send(settings) is can_send


async def test_production_without_a_key_reports_not_sent(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(environment="production", resend_api_key="")
    with caplog.at_level(logging.WARNING, logger="app.gateways.email_gateway"):
        sent = await email_gateway.send_email(
            settings, to="user@example.com", subject="Reminder", html="<p>x</p>", text="x"
        )
    assert sent is False
    assert "RESEND_API_KEY is not set" in caplog.text
    assert "user@example.com" not in caplog.text


async def test_development_without_a_key_still_mocks_a_send() -> None:
    settings = Settings(environment="development", resend_api_key="")
    assert await email_gateway.send_email(
        settings, to="user@example.com", subject="Hi", html="<p>x</p>", text="x"
    )


@pytest.mark.parametrize(
    "environment, key, enabled, warns",
    [
        ("production", "", True, True),
        ("production", "re_live", True, False),
        ("production", "", False, False),  # turned off on purpose
        ("development", "", True, False),
    ],
)
def test_boot_warning_when_email_is_on_but_cannot_send(
    caplog: pytest.LogCaptureFixture, environment: str, key: str, enabled: bool, warns: bool
) -> None:
    settings = Settings(environment=environment, resend_api_key=key, email_enabled=enabled)
    with caplog.at_level(logging.WARNING, logger="app.gateways.email_gateway"):
        email_gateway.warn_if_unavailable(settings)
    assert ("RESEND_API_KEY is not set" in caplog.text) is warns


async def test_reminder_scheduler_does_not_start_without_a_provider() -> None:
    settings = Settings(environment="production", resend_api_key="")
    await email_reminder_scheduler.start_email_reminder_scheduler(settings)
    try:
        assert LOCK_KEY not in periodic._tasks
    finally:
        await email_reminder_scheduler.stop_email_reminder_scheduler()


async def test_reminder_cycle_sends_nothing_without_a_provider() -> None:
    settings = Settings(environment="production", resend_api_key="")
    cycle = AsyncMock(return_value=0)
    with patch.object(email_reminder_scheduler.reminder_emails, "run_email_reminder_cycle", cycle):
        await email_reminder_scheduler.run_email_reminder_cycle(settings)
    cycle.assert_not_awaited()


@pytest.mark.parametrize(
    "environment, key, scheduler_on, available",
    [
        ("production", "", True, False),
        ("production", "re_live", True, True),
        ("production", "re_live", False, False),
        ("development", "", True, True),
    ],
)
def test_user_payload_says_whether_email_reminders_work(
    environment: str, key: str, scheduler_on: bool, available: bool
) -> None:
    settings = Settings(
        environment=environment,
        resend_api_key=key,
        email_reminders_scheduler_enabled=scheduler_on,
    )
    out = UserOut(
        id=uuid4(),
        email="a@b.c",
        name=None,
        avatar_url=None,
        memory_enabled=True,
        created_at=datetime(2026, 1, 1),
    )
    with patch("app.core.config.get_settings", return_value=settings):
        assert out.model_dump()["email_reminders_available"] is available
