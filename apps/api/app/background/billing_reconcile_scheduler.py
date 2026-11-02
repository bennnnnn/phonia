"""Periodic RevenueCat entitlement check for users on a paid plan.

A lost webhook (or exhausted retry after a non-200) can leave a paid plan after
the store has already revoked or changed it. App-open sync only helps if they
reopen the app. This cycle re-verifies every paid row (plus and pro) against
RevenueCat's REST API, so a lapsed plan drops and a Pro -> Plus change lands.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.background.periodic import (
    CycleLock,
    lock_ttl_yield_next_tick,
    run_locked_cycle,
    start_periodic,
    stop_periodic,
)
from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules.billing import subscription as subscription_service
from app.modules.billing.entitlements import PAID_PLANS, PLANS
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)

_NAME = "billing_reconcile"
LOCK_KEY = "recall:billing_reconcile:lock"


def _scheduler_enabled(settings: Settings) -> bool:
    return settings.billing_reconcile_enabled and bool(settings.revenuecat_secret_key.strip())


async def _billing_cycle(settings: Settings, lock: CycleLock) -> None:
    if not settings.revenuecat_secret_key.strip():
        return
    for paid_plan in (plan for plan in PLANS if plan in PAID_PLANS):
        if not await _reconcile_plan(settings, lock, paid_plan):
            return


async def _reconcile_plan(settings: Settings, lock: CycleLock, current_plan: str) -> bool:
    """Re-check every row on *current_plan*. False when the cycle must stop."""
    after_id: UUID | None = None
    batch = max(1, settings.billing_reconcile_batch_size)
    while True:
        async with SessionLocal() as session:
            ids = await users_repo.list_ids_by_plan(
                session, plan=current_plan, after_id=after_id, limit=batch
            )
        if not ids:
            return True
        for user_id in ids:
            plan = await subscription_service.resolve_plan_from_revenuecat(settings, str(user_id))
            if plan is not None and plan != current_plan:
                async with SessionLocal() as session:
                    await subscription_service.apply_plan_for_app_user_id(
                        session, str(user_id), plan=plan
                    )
                    logger.info("Billing reconcile set plan=%s user=%s", plan, user_id)
            if not await lock.refresh():
                logger.warning("Billing reconcile lock lost; stopping cycle")
                return False
            await asyncio.sleep(settings.billing_reconcile_rest_gap_seconds)
        after_id = ids[-1]


async def run_billing_reconcile_cycle(settings: Settings) -> None:
    await run_locked_cycle(
        name="billing reconcile",
        lock_key=LOCK_KEY,
        lock_ttl_seconds=lock_ttl_yield_next_tick(settings.billing_reconcile_interval_seconds),
        enabled=_scheduler_enabled(settings),
        fn=_billing_cycle,
        settings=settings,
    )


async def start_billing_reconcile_scheduler(settings: Settings) -> None:
    await start_periodic(
        name=_NAME,
        interval_seconds=max(1, settings.billing_reconcile_interval_seconds),
        enabled=_scheduler_enabled(settings),
        cycle=run_billing_reconcile_cycle,
        settings=settings,
    )


async def stop_billing_reconcile_scheduler() -> None:
    await stop_periodic(_NAME)
