"""RevenueCat webhook — keep backend plan in sync with store entitlements."""

from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_redis, get_settings_dep
from app.core.redis_lock import acquire_lock
from app.core.request_limits import reject_oversized
from app.models.orm import User
from app.modules.billing import entitlements
from app.modules.billing import revenuecat as webhook_service
from app.modules.notifications import enqueue_purchase_receipt

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
plans_router = APIRouter(prefix="/billing", tags=["billing"])


class PlanOut(BaseModel):
    id: str
    features: list[str]
    allowances: dict[str, int]


class PlansOut(BaseModel):
    current: str
    plans: list[PlanOut]


@plans_router.get("/plans", response_model=PlansOut)
async def list_plans(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
) -> PlansOut:
    """Every plan with what it includes and its numbers, for the paywall.

    Prices are not here: the app reads them, localized, from the store offering.
    """
    return PlansOut(
        current=entitlements.plan_of(user),
        plans=[PlanOut.model_validate(item) for item in entitlements.plan_catalog(settings)],
    )


# Cap before body parse — endpoint is rate-limit-exempt and auth runs in-handler.
_MAX_WEBHOOK_BODY_BYTES = 64 * 1024


def _secrets_match(candidate: str, expected: str) -> bool:
    # hmac.compare_digest(str, str) raises TypeError on non-ASCII. Starlette
    # decodes headers as latin-1, so a 0x80-0xFF byte would 500 this
    # rate-limit-exempt route instead of 401.
    if not candidate.isascii() or not expected.isascii():
        return False
    return hmac.compare_digest(candidate, expected)


def _verify_auth(authorization: str | None, settings: Settings) -> None:
    expected = settings.revenuecat_webhook_auth.strip()
    if not expected:
        # Never skip auth based on `environment` alone — a dev config on a
        # public host would let anyone grant themselves Pro. Require an
        # explicit opt-in (DEV_ALLOW_UNAUTHED_WEBHOOKS) for local testing.
        if settings.dev_allow_unauthed_webhooks:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RevenueCat webhook not configured",
        )
    token = (authorization or "").strip()
    # Accept either the raw shared secret or a Bearer-prefixed form. Compare in
    # constant time to avoid leaking whether the prefix matched via timing.
    candidates = (
        [token, token.removeprefix("Bearer ").strip()] if token.startswith("Bearer ") else [token]
    )
    authorized = any(_secrets_match(c, expected) for c in candidates)
    if not authorized:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.post("/revenuecat", status_code=status.HTTP_200_OK)
async def revenuecat_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> None:
    # Auth + size before JSON parse — unauthenticated body work is a DoS vector
    # (this path is exempt from the global REST rate limiter).
    _verify_auth(request.headers.get("Authorization"), settings)
    reject_oversized(request, b"", _MAX_WEBHOOK_BODY_BYTES, "Webhook payload too large")
    body = await request.body()
    reject_oversized(request, body, _MAX_WEBHOOK_BODY_BYTES, "Webhook payload too large")
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        )
    payload: dict[str, Any] = parsed

    try:
        await webhook_service.process_event(
            session,
            redis,
            settings,
            payload,
            subscriber_lock=acquire_lock,
            receipt_enqueuer=enqueue_purchase_receipt,
        )
    except webhook_service.SubscriberBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RevenueCat webhook busy for subscriber",
        ) from exc
    except webhook_service.SubscriberFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RevenueCat subscriber lookup failed",
        ) from exc
