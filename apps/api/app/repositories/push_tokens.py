import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import sentry
from app.exceptions import PushTokenBindError
from app.models.orm import PushToken

logger = logging.getLogger(__name__)


def _normalize_device_id(device_id: str | None) -> str | None:
    if device_id is None:
        return None
    cleaned = device_id.strip()
    return cleaned or None


def _report_rebind(*, prior_user_id: UUID, new_user_id: UUID) -> None:
    """Best-effort visibility when a token moves between accounts."""
    logger.warning(
        "push token rebound prior_user=%s new_user=%s",
        prior_user_id,
        new_user_id,
    )
    sentry.report_breadcrumb(
        "push.token",
        "push token rebound across users",
        level="warning",
        data={"prior_user_id": str(prior_user_id), "new_user_id": str(new_user_id)},
    )


async def upsert(
    session: AsyncSession,
    *,
    user_id: UUID,
    expo_push_token: str,
    platform: str,
    device_id: str | None = None,
    android_channels: str | None = None,
) -> PushToken:
    incoming_device = _normalize_device_id(device_id)
    result = await session.execute(
        select(PushToken).where(PushToken.expo_push_token == expo_push_token)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = PushToken(
            user_id=user_id,
            expo_push_token=expo_push_token,
            platform=platform,
            device_id=incoming_device,
            android_channels=android_channels,
        )
        session.add(row)
    elif row.user_id == user_id:
        # Same user re-registering — refresh platform/device metadata.
        row.platform = platform
        if incoming_device is not None:
            row.device_id = incoming_device
        if android_channels is not None:
            row.android_channels = android_channels
    else:
        # Device account switch: only allow when the caller proves possession of
        # the same install (device_id). A stolen Expo token string alone must
        # not silence the prior owner. Full attestation remains deferred.
        if incoming_device is None:
            raise PushTokenBindError(
                "device_id is required to move a push token to another account."
            )
        prior_device = _normalize_device_id(row.device_id)
        if prior_device is None:
            # A row from before device ids has no install to match, so any
            # device id would pass. It stays with its owner; the owner's next
            # registration records the device and later moves follow the rule.
            raise PushTokenBindError("Push token is bound to another account.")
        if prior_device != incoming_device:
            raise PushTokenBindError("Push token is bound to a different device.")
        prior_user_id = row.user_id
        await session.delete(row)
        await session.flush()
        row = PushToken(
            user_id=user_id,
            expo_push_token=expo_push_token,
            platform=platform,
            device_id=incoming_device,
            android_channels=android_channels,
        )
        session.add(row)
        _report_rebind(prior_user_id=prior_user_id, new_user_id=user_id)
    if incoming_device:
        await delete_stale_tokens_for_device(
            session,
            user_id=user_id,
            device_id=incoming_device,
            keep_expo_push_token=expo_push_token,
        )
    await session.commit()
    await session.refresh(row)
    return row


async def delete_stale_tokens_for_device(
    session: AsyncSession,
    *,
    user_id: UUID,
    device_id: str,
    keep_expo_push_token: str,
) -> int:
    """Remove rotated Expo tokens for the same physical device."""
    result = await session.execute(
        delete(PushToken).where(
            PushToken.user_id == user_id,
            PushToken.device_id == device_id,
            PushToken.expo_push_token != keep_expo_push_token,
        )
    )
    return int(cast(CursorResult[Any], result).rowcount or 0)


async def delete_token(session: AsyncSession, user_id: UUID, expo_push_token: str) -> bool:
    result = await session.execute(
        delete(PushToken).where(
            PushToken.user_id == user_id,
            PushToken.expo_push_token == expo_push_token,
        )
    )
    await session.commit()
    return cast(CursorResult[Any], result).rowcount > 0


async def delete_for_user(session: AsyncSession, user_id: UUID) -> int:
    """Every device's token for one account (sign out everywhere)."""
    result = await session.execute(delete(PushToken).where(PushToken.user_id == user_id))
    await session.commit()
    return int(cast(CursorResult[Any], result).rowcount or 0)


async def delete_by_token(session: AsyncSession, expo_push_token: str) -> int:
    """Delete a push token by its string (used for pruning invalid tokens)."""
    result = await session.execute(
        delete(PushToken).where(PushToken.expo_push_token == expo_push_token)
    )
    await session.commit()
    return int(cast(CursorResult[Any], result).rowcount or 0)


async def list_for_user(session: AsyncSession, user_id: UUID) -> list[PushToken]:
    result = await session.execute(select(PushToken).where(PushToken.user_id == user_id))
    return list(result.scalars().all())


async def list_for_users(session: AsyncSession, user_ids: list[UUID]) -> list[PushToken]:
    """Batched list_for_user — one query across many users instead of one per user."""
    if not user_ids:
        return []
    result = await session.execute(select(PushToken).where(PushToken.user_id.in_(user_ids)))
    return list(result.scalars().all())
