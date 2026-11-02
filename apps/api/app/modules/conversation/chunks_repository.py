"""Message chunk repository for chat-history RAG retrieval."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.orm import MessageChunk

EMBEDDING_DIM = 1536


async def has_chunks_for_user(session: AsyncSession, user_id: UUID) -> bool:
    result = await session.execute(
        select(MessageChunk.id)
        .where(MessageChunk.user_id == user_id, MessageChunk.embedding.isnot(None))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def indexed_message_ids(
    session: AsyncSession,
    user_id: UUID,
    message_ids: list[UUID],
) -> set[UUID]:
    if not message_ids:
        return set()
    # Only embedded rows count: one with no vector is never found by search.
    result = await session.execute(
        select(MessageChunk.message_id).where(
            MessageChunk.user_id == user_id,
            MessageChunk.message_id.in_(message_ids),
            MessageChunk.embedding.isnot(None),
        )
    )
    return {row[0] for row in result.all()}


async def replace_chunks_of_messages(
    session: AsyncSession,
    *,
    user_id: UUID,
    messages: list[tuple[UUID, UUID, str, list[tuple[int, str, list[float] | None]]]],
) -> None:
    """Replace the stored chunks of each message, uncommitted: one delete and one insert
    however many messages (a turn indexes two).

    ``messages``: (message id, chat id, role, its chunks) each; a chunk is (index, text,
    vector), and a vector that is not ``EMBEDDING_DIM`` long is stored as none.
    """
    if not messages:
        return
    await session.execute(
        delete(MessageChunk).where(MessageChunk.message_id.in_([m[0] for m in messages]))
    )
    session.add_all(
        MessageChunk(
            user_id=user_id,
            message_id=message_id,
            chat_id=chat_id,
            role=role,
            chunk_index=index,
            text=text,
            embedding=vec if vec is not None and len(vec) == EMBEDDING_DIM else None,
        )
        for message_id, chat_id, role, chunks in messages
        for index, text, vec in chunks
    )
    await session.flush()


async def prune_beyond_window(session: AsyncSession, user_id: UUID, *, window: int) -> None:
    """Delete the user's chunks older than their newest ``window``: no search reads them.

    Every turn stores up to a dozen chunks (a 1536-dim vector each, about 7 KB with its
    text), ten times the size of the messages themselves, and a search ranks only the
    newest ``window``. Kept with their chat, a user's older chunks grew for ever.
    """
    older = (
        select(MessageChunk.id)
        .where(MessageChunk.user_id == user_id)
        .order_by(MessageChunk.created_at.desc())
        .offset(window)
    )
    await session.execute(delete(MessageChunk).where(MessageChunk.id.in_(older)))


async def search_semantic(
    session: AsyncSession,
    user_id: UUID,
    query_embedding: list[float],
    *,
    window: int,
    exclude_message_ids: set[UUID] | None = None,
    limit: int = 6,
    max_distance: float | None = None,
) -> list[MessageChunk]:
    """The ``limit`` chunks nearest ``query_embedding`` among the user's newest ``window``.

    Chunks are kept as long as their chat, but a search ranks only the newest: an exact
    distance over a bounded set, read through ``(user_id, created_at)``. A global vector
    index filters by user only after its scan, so it found nothing for most users.
    """
    if len(query_embedding) != EMBEDDING_DIM:
        return []
    filters = [MessageChunk.user_id == user_id, MessageChunk.embedding.isnot(None)]
    if exclude_message_ids:
        filters.append(MessageChunk.message_id.notin_(exclude_message_ids))
    # The LIMIT keeps the planner from flattening the window into the outer query.
    newest = (
        select(MessageChunk.id, MessageChunk.embedding)
        .where(*filters)
        .order_by(MessageChunk.created_at.desc())
        .limit(window)
        .subquery("newest")
    )
    distance = newest.c.embedding.cosine_distance(query_embedding)
    stmt = select(MessageChunk).join(newest, newest.c.id == MessageChunk.id)
    if max_distance is not None:
        stmt = stmt.where(distance <= max_distance)
    result = await session.execute(stmt.order_by(distance).limit(limit))
    return list(result.scalars().all())


async def delete_near(
    session: AsyncSession,
    user_id: UUID,
    vector: ColumnElement[Any],
    *,
    max_distance: float,
) -> None:
    """Drop the user's chunks within ``max_distance`` (cosine) of ``vector``.

    ``vector`` is a SQL expression (memory passes its fact's embedding as a subquery),
    read inside the statement and never loaded; a NULL deletes nothing. Every chunk of
    the user is compared, not only the window a search reads: a chat deleted later must
    not bring an older copy back into it. No commit.
    """
    await session.execute(
        delete(MessageChunk).where(
            MessageChunk.user_id == user_id,
            MessageChunk.embedding.isnot(None),
            MessageChunk.embedding.cosine_distance(vector) <= max_distance,
        )
    )


async def delete_mentioning_all(
    session: AsyncSession,
    user_id: UUID,
    names: list[str],
    *,
    role: str,
) -> None:
    """Drop the user's ``role`` chunks whose text names every one of ``names``; no commit."""
    if not names:
        return
    filters = [MessageChunk.user_id == user_id, MessageChunk.role == role]
    filters.extend(MessageChunk.text.icontains(name, autoescape=True) for name in names)
    await session.execute(delete(MessageChunk).where(*filters))


async def delete_all_for_user(session: AsyncSession, user_id: UUID) -> None:
    """Drop every chunk of the user's chat-history index; no commit."""
    await session.execute(delete(MessageChunk).where(MessageChunk.user_id == user_id))
