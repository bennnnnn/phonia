"""One pass over a user's recent chats, so memory starts from what they already said.

Live extraction only reads new turns. When someone opens the Memory screen for
the first time (or memory missed their earlier chats), this job reads the user
lines of their most recent chats once and records that it did.

Chats are read newest first, and each pass only adds facts memory is missing,
so an older line never overrules a newer one. A chat that could not be read
(provider error, busy memory) is tried again on a later pass; the chats already
read are skipped. After ``_PASS_LIMIT`` passes the scan counts as done anyway.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import exists, select, update

from app.core import jobs, user_cache
from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.models.orm import Chat, Message, User
from app.modules.memory.extraction_workflow import extract_history_chat
from app.modules.memory.switch import memory_switch_on
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)

HISTORY_SCAN_JOB = "memory_history_scan"
HISTORY_SCAN_CHATS = 20
_QUEUED_TTL_SECONDS = 60 * 30
# A pass that missed chats waits this long before the next one may start.
_RETRY_AFTER_SECONDS = 60 * 30
_PASS_LIMIT = 3
_STATE_TTL_SECONDS = 60 * 60 * 24 * 7
_RETRY_STATE = "retry"


def _queued_key(user_id: UUID) -> str:
    return f"memory:history_scan:{user_id}"


def _read_chats_key(user_id: UUID) -> str:
    return f"memory:history_scan_read:{user_id}"


def _missed_passes_key(user_id: UUID) -> str:
    return f"memory:history_scan_missed:{user_id}"


async def request_history_scan(redis: Redis, user: User) -> bool:
    """Queue the scan unless it already ran. True while it is queued or running."""
    if not memory_switch_on(user) or user.memory_history_scanned_at is not None:
        return False
    key = _queued_key(user.id)
    try:
        if not await redis.set(key, "queued", ex=_QUEUED_TTL_SECONDS, nx=True):
            # Queued or running, unless the last pass missed chats and is waiting.
            return await redis.get(key) != _RETRY_STATE
    except Exception:
        logger.warning("memory history scan check failed user_id=%s", user.id, exc_info=True)
        return False
    try:
        await jobs.enqueue(
            redis,
            HISTORY_SCAN_JOB,
            {"user_id": str(user.id)},
            dedupe_key=jobs.unique_dedupe_key(f"{HISTORY_SCAN_JOB}:{user.id}"),
        )
    except Exception:
        logger.warning("memory history scan enqueue failed user_id=%s", user.id, exc_info=True)
        try:
            await redis.delete(key)
        except Exception:
            logger.debug("memory history scan unqueue failed user_id=%s", user.id, exc_info=True)
        return False
    return True


async def _recent_chat_ids(user_id: UUID) -> list[UUID]:
    """The most recently used chats with user lines, newest first."""
    has_user_lines = exists().where(Message.chat_id == Chat.id, Message.role == "user")
    async with SessionLocal() as session:
        result = await session.execute(
            select(Chat.id)
            .where(Chat.user_id == user_id, has_user_lines)
            .order_by(Chat.updated_at.desc())
            .limit(HISTORY_SCAN_CHATS)
        )
        return list(result.scalars().all())


async def _read_chat(settings: Settings, user_id: UUID, chat_id: UUID) -> bool:
    """True once the chat's lines were read, even with nothing to learn."""
    for attempt in range(jobs.LOCK_RETRY_ATTEMPTS):
        outcome = await extract_history_chat(settings, user_id=user_id, chat_id=chat_id)
        if outcome != "skipped_lock":
            return outcome is None
        await asyncio.sleep(jobs.LOCK_RETRY_BACKOFF_S * (attempt + 1))
    return False


async def _chats_read(redis: Redis, user_id: UUID) -> set[str]:
    try:
        members = await redis.smembers(_read_chats_key(user_id))
        return {m.decode() if isinstance(m, bytes) else m for m in members}
    except Exception:
        logger.debug("memory history scan state read failed user_id=%s", user_id, exc_info=True)
        return set()


async def _note_chat_read(redis: Redis, user_id: UUID, chat_id: UUID) -> None:
    key = _read_chats_key(user_id)
    try:
        # One transaction: a crash between the two left a set with no TTL.
        async with redis.pipeline(transaction=True) as pipe:
            pipe.sadd(key, str(chat_id))
            pipe.expire(key, _STATE_TTL_SECONDS)
            await pipe.execute()
    except Exception:
        logger.debug("memory history scan state write failed user_id=%s", user_id, exc_info=True)


async def _retry_later(redis: Redis, user_id: UUID) -> bool:
    """Hold the missed chats for a later pass. False once the passes are used up."""
    key = _missed_passes_key(user_id)
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, _STATE_TTL_SECONDS)
            passes = int((await pipe.execute())[0])
        if passes >= _PASS_LIMIT:
            return False
        await redis.set(_queued_key(user_id), _RETRY_STATE, ex=_RETRY_AFTER_SECONDS)
    except Exception:
        # Without Redis a later pass could not skip the chats already read.
        logger.debug("memory history scan retry failed user_id=%s", user_id, exc_info=True)
        return False
    return True


async def _clear_state(redis: Redis, user_id: UUID) -> None:
    try:
        await redis.delete(
            _queued_key(user_id), _read_chats_key(user_id), _missed_passes_key(user_id)
        )
    except Exception:
        logger.debug("memory history scan state clear failed user_id=%s", user_id, exc_info=True)


async def scan_recent_chats(settings: Settings, *, user_id: UUID) -> None:
    async with SessionLocal() as session:
        user = await users_repo.get_by_id(session, user_id)
    if user is None or not memory_switch_on(user):
        return
    if user.memory_history_scanned_at:
        # Asked by a cached copy still saying "not scanned", or retried after the
        # stamp's publish failed: retire those copies (core/user_cache).
        await user_cache.publish_change(user_id)
        await _clear_state(get_redis_client(), user_id)
        return
    redis = get_redis_client()
    already_read = await _chats_read(redis, user_id)
    chat_ids = await _recent_chat_ids(user_id)
    missed = 0
    for chat_id in chat_ids:
        if str(chat_id) in already_read:
            continue
        try:
            read = await _read_chat(settings, user_id, chat_id)
        except Exception:
            # One bad chat must not stop the rest of the pass.
            logger.warning(
                "memory history scan chat failed user_id=%s chat_id=%s",
                user_id,
                chat_id,
                exc_info=True,
            )
            read = False
        if read:
            await _note_chat_read(redis, user_id, chat_id)
        else:
            missed += 1
    if missed and await _retry_later(redis, user_id):
        logger.warning("memory history scan will retry user_id=%s missed=%s", user_id, missed)
        return
    async with SessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(memory_history_scanned_at=datetime.now(UTC))
        )
        await session.commit()
    # Cached copies of the row still say "not scanned" (core/user_cache).
    await user_cache.publish_change(user_id)
    await _clear_state(redis, user_id)
    logger.info(
        "memory history scan done user_id=%s chats=%s missed=%s", user_id, len(chat_ids), missed
    )
