"""Authenticated account update, logout, and deletion workflows."""

import logging
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import user_cache
from app.core.access_tokens import REVOKED_SINCE_PREFIX
from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.jobs import JobSkipped, enqueue, purge_user_jobs, schedule_job
from app.core.validation import normalize_avatar_url
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.gateways import apple_revoke
from app.models.orm import User
from app.modules import memory as memory_service
from app.modules.account import quota_carryover
from app.modules.account import tokens as tokens_service
from app.modules.attachments import service as attachments_service
from app.modules.billing import plan as plan_service
from app.modules.chat import service as chats_service
from app.modules.memory import crud as memory_crud
from app.modules.suggestions import service as suggestions_service
from app.modules.todos import service as todos_service
from app.repositories import push_tokens as push_tokens_repo
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)


async def update_account(
    session: AsyncSession,
    user: User,
    settings: Settings,
    fields: dict[str, Any],
) -> User:
    # An older app still sends default_model: it chooses through the same rule.
    chosen = fields.pop("default_model", None)
    if chosen is not None and "enabled_models" not in fields:
        fields["enabled_models"] = plan_service.models_choosing(user, settings, chosen)
    if "enabled_models" in fields:
        fields["enabled_models"] = plan_service.validate_enabled_models_for_update(
            user,
            fields["enabled_models"],
            settings,
        )
    # A rename changes which saved name facts the memory block keeps (memory.user_name).
    memory_changed = (
        "memory_enabled" in fields and fields["memory_enabled"] != user.memory_enabled
    ) or ("name" in fields and fields["name"] != user.name)
    if fields.get("avatar_url"):
        try:
            avatar_url = normalize_avatar_url(fields["avatar_url"])
            if avatar_url is None:
                raise ValueError("Choose an uploaded photo that has finished uploading.")
            attachment_id = UUID(avatar_url.split("/")[2])
            if not await attachments_service.claim_profile_photo(session, attachment_id, user.id):
                raise ValueError("Choose an uploaded photo that has finished uploading.")
            fields["avatar_url"] = avatar_url
            updated = await users_repo.update(session, user, commit=False, **fields)
            user_id = updated.id
            await session.commit()
            await user_cache.publish_change(user_id)
            await session.refresh(updated)
        except BaseException:
            await session.rollback()
            raise
    else:
        updated = await users_repo.update(session, user, **fields)
    if memory_changed:
        await memory_service.invalidate_memory_block(user.id)
    return updated


async def upgrade_to_pro_for_dev(
    session: AsyncSession,
    user: User,
    *,
    plan: str = "pro",
) -> User:
    return await users_repo.update(session, user, plan=plan)


async def logout(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    access_token: str | None,
    refresh_token: str | None,
    expo_push_token: str | None = None,
) -> None:
    """End this device's session; with ``expo_push_token``, this device stops getting the
    account's reminders too. Signed out, a phone kept showing them on its lock screen.
    """
    if expo_push_token:
        # Before the revokes: the live session proves whose token this is, so a token
        # string alone never silences another account's device.
        user_id = await _session_user(redis, settings, access_token, refresh_token)
        if user_id is not None:
            await push_tokens_repo.delete_token(session, user_id, expo_push_token)
    if access_token and refresh_token:
        await tokens_service.revoke_access_token(redis, access_token, settings)
        await tokens_service.revoke_refresh_token(redis, refresh_token)
    elif refresh_token:
        await tokens_service.revoke_refresh_token(redis, refresh_token)
    elif access_token:
        # No refresh token (the phone could not read it): this device's session only.
        user_id = await tokens_service.verify_access_token(redis, access_token, settings)
        session_id = tokens_service.session_id_from_access_token(access_token, settings)
        if session_id:
            await tokens_service.end_session(redis, user_id, session_id, settings=settings)
        await tokens_service.revoke_access_token(redis, access_token, settings)


async def logout_everywhere(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user_id: UUID,
    *,
    access_token: str | None,
) -> None:
    """End every session, and forget every device's push token: no signed-out phone keeps
    getting this account's reminders."""
    await tokens_service.purge_user_sessions(redis, user_id, settings)
    if access_token:
        await tokens_service.revoke_access_token(redis, access_token, settings)
    await push_tokens_repo.delete_for_user(session, user_id)


async def _session_user(
    redis: Redis, settings: Settings, access_token: str | None, refresh_token: str | None
) -> UUID | None:
    """The account a live access or refresh token of this device belongs to."""
    if access_token:
        try:
            return await tokens_service.verify_access_token(redis, access_token, settings)
        except AuthenticationError:
            pass  # expired: the refresh token still proves the session
    return await tokens_service.refresh_token_user(redis, refresh_token) if refresh_token else None


# The account's sweep is also scheduled before its rows commit, in case the one queued
# after the commit is lost (Redis failing at that moment, or the process ending). It runs
# this long after and skips an account still there; a delete commits well within it.
# Its own type: a worker from before the existence check holds an entry of a type it
# does not know (docs/ROLLBACK.md), where it would sweep a live account's files.
SWEEP_BACKSTOP_SECONDS = 600
SWEEP_JOB = "storage_sweep"
SWEEP_BACKSTOP_JOB = "account_sweep_backstop"


async def delete_account(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
    *,
    apple_authorization_code: str | None = None,
) -> None:
    """Delete the account and everything stored for it: complete, or refused whole.

    1. The usage counters are carried (``quota_carryover``). Redis failing refuses the
       delete (503 ``unavailable``) with nothing undone.
    2. One transaction deletes every row; before it commits, the account's sweep is
       scheduled as a backstop (Redis refusing that refuses the delete too). The database
       failing rolls it all back: 503 ``unavailable``, still signed in, so the phone's
       retry deletes it, and the backstop finds the account and leaves it alone.
    3. Committed, the account is gone. Only then what is outside the database: every
       session ends, the stored files go, and the sweep is queued at once. None of these
       fails the request: each is idempotent and the sweep (``sweep_deleted_account``)
       does it again.

    The sessions and files used to go first: the database failing after them left the
    account signed out everywhere with its files deleted and every other row kept, and
    the phone read its retry's 401 as "deleted".

    *apple_authorization_code* is a fresh Sign in with Apple code the phone
    asked for; with it, the user's Apple grant is revoked last, best effort
    (``gateways/apple_revoke.py``), so Apple being down never blocks the delete.
    """
    apple_sub = user.apple_sub
    user_id = user.id
    await quota_carryover.save_on_delete(redis, settings, user)
    sweep, storage_keys = await _erase_account(session, redis, user_id)
    try:
        await tokens_service.purge_user_sessions(redis, user_id, settings)
    except Exception:
        logger.warning("Session purge after delete failed; its sweep ends them", exc_info=True)
    await attachments_service.delete_account_files(settings, storage_keys)
    await enqueue(redis, SWEEP_JOB, sweep, dedupe_key=_sweep_dedupe_key(user_id))
    if apple_sub and apple_authorization_code:
        await apple_revoke.revoke_authorization_code(
            settings, apple_authorization_code, expected_sub=apple_sub
        )
    elif apple_sub:
        logger.info("Apple-linked account deleted without an Apple code; grant not revoked")


async def _erase_account(
    session: AsyncSession, redis: Redis, user_id: UUID
) -> tuple[dict[str, object], list[str]]:
    """Every row in one transaction, its backstop sweep scheduled before the commit.

    Returns the sweep's payload and the stored files' keys. Rolls back and raises on any
    failure, so nothing is deleted.
    """
    from app.modules.conversation.history import forget_user_chats

    try:
        await users_repo.lock_for_delete(session, user_id)
        # Keyed by reply id, not user id, so only the rows can find them: read under the
        # lock, before the messages go, and dropped by the sweep.
        reply_ids = await chats_service.follow_up_reply_ids(session, user_id)
        sweep: dict[str, object] = {"user_id": str(user_id), "reply_ids": reply_ids}
        try:
            await schedule_job(
                redis,
                SWEEP_BACKSTOP_JOB,
                sweep,
                delay_s=SWEEP_BACKSTOP_SECONDS,
                dedupe_key=_sweep_dedupe_key(user_id),
            )
        except (RedisError, OSError) as exc:
            raise RedisUnavailableError() from exc
        storage_keys = await erase_user_rows(session, user_id, commit=False)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    user_cache.forget_user(user_id)
    forget_user_chats(user_id)
    return sweep, storage_keys


def _sweep_dedupe_key(user_id: UUID) -> str:
    return f"{SWEEP_JOB}:{user_id}"


async def sweep_deleted_account(
    settings: Settings, redis: Redis, user_id: UUID, reply_ids: list[str]
) -> None:
    """Finish a committed account delete: the worker's ``storage_sweep``.

    Ends every session, then drops the cached follow-up questions, every Redis key and
    job naming the user, and every stored object left under its prefix. Each step is
    idempotent and a failure retries the job. Raises ``JobSkipped`` while the account
    exists: the backstop of a delete that rolled back must leave it alone.
    """
    async with SessionLocal() as session:
        if await users_repo.get_by_id(session, user_id) is not None:
            raise JobSkipped("account still exists")
    await tokens_service.purge_user_sessions(redis, user_id, settings)
    await chats_service.forget_follow_up_questions(redis, reply_ids)
    await purge_user_redis_keys(redis, user_id)
    await purge_user_jobs(redis, user_id, keep_types=frozenset({SWEEP_JOB, SWEEP_BACKSTOP_JOB}))
    await attachments_service.sweep_account_storage(settings, user_id)


# Kept after a delete: the cutoff that keeps the deleted account's already
# issued access tokens rejected (it expires with them), and job markers.
_KEEP_AFTER_DELETE_PREFIXES = (REVOKED_SINCE_PREFIX, "jobdone:")
_PURGE_SCAN_COUNT = 1000
_PURGE_BATCH = 500


async def erase_user_rows(
    session: AsyncSession, user_id: UUID, *, commit: bool = True
) -> list[str]:
    """Every row of the account, the user's own last; the keys of its stored files.

    Under the user's row lock (memory writers take it first) each module deletes its
    rows, children before the chats and the user they hang from; ``users_repo`` then
    deletes the core rows and the user. Commits unless ``commit=False``.
    """
    await users_repo.lock_for_delete(session, user_id)
    for delete_rows in (
        memory_crud.delete_user_rows,
        todos_service.delete_user_rows,
        suggestions_service.delete_user_rows,
    ):
        await delete_rows(session, user_id)
    storage_keys = await attachments_service.delete_user_rows(session, user_id)
    await users_repo.delete_user(session, user_id, commit=commit)
    return storage_keys


async def purge_user_redis_keys(redis: Redis, user_id: UUID) -> int:
    """Delete every Redis key that names a deleted user. Returns the count.

    Memory caches, reminder and settings cards, web-search and voice
    lookups, usage counters and history-scan state are all keyed by user id.
    One SCAN pass covers them, including key families added later. Runs in
    the worker (``storage_sweep``): a full keyspace scan does not belong on
    the request path.
    """
    needle = str(user_id)
    batch: list[str] = []
    removed = 0
    async for raw in redis.scan_iter(match=f"*{needle}*", count=_PURGE_SCAN_COUNT):
        key = raw.decode() if isinstance(raw, bytes) else str(raw)
        if key.startswith(_KEEP_AFTER_DELETE_PREFIXES) or needle not in key:
            continue
        batch.append(key)
        if len(batch) >= _PURGE_BATCH:
            removed += int(await redis.unlink(*batch) or 0)
            batch = []
    if batch:
        removed += int(await redis.unlink(*batch) or 0)
    if removed:
        logger.info("Account Redis purge user_id=%s removed=%s", user_id, removed)
    return removed


__all__ = [
    "SWEEP_BACKSTOP_JOB",
    "SWEEP_JOB",
    "delete_account",
    "logout",
    "purge_user_redis_keys",
    "sweep_deleted_account",
    "update_account",
    "upgrade_to_pro_for_dev",
]
