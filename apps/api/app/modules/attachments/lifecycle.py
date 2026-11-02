"""Attachment storage cleanup — message deletes and orphan reaping."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.gateways.storage_gateway import get_storage_gateway
from app.modules.attachments import repository as attachments_repo
from app.modules.attachments.quota import has_current_upload_reservation, upload_counter
from app.modules.attachments.thumbnails import delete_thumbnails
from app.services.quota import counters

logger = logging.getLogger(__name__)

# Failed R2 deletes, retried by the orphan reaper: member = storage key, score = when the
# next attempt is due. A plain set had no bound and was read whole every cycle.
PENDING_STORAGE_DELETE_KEY = "recall:storage:pending_delete:due"
_PENDING_ATTEMPTS_KEY = "recall:storage:pending_delete:attempts"
# The set before it kept order and attempts; its members move over on the next retry pass.
_LEGACY_PENDING_KEY = "recall:storage:pending_delete"
_PENDING_MAX = 50_000
_PENDING_PAGE = 500
_PENDING_MAX_ATTEMPTS = 10
_PENDING_FIRST_RETRY_S = 3_600
_PENDING_MAX_RETRY_S = 86_400


async def detach_attachments_for_messages(
    session: AsyncSession,
    message_ids: list[UUID],
    *,
    commit: bool = True,
) -> list[str]:
    """Remove attachment DB rows/chunks; return storage keys for deferred byte delete.

    Callers that need transactional safety with a parent commit should pass
    ``commit=False``, commit the parent session, then ``delete_storage_keys``.
    """
    if not message_ids:
        return []
    rows = await attachments_repo.list_for_message_ids(session, message_ids)
    if not rows:
        return []
    attachment_ids = [row.id for row in rows]
    storage_keys = [row.storage_key for row in rows if row.storage_key]
    # The FK cascade deletes chunks after locking their attachment parent,
    # matching the index worker's lock order.
    await attachments_repo.delete_rows(session, attachment_ids, commit=commit)
    return storage_keys


async def delete_storage_keys(settings: Settings, storage_keys: list[str]) -> list[str]:
    """Best-effort byte delete. Returns keys whose delete failed (keep those rows)."""
    if not storage_keys:
        return []
    gateway = get_storage_gateway(settings)
    results = await asyncio.gather(
        *(gateway.delete_bytes(key) for key in storage_keys),
        return_exceptions=True,
    )
    # An object's stored thumbnails go with it. A failed one is queued: the retry
    # deletes the (gone) object again, then its thumbnails.
    thumbs = await asyncio.gather(
        *(delete_thumbnails(gateway, key) for key in storage_keys), return_exceptions=True
    )
    thumbs_failed = [
        key for key, done in zip(storage_keys, thumbs, strict=True) if done is not True
    ]
    if thumbs_failed:
        await enqueue_failed_storage_deletes(thumbs_failed)
    failed: list[str] = []
    for key, result in zip(storage_keys, results, strict=False):
        if isinstance(result, Exception):
            logger.warning("Failed to delete attachment bytes key=%s", key, exc_info=result)
            failed.append(key)
    return failed


async def enqueue_failed_storage_deletes(keys: list[str]) -> None:
    """Keep failed R2 deletes so the orphan reaper can retry after rows are gone."""
    if not keys:
        return
    try:
        redis = get_redis_client()
        await redis.zadd(PENDING_STORAGE_DELETE_KEY, dict.fromkeys(keys, time.time()), nx=True)
        size = int(await redis.zcard(PENDING_STORAGE_DELETE_KEY))
        if size > _PENDING_MAX:
            # Past the cap the latest-due keys go: those objects stay in R2 until a sweep.
            await redis.zremrangebyrank(PENDING_STORAGE_DELETE_KEY, _PENDING_MAX, -1)
            logger.error("Pending storage deletes over %s; dropped the latest-due", _PENDING_MAX)
    except Exception:
        logger.warning("Could not enqueue failed storage deletes", exc_info=True)


async def _move_legacy_pending(redis: Redis) -> None:
    raw = await redis.smembers(_LEGACY_PENDING_KEY)
    keys = [item for item in raw if isinstance(item, str)]
    if keys:
        await redis.zadd(PENDING_STORAGE_DELETE_KEY, dict.fromkeys(keys, time.time()), nx=True)
    await redis.delete(_LEGACY_PENDING_KEY)


async def retry_pending_storage_deletes(settings: Settings) -> int:
    """Retry the deletes that are due, a page at a time, backing off up to a day each."""
    try:
        redis = get_redis_client()
        await _move_legacy_pending(redis)
        now = time.time()
        keys = cast(
            list[str],
            await redis.zrangebyscore(
                PENDING_STORAGE_DELETE_KEY, "-inf", now, start=0, num=_PENDING_PAGE
            ),
        )
    except Exception:
        logger.debug("Pending storage-delete retry skipped", exc_info=True)
        return 0
    if not keys:
        return 0
    still_failed = set(await delete_storage_keys(settings, keys))
    succeeded = [key for key in keys if key not in still_failed]
    try:
        if succeeded:
            await redis.zrem(PENDING_STORAGE_DELETE_KEY, *succeeded)
            await redis.hdel(_PENDING_ATTEMPTS_KEY, *succeeded)
        for key in still_failed:
            await _back_off_pending(redis, key, now)
    except Exception:
        logger.debug("Could not update pending storage deletes", exc_info=True)
    return len(succeeded)


async def _back_off_pending(redis: Redis, key: str, now: float) -> None:
    attempts = int(await redis.hincrby(_PENDING_ATTEMPTS_KEY, key, 1))
    if attempts >= _PENDING_MAX_ATTEMPTS:
        logger.error("Storage delete gave up after %s attempts key=%s", attempts, key)
        await redis.zrem(PENDING_STORAGE_DELETE_KEY, key)
        await redis.hdel(_PENDING_ATTEMPTS_KEY, key)
        return
    wait = min(_PENDING_MAX_RETRY_S, _PENDING_FIRST_RETRY_S * 2 ** (attempts - 1))
    await redis.zadd(PENDING_STORAGE_DELETE_KEY, {key: now + wait})


async def purge_attachments_for_messages(
    session: AsyncSession,
    settings: Settings,
    message_ids: list[UUID],
) -> int:
    """Detach DB rows then delete stored bytes for attachments on ``message_ids``."""
    storage_keys = await detach_attachments_for_messages(session, message_ids, commit=True)
    failed = await delete_storage_keys(settings, storage_keys)
    await enqueue_failed_storage_deletes(failed)
    return len(storage_keys)


async def delete_objects_of_deleted_rows(settings: Settings, storage_keys: list[str]) -> None:
    """Delete the stored objects (and thumbnails) of rows already deleted and committed.

    Account delete calls it once the account's rows are gone. Best effort, never raises:
    a failed object is queued for the reaper's retry, and the account's ``storage_sweep``
    deletes everything left under ``{user_id}/``.
    """
    try:
        failed = await delete_storage_keys(settings, storage_keys)
    except Exception:
        logger.warning("Stored objects of a deleted account not deleted; queued", exc_info=True)
        failed = storage_keys
    await enqueue_failed_storage_deletes(failed)


async def reap_orphan_attachments(settings: Settings) -> int:
    """Delete bytes + rows for unlinked pending uploads and hidden send-clones.

    Uses a DB-first-then-storage order: the DB unlink check
    (``delete_unlinked_returning``) runs BEFORE storage deletion, so an
    attachment linked between list and delete time is NOT reaped (its row
    survives, its bytes are not touched). Previously storage was deleted
    first, which could leave a linked attachment with missing file content.

    Verified Library items that outlive their chat are not listed.

    Image uploads that are reaped also get their daily image-upload slot
    refunded — without this, an abandoned presign (never sent/confirmed)
    permanently consumes a slot the user can never get back, eventually
    locking them out of image uploads for the day.

    A cycle runs batches while they come back full, up to
    ``attachment_orphan_reap_batches_per_cycle``: one batch an hour cleared at most
    2,400 a day, fewer than one "delete all chats" by a heavy photo user leaves.
    """
    await retry_pending_storage_deletes(settings)
    reaped = 0
    for _ in range(max(1, settings.attachment_orphan_reap_batches_per_cycle)):
        listed, removed = await _reap_orphan_batch(settings)
        reaped += removed
        # A short batch is the end; one that removed nothing would list the same rows.
        if listed < settings.attachment_orphan_reap_limit or not removed:
            break
    if reaped:
        logger.info("Reaped %d orphan attachment(s)", reaped)
    return reaped


async def _reap_orphan_batch(settings: Settings) -> tuple[int, int]:
    """One batch: (orphans listed, rows removed with their bytes)."""
    async with SessionLocal() as session:
        orphans = await attachments_repo.list_orphans(
            session,
            older_than_hours=settings.attachment_orphan_grace_hours,
            pending_older_than_hours=settings.attachment_pending_orphan_hours,
            limit=settings.attachment_orphan_reap_limit,
        )
    if not orphans:
        return 0, 0

    # DB-first: delete rows that are still unlinked. This returns the storage
    # keys of rows actually removed — a row linked between list and delete
    # is NOT removed and its bytes are preserved.
    ids_to_delete = [row.id for row in orphans]
    async with SessionLocal() as session:
        removed_keys = await attachments_repo.delete_unlinked_returning(
            session, ids_to_delete, orphan_only=True
        )
    if not removed_keys:
        return len(orphans), 0

    # Storage cleanup for confirmed-removed rows only.
    removed_set = set(removed_keys)
    rows_to_refund = [row for row in orphans if row.storage_key in removed_set]
    failed = await delete_storage_keys(settings, removed_keys)
    await enqueue_failed_storage_deletes(failed)

    # Refund the daily upload slot of each reaped upload.
    if rows_to_refund:
        redis = get_redis_client()
        for row in rows_to_refund:
            if has_current_upload_reservation(row):
                try:
                    await counters.refund(upload_counter(row.content_type), redis, row.user_id)
                except Exception:
                    logger.warning(
                        "Upload quota refund failed user_id=%s", row.user_id, exc_info=True
                    )
    return len(orphans), len(removed_keys)


async def sweep_user_storage(settings: Settings, user_id: UUID) -> int:
    """Delete leftover objects under ``{user_id}/`` after account wipe.

    Complements ``delete_objects_of_deleted_rows`` when Redis pending-delete never
    ran. Prefix is the user UUID only — never ``/`` or ``..``.
    """
    prefix = f"{user_id}/"
    if ".." in prefix or prefix.startswith("/"):
        return 0
    gateway = get_storage_gateway(settings)
    deleted = await gateway.delete_prefix(prefix)
    if deleted:
        logger.info("storage_sweep user_id=%s deleted=%s", user_id, deleted)
    return deleted
