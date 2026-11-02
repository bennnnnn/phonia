import math
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.memory.erase as erase
from app.models.orm import Memory, MemoryArea, User
from app.modules.memory.ops import ACTIVE_STATUS, MUTED_STATUS, normalize_memory_text
from app.modules.memory.writes_repository import MemoryFactWrite as MemoryFactWrite
from app.modules.memory.writes_repository import apply_fact_ops as apply_fact_ops
from app.modules.memory.writes_repository import lock_memory_enabled as lock_memory_enabled
from app.modules.memory.writes_repository import (
    update_embedding_if_current as update_embedding_if_current,
)


async def list_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    include_muted: bool = True,
    include_superseded: bool = False,
) -> list[Memory]:
    statuses = [ACTIVE_STATUS]
    if include_muted:
        statuses.append(MUTED_STATUS)
    filters = [Memory.user_id == user_id]
    if not include_superseded:
        filters.append(Memory.status.in_(statuses))
    result = await session.execute(
        select(Memory).where(*filters).order_by(Memory.type.asc(), Memory.last_confirmed_at.desc())
    )
    return list(result.scalars().all())


async def list_scored_for_user(
    session: AsyncSession, user_id: UUID, query_vec: list[float]
) -> list[tuple[Memory, float | None]]:
    """The user's active and muted facts, each with its cosine similarity to ``query_vec``.

    Postgres computes the similarities, so no vector leaves the database: loading both
    vector copies of 150 facts moved ~7 MB and cost ~60 ms of event-loop CPU a turn. A
    fact with no vector yet scores None.
    """
    similarity = (1 - Memory.embedding.cosine_distance(query_vec)).label("similarity")
    result = await session.execute(
        select(Memory, similarity)
        .where(Memory.user_id == user_id, Memory.status.in_((ACTIVE_STATUS, MUTED_STATUS)))
        .order_by(Memory.type.asc(), Memory.last_confirmed_at.desc())
    )
    return [(memory, _finite(score)) for memory, score in result.all()]


def _finite(score: float | None) -> float | None:
    """A zero vector's cosine is NaN in pgvector; it matches nothing."""
    if score is None:
        return None
    value = float(score)
    return 0.0 if math.isnan(value) else value


async def list_embed_state(
    session: AsyncSession, user_id: UUID
) -> list[tuple[UUID, str, bool, str | None]]:
    """``(id, text, has_vector, embedding_text_hash)`` of each active fact, vectors unread."""
    result = await session.execute(
        select(Memory.id, Memory.text, Memory.embedding.isnot(None), Memory.embedding_text_hash)
        .where(Memory.user_id == user_id, Memory.status == ACTIVE_STATUS)
        .order_by(Memory.type.asc(), Memory.last_confirmed_at.desc())
    )
    return [(row[0], row[1], bool(row[2]), row[3]) for row in result.all()]


async def list_areas(session: AsyncSession, user_id: UUID) -> list[MemoryArea]:
    result = await session.execute(
        select(MemoryArea).where(MemoryArea.user_id == user_id).order_by(MemoryArea.title.asc())
    )
    return list(result.scalars().all())


async def delete_topic(
    session: AsyncSession,
    user_id: UUID,
    topic: str,
    *,
    commit: bool = True,
) -> int:
    """Delete one memory document: every fact with this topic, and its area row."""
    await _purge_where(session, user_id, Memory.topic == topic)
    result = cast(
        CursorResult[Any],
        await session.execute(
            delete(Memory).where(Memory.user_id == user_id, Memory.topic == topic)
        ),
    )
    await session.execute(
        delete(MemoryArea).where(MemoryArea.user_id == user_id, MemoryArea.key == topic)
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return int(result.rowcount or 0)


async def note_manual_edit(session: AsyncSession, user_id: UUID) -> None:
    """Stamp a hand edit to memory; the caller commits.

    The history scan reads only lines written after this stamp, so it cannot
    bring back what the user removed or changed. Only background jobs read the
    stamp, from the row itself, so it is not published to cached user copies
    (``core/user_cache``).
    """
    await session.execute(
        update(User).where(User.id == user_id).values(memory_edited_at=datetime.now(UTC))
    )


async def list_range(
    session: AsyncSession,
    user_id: UUID,
    *,
    offset: int,
    limit: int,
    include_superseded: bool = False,
) -> list[Memory]:
    if limit <= 0:
        return []
    filters = [Memory.user_id == user_id]
    if not include_superseded:
        filters.append(Memory.status.in_((ACTIVE_STATUS, MUTED_STATUS)))
    result = await session.execute(
        select(Memory)
        .where(*filters)
        .order_by(Memory.type.asc(), Memory.last_confirmed_at.desc(), Memory.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def apply_writes(
    session: AsyncSession,
    *,
    user_id: UUID,
    writes: list[MemoryFactWrite],
    expected_facts: dict[UUID, str] | None,
    active_cap: int,
    commit: bool = True,
    applied: list[str] | None = None,
) -> list[UUID]:
    touched = await apply_fact_ops(
        session,
        user_id,
        writes,
        expected_facts,
        active_cap=active_cap,
        applied=applied,
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return touched


async def delete_all_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    commit: bool = True,
) -> int:
    result = cast(
        CursorResult[Any],
        await session.execute(delete(Memory).where(Memory.user_id == user_id)),
    )
    await session.execute(delete(MemoryArea).where(MemoryArea.user_id == user_id))
    # With every fact gone, past-chat recall must not repeat any of them. Here, not at
    # the top: chat's history index loads modules that read memory.
    from app.modules.conversation import history_rag

    await history_rag.forget_all_snippets(session, user_id)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return int(result.rowcount or 0)


async def delete_by_id(
    session: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    *,
    commit: bool = True,
) -> bool:
    """Delete one fact with the older versions it superseded and the snippets repeating it."""
    if await get_by_id(session, user_id, memory_id) is None:
        return False
    await erase.delete_fact_rows(session, user_id, memory_id)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return True


async def get_by_id(session: AsyncSession, user_id: UUID, memory_id: UUID) -> Memory | None:
    result = await session.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_text(
    session: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    text: str,
    *,
    commit: bool = True,
) -> Memory | None:
    memory = await get_by_id(session, user_id, memory_id)
    if memory is None:
        return None
    memory.text = normalize_memory_text(text)
    memory.embedding = None
    memory.embedding_json = None
    memory.embedding_text_hash = None
    memory.last_confirmed_at = func_now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(memory)
    return memory


async def _purge_where(session: AsyncSession, user_id: UUID, condition: Any) -> None:
    rows = await session.execute(select(Memory).where(Memory.user_id == user_id, condition))
    await erase.purge_fact_chunks(session, user_id, rows.scalars().all())


def func_now() -> datetime:
    return datetime.now(UTC)


async def update_text_and_embedding(
    session: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    text: str,
    embedding: list[float],
    *,
    embedding_text_hash: str | None = None,
    commit: bool = True,
) -> Memory | None:
    """Update text and its embedding together so semantic recall doesn't rank
    on a stale vector after a fact delete/edit."""
    memory = await get_by_id(session, user_id, memory_id)
    if memory is None:
        return None
    memory.text = normalize_memory_text(text)
    memory.embedding = embedding
    memory.embedding_json = None
    memory.last_confirmed_at = func_now()
    if embedding_text_hash is not None:
        memory.embedding_text_hash = embedding_text_hash
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(memory)
    return memory


async def update_status(
    session: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    status: str,
    *,
    commit: bool = True,
) -> Memory | None:
    memory = await get_by_id(session, user_id, memory_id)
    if memory is None:
        return None
    if memory.status == "superseded" and status != "superseded":
        return None
    if status == MUTED_STATUS and memory.status != MUTED_STATUS:
        # Muted means not used in replies, past-chat recall included.
        await erase.purge_fact_chunks(session, user_id, [memory])
    memory.status = status
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(memory)
    return memory
