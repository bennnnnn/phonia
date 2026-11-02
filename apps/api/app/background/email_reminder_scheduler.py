"""Periodic email reminder scheduler — dated to-do reminders (opt-in)."""

from __future__ import annotations

import logging

from app.background.periodic import (
    CycleLock,
    run_locked_cycle,
    start_periodic,
    stop_periodic,
)
from app.core.config import Settings
from app.core.db import SessionLocal
from app.gateways import email_gateway
from app.modules.notifications import reminder_email as reminder_emails

logger = logging.getLogger(__name__)

_NAME = "email_reminders"
LOCK_KEY = "recall:email_reminders:lock"
INTERVAL_SECONDS = 60
# Refreshed before every send (see push_scheduler.LOCK_TTL_SECONDS).
LOCK_TTL_SECONDS = 2 * INTERVAL_SECONDS


def _email_reminders_enabled(settings: Settings) -> bool:
    # Not without a provider: a mock "send" marked reminders sent that never went out.
    return settings.email_reminders_scheduler_enabled and email_gateway.can_send(settings)


async def _email_cycle(settings: Settings, lock: CycleLock) -> None:
    async with SessionLocal() as session:
        count = await reminder_emails.run_email_reminder_cycle(
            session, settings, keep_lock=lock.refresh
        )
        if count:
            logger.info("Email reminder cycle sent count=%s", count)


async def run_email_reminder_cycle(settings: Settings) -> None:
    await run_locked_cycle(
        name="email reminders",
        lock_key=LOCK_KEY,
        lock_ttl_seconds=LOCK_TTL_SECONDS,
        enabled=_email_reminders_enabled(settings),
        fn=_email_cycle,
        settings=settings,
    )


async def start_email_reminder_scheduler(settings: Settings) -> None:
    if settings.email_reminders_scheduler_enabled and not _email_reminders_enabled(settings):
        logger.info("Email reminder scheduler not started: this process cannot send email")
    await start_periodic(
        name=_NAME,
        interval_seconds=INTERVAL_SECONDS,
        enabled=_email_reminders_enabled(settings),
        cycle=run_email_reminder_cycle,
        settings=settings,
    )


async def stop_email_reminder_scheduler() -> None:
    await stop_periodic(_NAME)
