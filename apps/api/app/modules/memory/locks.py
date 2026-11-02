"""The per-user memory write lock: one writer at a time over a user's facts."""

import asyncio
import logging
from uuid import UUID

from app.core.redis import get_redis_client
from app.core.redis_lock import acquire_lock, release_lock
from app.exceptions import DomainError, RedisUnavailableError

logger = logging.getLogger(__name__)

# Covers one LLM round-trip + optional fallback retry with headroom.
_MEMORY_WRITE_LOCK_TTL = 150
_DELETE_LOCK_RETRY_ATTEMPTS = 4
_DELETE_LOCK_RETRY_DELAY_SECONDS = 0.15


class MemoryWriteLockBusyError(DomainError):
    """Another write holds the user's memory; 409 ``memory_busy``."""

    status_code = 409
    default_code = "memory_busy"

    def __init__(self, user_id: UUID) -> None:
        super().__init__("Memory is being updated right now — try again in a moment.")
        self.user_id = user_id


def memory_write_lock_key(user_id: UUID) -> str:
    return f"memwrite:{user_id}"


async def take_memory_write_lock(user_id: UUID) -> str | None:
    """The per-user memory write lock's token, or None while another write holds it.

    A Redis error raises ``RedisUnavailableError`` (fail closed): Redis cannot say who
    holds the lock, so nothing writes, and an edit the user waits on answers 503.
    """
    try:
        return await acquire_lock(
            get_redis_client(), memory_write_lock_key(user_id), _MEMORY_WRITE_LOCK_TTL
        )
    except Exception as exc:
        raise RedisUnavailableError() from exc


async def acquire_memory_write_lock(user_id: UUID) -> str | None:
    """The lock for a background writer: None while held or while Redis is down.

    Either way the job retries after a backoff (``skipped_lock``), failing closed.
    """
    try:
        return await take_memory_write_lock(user_id)
    except RedisUnavailableError:
        # Not contention: the caller's "lock held" line follows, and this says why.
        logger.warning(
            "Memory write lock unavailable (Redis error) user_id=%s", user_id, exc_info=True
        )
        return None


async def release_memory_write_lock(user_id: UUID, token: str | None) -> None:
    """Release only when ``token`` still owns the lock."""
    if not token:
        return
    try:
        await release_lock(get_redis_client(), memory_write_lock_key(user_id), token)
    except Exception:
        logger.debug("Memory write lock release failed", exc_info=True)


async def acquire_memory_write_lock_or_raise(user_id: UUID) -> str:
    """The lock for a hand edit, retried briefly; ``MemoryWriteLockBusyError`` if held.

    Redis down raises ``RedisUnavailableError`` at once (503 unavailable). It read as held,
    so an outage said "Memory is being updated" (409 ``memory_busy``) after four tries.
    """
    for attempt in range(_DELETE_LOCK_RETRY_ATTEMPTS):
        token = await take_memory_write_lock(user_id)
        if token:
            return token
        if attempt < _DELETE_LOCK_RETRY_ATTEMPTS - 1:
            await asyncio.sleep(_DELETE_LOCK_RETRY_DELAY_SECONDS)
    raise MemoryWriteLockBusyError(user_id)
