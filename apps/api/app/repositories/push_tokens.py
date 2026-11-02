import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    max_per_user: int | None = None,
) -> PushToken:
    """Register ``expo_push_token`` for ``user_id``; commits.

    One statement inserts a new token or refreshes the caller's own, so two registrations
    of the same token at once (an app start and a permission grant) can no longer both
    insert and fail one on ``uq_push_tokens_expo_token``. A token another account holds
    moves only by the device rule (``_move_from_other_account``). ``max_per_user`` keeps
    that many of the account's most recently registered tokens; the oldest go.
    """
    incoming_device = _normalize_device_id(device_id)
    row = await _insert_or_refresh_own(
        session,
        user_id=user_id,
        expo_push_token=expo_push_token,
        platform=platform,
        device_id=incoming_device,
        android_channels=android_channels,
    )
    if row is None:
        row = await _move_from_other_account(
            session,
            user_id=user_id,
            expo_push_token=expo_push_token,
            platform=platform,
            device_id=incoming_device,
            android_channels=android_channels,
        )
    if incoming_device:
        await delete_stale_tokens_for_device(
            session,
            user_id=user_id,
            device_id=incoming_device,
            keep_expo_push_token=expo_push_token,
        )
    if max_per_user is not None:
        await _prune_beyond(session, user_id=user_id, keep_id=row.id, limit=max_per_user)
    await session.commit()
    await session.refresh(row)
    return row


async def _insert_or_refresh_own(
    session: AsyncSession,
    *,
    user_id: UUID,
    expo_push_token: str,
    platform: str,
    device_id: str | None,
    android_channels: str | None,
) -> PushToken | None:
    """INSERT ... ON CONFLICT: a new token's row, or the caller's own refreshed (a missing
    device id or channel set keeps the stored one); None when another account holds it."""
    insert = pg_insert(PushToken).values(
        id=uuid4(),
        user_id=user_id,
        expo_push_token=expo_push_token,
        platform=platform,
        device_id=device_id,
        android_channels=android_channels,
    )
    stmt = insert.on_conflict_do_update(
        index_elements=[PushToken.expo_push_token],
        set_={
            "platform": insert.excluded.platform,
            "device_id": func.coalesce(insert.excluded.device_id, PushToken.device_id),
            "android_channels": func.coalesce(
                insert.excluded.android_channels, PushToken.android_channels
            ),
            "updated_at": func.now(),
        },
        where=PushToken.user_id == insert.excluded.user_id,
    ).returning(PushToken)
    result = await session.execute(stmt, execution_options={"populate_existing": True})
    return result.scalar_one_or_none()


async def _move_from_other_account(
    session: AsyncSession,
    *,
    user_id: UUID,
    expo_push_token: str,
    platform: str,
    device_id: str | None,
    android_channels: str | None,
) -> PushToken:
    """Move a token another account holds, when the caller proves the same install."""
    result = await session.execute(
        select(PushToken).where(PushToken.expo_push_token == expo_push_token).with_for_update()
    )
    row = result.scalar_one_or_none()
    # Device account switch: only allow when the caller proves possession of the same
    # install (device_id). A stolen Expo token string alone must not silence the prior
    # owner. Full attestation remains deferred.
    if device_id is None:
        raise PushTokenBindError("device_id is required to move a push token to another account.")
    if row is None:
        # Its holder deleted it meanwhile: the token is free again.
        raise PushTokenBindError("Push token is bound to another account.")
    prior_device = _normalize_device_id(row.device_id)
    if prior_device is None:
        # A row from before device ids has no install to match, so any device id would
        # pass. It stays with its owner; the owner's next registration records the
        # device and later moves follow the rule.
        raise PushTokenBindError("Push token is bound to another account.")
    if prior_device != device_id:
        raise PushTokenBindError("Push token is bound to a different device.")
    prior_user_id = row.user_id
    row.user_id = user_id
    row.platform = platform
    row.device_id = device_id
    row.android_channels = android_channels
    row.updated_at = datetime.now(UTC)
    await session.flush()
    _report_rebind(prior_user_id=prior_user_id, new_user_id=user_id)
    return row


async def _prune_beyond(session: AsyncSession, *, user_id: UUID, keep_id: UUID, limit: int) -> int:
    """Delete the account's tokens past its ``limit`` newest, never ``keep_id``."""
    newest = (
        select(PushToken.id)
        .where(PushToken.user_id == user_id, PushToken.id != keep_id)
        .order_by(PushToken.updated_at.desc(), PushToken.id.desc())
        .limit(max(0, limit - 1))
    )
    result = await session.execute(
        delete(PushToken).where(
            PushToken.user_id == user_id,
            PushToken.id != keep_id,
            PushToken.id.not_in(newest.scalar_subquery()),
        )
    )
    pruned = int(cast(CursorResult[Any], result).rowcount or 0)
    if pruned:
        logger.info("Pruned push tokens over the per-account cap user=%s count=%s", user_id, pruned)
    return pruned


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
