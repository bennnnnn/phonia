"""Reading and editing the user's facts: their own edits, and the reads other modules make.

Each holds the user's write lock and commits as one unit, then drops the cached blocks.
Locks and the cache are called through their modules, so a test that patches
``locks.acquire_memory_write_lock`` or ``cache.invalidate_memory_block`` reaches here.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.exceptions import DomainError
from app.gateways import embedding_gateway
from app.models.orm import Memory, MemoryArea
from app.modules.memory import cache, locks
from app.modules.memory import repository as memories_repo
from app.modules.memory.ops import normalize_memory_text
from app.modules.memory.text import embedding_text_hash, strip_memory_as_of

logger = logging.getLogger(__name__)


class MemoryEmptyTextError(DomainError):
    """Edited memory text normalized to empty."""

    default_code = "memory_empty"

    def __init__(self, message: str = "Memory text cannot be empty") -> None:
        super().__init__(message)


@asynccontextmanager
async def _write_locked(user_id: UUID) -> AsyncIterator[None]:
    """Hold the user's memory write lock for the block (busy: ``MemoryWriteLockBusyError``)."""
    lock_token = await locks.acquire_memory_write_lock_or_raise(user_id)
    try:
        yield
    finally:
        await locks.release_memory_write_lock(user_id, lock_token)


async def _commit_hand_delete[T: int](
    session: AsyncSession,
    user_id: UUID,
    delete: Callable[[], Awaitable[T]],
) -> T:
    """One hand delete as one transaction: delete, stamp the edit, commit; then drop caches.

    Stamping ``memory_edited_at`` in the same commit keeps the history scan from
    restoring what the user removed. A failure rolls the whole unit back.
    """
    try:
        removed = await delete()
        if removed:
            await memories_repo.note_manual_edit(session, user_id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    if removed:
        await cache.invalidate_memory_block(user_id)
    return removed


async def update_memory(
    session: AsyncSession,
    settings: Settings,
    user_id: UUID,
    memory_id: UUID,
    text: str | None,
    *,
    status: str | None = None,
) -> Memory | None:
    clean: str | None = None
    if text is not None:
        clean = normalize_memory_text(strip_memory_as_of(text))
        if not clean:
            raise MemoryEmptyTextError()
    if clean is None and status is None:
        raise MemoryEmptyTextError()
    async with _write_locked(user_id):
        memory = await memories_repo.get_by_id(session, user_id, memory_id)
        if memory is None:
            return None
        new_vec: list[float] | None = None
        if clean is not None:
            # End the read before the embedding call (a provider round trip); the write
            # lock keeps the row as read until the writes below.
            await session.commit()
            try:
                new_vec = await embedding_gateway.embed_text(settings, clean)
            except Exception:
                logger.warning("Memory re-embed on edit failed", exc_info=True)
        updated: Memory | None = memory
        try:
            if status is not None:
                updated = await memories_repo.update_status(
                    session, user_id, memory_id, status, commit=False
                )
                if updated is None:
                    return None
            if clean is not None:
                if new_vec is not None:
                    updated = await memories_repo.update_text_and_embedding(
                        session,
                        user_id,
                        memory_id,
                        clean,
                        new_vec,
                        embedding_text_hash=embedding_text_hash(clean),
                        commit=False,
                    )
                else:
                    updated = await memories_repo.update_text(
                        session,
                        user_id,
                        memory_id,
                        clean,
                        commit=False,
                    )
            if updated is not None:
                await memories_repo.note_manual_edit(session, user_id)
                await session.commit()
                await session.refresh(updated)
        except Exception:
            await session.rollback()
            raise
        if updated is not None:
            await cache.invalidate_memory_block(user_id)
        return updated


async def delete_memory(session: AsyncSession, user_id: UUID, memory_id: UUID) -> bool:
    async with _write_locked(user_id):
        return await _commit_hand_delete(
            session,
            user_id,
            lambda: memories_repo.delete_by_id(session, user_id, memory_id, commit=False),
        )


async def delete_memory_document(session: AsyncSession, user_id: UUID, topic: str) -> bool:
    """Delete every fact in one document (and an area's title row)."""
    async with _write_locked(user_id):
        removed = await _commit_hand_delete(
            session,
            user_id,
            lambda: memories_repo.delete_topic(session, user_id, topic, commit=False),
        )
    return removed > 0


async def delete_all_memories(session: AsyncSession, user_id: UUID) -> int:
    async with _write_locked(user_id):
        return await _commit_hand_delete(
            session,
            user_id,
            lambda: memories_repo.delete_all_for_user(session, user_id, commit=False),
        )


async def active_fact_texts(session: AsyncSession, user_id: UUID) -> list[str]:
    """Each fact in use, as text: not muted, not superseded (a saved-detail reply)."""
    rows = await memories_repo.list_for_user(
        session, user_id, include_muted=False, include_superseded=False
    )
    return [row.text for row in rows]


async def facts_for_export(
    session: AsyncSession, user_id: UUID, *, offset: int, limit: int
) -> list[Memory]:
    """One page of every fact the user has, superseded ones included (the data export)."""
    return await memories_repo.list_range(
        session, user_id, offset=offset, limit=limit, include_superseded=True
    )


async def areas_for_export(session: AsyncSession, user_id: UUID) -> list[MemoryArea]:
    """The user's areas, by title (the data export)."""
    return await memories_repo.list_areas(session, user_id)


async def delete_user_rows(session: AsyncSession, user_id: UUID) -> None:
    """Every fact, area and past-chat index row of a deleted account; no commit.

    ``account.lifecycle`` calls it under the user's row lock, the order memory's writers
    take, before the user row goes.
    """
    await memories_repo.delete_all_for_user(session, user_id, commit=False)
