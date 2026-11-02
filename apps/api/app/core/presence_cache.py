"""Remembered answers to "has this user (or chat) any indexed chunks yet?".

Every turn asked Postgres three times, in sessions of their own, before the first
token: chat history once, and documents twice. The index jobs now set the answer when
they write chunks, and a probe's own answer is kept: a yes for a month (a cleared index
forgets it), a no for ten minutes (the next index job overwrites it at once).
Best-effort: a Redis failure asks Postgres, as before.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

PRESENT_TTL_SECONDS = 30 * 86_400
ABSENT_TTL_SECONDS = 600


def history_key(user_id: object) -> str:
    return f"ragidx:user:{user_id}"


def documents_key(chat_id: object) -> str:
    return f"ragidx:chat:{chat_id}"


async def cached_presence(key: str, probe: Callable[[], Awaitable[bool]]) -> bool:
    """The remembered answer for ``key``, or ``probe()``'s, remembered."""
    redis = get_redis_client()
    try:
        known = await redis.get(key)
        if known is not None:
            return bool(known == "1")
    except Exception:
        logger.debug("Chunk presence read failed key=%s", key, exc_info=True)
    present = await probe()
    try:
        await redis.set(
            key, "1" if present else "0", ex=PRESENT_TTL_SECONDS if present else ABSENT_TTL_SECONDS
        )
    except Exception:
        logger.debug("Chunk presence write failed key=%s", key, exc_info=True)
    return present


async def mark_present(key: str) -> None:
    """Chunks were just written under ``key``."""
    try:
        await get_redis_client().set(key, "1", ex=PRESENT_TTL_SECONDS)
    except Exception:
        logger.debug("Chunk presence mark failed key=%s", key, exc_info=True)


async def forget_presence(key: str) -> None:
    """The chunks under ``key`` were deleted: the next probe asks Postgres."""
    try:
        await get_redis_client().delete(key)
    except Exception:
        logger.debug("Chunk presence forget failed key=%s", key, exc_info=True)
