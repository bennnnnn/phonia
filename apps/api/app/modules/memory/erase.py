"""Removing a fact end to end: its older versions, and the chat snippets that repeat it.

Deleting "User lives in Lisbon" also deletes the "User lives in Nairobi" row it
superseded, and drops the past-chat snippets that would put either back into a
prompt through chat-history recall. The snippets are purged from the recall index
when the fact goes (one write, nothing to check on later turns); the messages stay
in their chats. Callers own the transaction.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Memory
from app.modules.conversation import history_rag as chat_history_rag

# A snippet this close to a removed fact says the same thing (retrieval itself
# reads snippets from 0.30 up, against the question rather than the fact).
_PURGE_MIN_SIMILARITY = 0.5
# Names in a fact ("Nairobi", "Uber"): capitalised words after its first word.
_NAME = re.compile(r"(?<![\w'])[A-Z][\w+#.-]*[\w+#]")
_NOT_NAMES = frozenset({"User", "User's", "I"})


async def delete_fact_rows(
    session: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    *,
    purge: bool = True,
) -> set[UUID]:
    """Delete one fact and every older version it superseded. Returns the ids removed."""
    ids = {memory_id}
    frontier = {memory_id}
    while frontier:
        result = await session.execute(
            select(Memory.id).where(
                Memory.user_id == user_id, Memory.superseded_by_id.in_(frontier)
            )
        )
        frontier = {row[0] for row in result.all()} - ids
        ids |= frontier
    if purge:
        rows = await session.execute(
            select(Memory).where(Memory.user_id == user_id, Memory.id.in_(ids))
        )
        await purge_fact_chunks(session, user_id, rows.scalars().all())
    await session.execute(delete(Memory).where(Memory.user_id == user_id, Memory.id.in_(ids)))
    return ids


async def purge_fact_chunks(session: AsyncSession, user_id: UUID, facts: Iterable[Memory]) -> None:
    """Drop past-chat snippets that state these facts, so recall cannot bring them back."""
    for fact in facts:
        vector = select(Memory.embedding).where(Memory.id == fact.id).scalar_subquery()
        await chat_history_rag.forget_snippets_near(
            session, user_id, vector, max_distance=1.0 - _PURGE_MIN_SIMILARITY
        )
        names = fact_names(str(getattr(fact, "text", "") or ""))
        if names:
            # The user's own words that name all of it; an assistant line repeating
            # it is caught by the vector above.
            await chat_history_rag.forget_snippets_naming(session, user_id, names, role="user")


def fact_names(text: str) -> list[str]:
    """Capitalised names in a fact, skipping its first word and "User"."""
    words = text.strip().split(maxsplit=1)
    rest = words[1] if len(words) > 1 else ""
    names: list[str] = []
    for match in _NAME.finditer(rest):
        name = match.group(0)
        if name not in _NOT_NAMES and name not in names:
            names.append(name)
    return names
