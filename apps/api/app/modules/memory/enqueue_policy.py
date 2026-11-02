"""Policy for scheduling memory consolidation work."""

import logging
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.models.orm import Chat, Memory, User
from app.modules.memory import consolidation
from app.modules.memory import repository as memories_repo
from app.modules.memory.switch import memory_switch_on

logger = logging.getLogger(__name__)

_CONSOLIDATE_LOCK_TTL = 300


class MemorySection(Protocol):
    type: str
    text: str


def _lock_key(user_id: UUID) -> str:
    return f"memconsolidate:{user_id}"


async def request_consolidation(
    redis: Redis,
    user: User,
    memories: Iterable[MemorySection],
    *,
    skip_if_already_queued: bool,
) -> str:
    memory_list = list(memories)
    if not memory_switch_on(user) or not memory_list:
        return "skipped"

    lock_key = _lock_key(user.id)
    if skip_if_already_queued and await redis.exists(lock_key):
        return "in_progress"

    if not consolidation.facts_need_consolidation(memory_list):
        return "skipped"

    acquired = await redis.set(
        lock_key,
        "1",
        ex=_CONSOLIDATE_LOCK_TTL,
        nx=True,
    )
    if not acquired:
        return "in_progress"
    await jobs.enqueue(
        redis,
        "memory_consolidate",
        {"user_id": str(user.id)},
        dedupe_key=jobs.unique_dedupe_key(f"memory_consolidate:{user.id}"),
    )
    return "queued"


async def list_user_memories(
    session: AsyncSession,
    redis: Redis,
    user: User,
) -> list[Memory]:
    memories = await memories_repo.list_for_user(session, user.id)
    await maybe_request_consolidation(redis, user, memories)
    return memories


async def source_chat_titles(
    session: AsyncSession,
    memories: Iterable[Memory],
) -> dict[UUID, str]:
    chat_ids = {memory.source_chat_id for memory in memories if memory.source_chat_id}
    if not chat_ids:
        return {}
    result = await session.execute(select(Chat.id, Chat.title).where(Chat.id.in_(chat_ids)))
    return {row.id: (row.title or "") for row in result.all() if row.title}


async def maybe_request_consolidation(
    redis: Redis,
    user: User,
    memories: Iterable[MemorySection],
) -> None:
    try:
        await request_consolidation(
            redis,
            user,
            memories,
            skip_if_already_queued=True,
        )
    except Exception:
        logger.debug("Failed to enqueue memory consolidation", exc_info=True)
