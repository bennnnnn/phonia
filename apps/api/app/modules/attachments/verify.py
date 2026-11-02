"""Check an uploaded object once: a verified row is never read again.

``POST /attachments/{id}/confirm`` (and a first ``/file`` or ``/url`` read of a
row not yet checked) downloads the object to compare its bytes with the
declared type. That ran on every call: twenty parallel confirms of one 10 MB
file held 200 MB on a 1 GB machine. A verified row now returns at once, and one
request per attachment checks at a time (a short Redis lock); the others wait
for it and then read the row it left.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.redis import get_redis_client
from app.core.redis_lock import acquire_lock, release_lock
from app.exceptions import RedisUnavailableError
from app.gateways.storage_gateway import StorageGateway
from app.models.orm import Attachment
from app.modules.attachments import repository as attachments_repo
from app.modules.attachments.content import ensure_verified_or_purge

LOCK_PREFIX = "attachments:verify:"
# A peer waits this long for the check in progress, then is told to retry.
WAIT_SECONDS = 10.0
POLL_SECONDS = 0.2
# Calls one check makes to storage: a HEAD, the GET, its read and the body close.
_STORAGE_CALLS_PER_CHECK = 4
_LOCK_MARGIN_SECONDS = 15


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """``error`` refuses the upload; ``removed`` says this call purged the row; ``busy``
    says another request was still checking it after the wait."""

    error: str | None = None
    removed: bool = False
    busy: bool = False


def lock_key(attachment_id: UUID) -> str:
    return f"{LOCK_PREFIX}{attachment_id}"


def _lock_ttl_seconds(settings: Settings) -> int:
    """Outlives the longest check the storage deadline allows, so a lock frees itself
    only after its holder can no longer be running."""
    calls = _STORAGE_CALLS_PER_CHECK * settings.r2_call_deadline_seconds
    return int(calls) + _LOCK_MARGIN_SECONDS


async def _wait_for_lock(key: str, ttl_seconds: int) -> str | None:
    redis = get_redis_client()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    try:
        while True:
            token = await acquire_lock(redis, key, ttl_seconds)
            if token is not None or loop.time() >= deadline:
                return token
            await asyncio.sleep(POLL_SECONDS)
    except RedisError as exc:
        raise RedisUnavailableError() from exc


async def verify_upload_once(
    session: AsyncSession,
    settings: Settings,
    gateway: StorageGateway,
    row: Attachment,
    user_id: UUID,
) -> VerifyResult:
    """Check *row*'s stored bytes unless it is already verified (R2 only)."""
    if row.verified_at is not None:
        return VerifyResult()
    key = lock_key(row.id)
    token = await _wait_for_lock(key, _lock_ttl_seconds(settings))
    if token is None:
        return VerifyResult(busy=True)
    try:
        # A peer that held the lock may have verified or purged the row meanwhile.
        fresh = await attachments_repo.get_by_id(session, row.id, user_id)
        await session.commit()  # no transaction open across the download
        if fresh is None:
            return VerifyResult(error="Upload not found")
        if fresh.verified_at is not None:
            return VerifyResult()
        error, removed = await ensure_verified_or_purge(
            gateway,
            session,
            attachment_id=fresh.id,
            content_type=fresh.content_type,
            storage_key=fresh.storage_key,
            declared_size=fresh.size_bytes,
        )
        return VerifyResult(error=error, removed=removed)
    finally:
        await release_lock(get_redis_client(), key, token)
