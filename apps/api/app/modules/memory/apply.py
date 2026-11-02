"""Persist atomic memory facts, then embed without holding a DB connection."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules.memory import cache
from app.modules.memory import repository as memories_repo
from app.modules.memory.text import embedding_text_hash
from app.modules.memory.writes_repository import MemoryFactWrite

MemorySessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def apply_memory_facts(
    settings: Settings,
    *,
    user_id: UUID,
    writes: list[MemoryFactWrite],
    session_factory: MemorySessionFactory = SessionLocal,
    memories: Any = memories_repo,
    expected_facts: dict[UUID, str] | None = None,
    manual_edit: bool = False,
    applied: list[str] | None = None,
) -> None:
    """Persist fact ops, (re)embed stale rows, then invalidate caches.

    ``applied`` collects the op of every write that took effect.

    ``manual_edit`` marks writes the user asked for (a plain-words edit, a
    "forget ..."). When they change or remove saved facts, the edit is stamped
    in the same transaction so the history scan cannot bring the old facts back.
    """
    if not writes:
        return

    from app.gateways import embedding_gateway

    embed_needed: list[tuple[UUID, str]] = []
    async with session_factory() as session:
        try:
            if expected_facts is not None and not await memories.lock_memory_enabled(
                session, user_id
            ):
                return
            touched = await memories.apply_writes(
                session,
                user_id=user_id,
                writes=writes,
                expected_facts=expected_facts,
                active_cap=settings.memory_active_fact_cap,
                commit=False,
                **({"applied": applied} if applied is not None else {}),
            )
            if manual_edit and any(write.op != "add" for write in writes):
                await memories.note_manual_edit(session, user_id)
            touched_set = set(touched)
            backfill_left = max(0, settings.memory_embed_backfill_per_pass)
            for fact_id, text, has_vector, text_hash in await memories.list_embed_state(
                session, user_id
            ):
                if has_vector and text_hash == embedding_text_hash(text):
                    continue
                if fact_id not in touched_set:
                    if backfill_left <= 0:
                        continue
                    backfill_left -= 1
                embed_needed.append((fact_id, text))
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    if not embed_needed:
        await _invalidate_memory_caches(user_id)
        return

    vectors = await embedding_gateway.embed_many(
        settings, [text for _, text in embed_needed], concurrency=settings.embedding_concurrency
    )
    to_write = [
        (memory_id, text, vec, embedding_text_hash(text))
        for (memory_id, text), vec in zip(embed_needed, vectors, strict=True)
        if vec
    ]

    if to_write:
        async with session_factory() as session:
            try:
                for memory_id, text, vec, text_hash in to_write:
                    await memories.update_embedding_if_current(
                        session, user_id, memory_id, text, vec, text_hash, commit=False
                    )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    await _invalidate_memory_caches(user_id)


async def _invalidate_memory_caches(user_id: UUID) -> None:
    await cache.invalidate_memory_block(user_id)
