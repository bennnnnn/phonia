"""RevenueCat REST API — subscriber entitlement lookup."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core import sentry
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

REVENUECAT_API = "https://api.revenuecat.com/v1/subscribers"
REVENUECAT_TIMEOUT_SECONDS = 15.0


async def fetch_subscriber(secret_key: str, app_user_id: str) -> dict[str, Any] | None:
    if not secret_key.strip():
        return None
    url = f"{REVENUECAT_API}/{app_user_id}"
    try:
        response = await get_pooled_client(REVENUECAT_TIMEOUT_SECONDS).get(
            url,
            headers={
                "Authorization": f"Bearer {secret_key.strip()}",
                "Accept": "application/json",
            },
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception:
        logger.exception("RevenueCat subscriber fetch failed user=%s", app_user_id)
        sentry.report_breadcrumb(
            "billing.revenuecat",
            "subscriber fetch failed",
            level="error",
            data={"app_user_id": app_user_id},
        )
        sentry.report_message("RevenueCat subscriber fetch failed", level="warning")
        return None


def _in_future(raw: object, field: str) -> bool:
    """True when *raw* is an ISO-8601 time after now; a missing or bad one is not."""
    if not isinstance(raw, str) or not raw.strip():
        return False
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Invalid RevenueCat %s: %s", field, raw)
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment > datetime.now(UTC)


def entitlement_active(payload: dict[str, Any], entitlement_id: str) -> bool:
    """Whether the subscriber holds *entitlement_id* now.

    No ``expires_date`` is a grant that never ends (lifetime, promotional).
    Otherwise it holds until ``expires_date`` or, while a renewal is failing
    (BILLING_ISSUE), until the store's ``grace_period_expires_date``,
    whichever is later.
    """
    subscriber = payload.get("subscriber")
    if not isinstance(subscriber, dict):
        return False
    entitlements = subscriber.get("entitlements")
    if not isinstance(entitlements, dict):
        return False
    ent = entitlements.get(entitlement_id)
    if not isinstance(ent, dict):
        return False
    expires_raw = ent.get("expires_date")
    if not isinstance(expires_raw, str) or not expires_raw.strip():
        return True
    return _in_future(expires_raw, "expires_date") or _in_future(
        ent.get("grace_period_expires_date"), "grace_period_expires_date"
    )
