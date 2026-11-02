"""Sync user plan from RevenueCat entitlements."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import user_cache
from app.core.config import Settings
from app.exceptions import DomainError
from app.gateways import revenuecat_gateway
from app.models.orm import User
from app.modules.billing.entitlements import PLANS, plan_from_entitlements
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)


async def is_stale_rc_event(
    session: AsyncSession,
    app_user_id: str,
    event_timestamp_ms: int,
) -> bool:
    """True when *event_timestamp_ms* is older than the user's last RC event."""
    try:
        user_id = UUID(app_user_id)
    except ValueError:
        return False
    user = await users_repo.get_by_id(session, user_id)
    if user is None or user.rc_last_event_at_ms is None:
        return False
    return event_timestamp_ms < user.rc_last_event_at_ms


async def advance_rc_event_watermark(
    session: AsyncSession,
    app_user_id: str,
    event_timestamp_ms: int,
) -> None:
    """Move the per-user RC event watermark forward (never backward)."""
    try:
        user_id = UUID(app_user_id)
    except ValueError:
        return
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        return
    if user.rc_last_event_at_ms is not None and event_timestamp_ms <= user.rc_last_event_at_ms:
        return
    await users_repo.update(session, user, rc_last_event_at_ms=event_timestamp_ms)


def _plan_from_revenuecat_payload(payload: dict[str, Any], settings: Settings) -> str:
    entitlement_ids = (
        settings.revenuecat_entitlement_id,
        settings.revenuecat_plus_entitlement_id,
    )
    active = {
        entitlement_id
        for entitlement_id in entitlement_ids
        if entitlement_id and revenuecat_gateway.entitlement_active(payload, entitlement_id)
    }
    return plan_from_entitlements(active, settings)


async def resolve_plan_from_revenuecat(settings: Settings, app_user_id: str) -> str | None:
    """HTTP-only: the plan (``pro`` / ``plus`` / ``free``) the subscriber API
    grants now, or None if the secret is missing or the fetch failed. Never
    defaults to a paid plan."""
    if not settings.revenuecat_secret_key.strip():
        return None
    payload = await revenuecat_gateway.fetch_subscriber(
        settings.revenuecat_secret_key,
        app_user_id,
    )
    if payload is None:
        return None
    return _plan_from_revenuecat_payload(payload, settings)


class StoreUnreachableError(DomainError):
    """503 ``store_unreachable``: RevenueCat did not answer, so the plan is unknown."""

    status_code = 503
    default_code = "store_unreachable"


async def sync_user_plan_from_revenuecat(
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> User:
    """The user with the plan RevenueCat grants now.

    A store that does not answer is a 503, not the unchanged user: after a purchase
    the phone then says the plan will update shortly instead of closing on "Free".
    """
    plan = await resolve_plan_from_revenuecat(settings, str(user.id))
    if plan is None:
        raise StoreUnreachableError("Couldn't reach the store to check your plan. Try again.")
    if plan == user.plan:
        return user
    updated = await users_repo.update(session, user, plan=plan)
    logger.info("Updated plan from RevenueCat user=%s plan=%s", user.id, plan)
    return updated


async def apply_plan_for_app_user_id(
    session: AsyncSession,
    app_user_id: str,
    *,
    plan: str,
) -> bool:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan {plan!r}")
    try:
        user_id = UUID(app_user_id)
    except ValueError:
        logger.warning("RevenueCat webhook ignored invalid app_user_id=%s", app_user_id)
        return False
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        logger.warning("RevenueCat webhook user not found id=%s", app_user_id)
        return False
    if user.plan == plan:
        # No change — return False so the caller doesn't fire a duplicate
        # receipt email on every RENEWAL/replay of an already-Pro user. A replay
        # may follow a change whose publish failed: publish it (core/user_cache).
        await user_cache.publish_change(user.id)
        return False
    await users_repo.update(session, user, plan=plan)
    logger.info("RevenueCat webhook set plan=%s user=%s", plan, user_id)
    return True


async def handle_revenuecat_transfer(
    session: AsyncSession,
    settings: Settings,
    *,
    new_app_user_id: str,
    transferred_from: list[str],
) -> bool:
    """Move entitlements between app user ids.

    Fetches the target's plan from the RevenueCat API *before* any writes, then
    upgrades the target and only then re-reads each source. Returns False when
    the target plan could not be resolved so the webhook is not deduped and
    RevenueCat can retry. Never defaults the target to a paid plan.
    """
    cleaned_new = new_app_user_id.strip()
    if not cleaned_new:
        return False
    try:
        user_id = UUID(cleaned_new)
    except ValueError:
        logger.warning("RevenueCat TRANSFER ignored invalid app_user_id=%s", cleaned_new)
        return False

    plan = await resolve_plan_from_revenuecat(settings, cleaned_new)
    if plan is None:
        logger.warning(
            "RevenueCat TRANSFER deferred; subscriber fetch failed app_user_id=%s",
            cleaned_new,
        )
        return False

    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        logger.warning("RevenueCat TRANSFER user not found id=%s", cleaned_new)
        return False
    if user.plan != plan:
        await apply_plan_for_app_user_id(session, cleaned_new, plan=plan)
        logger.info("RevenueCat TRANSFER set plan=%s user=%s", plan, user_id)

    for old_id in transferred_from:
        cleaned = old_id.strip()
        if cleaned:
            await _resync_transfer_source(session, settings, cleaned)
    return True


async def _resync_transfer_source(
    session: AsyncSession, settings: Settings, app_user_id: str
) -> None:
    """The plan a source keeps after its entitlement moved: any other grant it holds.

    A source can still hold another product, store or promotional grant, and
    the hourly reconcile only re-checks paid rows, so setting it to free
    would stick until the app reopened. Unreadable falls back to free, as
    before: the moved entitlement is no longer this account's.
    """
    # The previous write re-read its row; end that transaction before the RevenueCat call.
    await session.commit()
    plan = await resolve_plan_from_revenuecat(settings, app_user_id)
    if plan is None:
        logger.warning("RevenueCat TRANSFER source unreadable; free app_user_id=%s", app_user_id)
        plan = "free"
    await apply_plan_for_app_user_id(session, app_user_id, plan=plan)
