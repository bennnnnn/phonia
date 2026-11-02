"""Conversation search — service façade over the search repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search import repository as search_repo


async def search_conversations(
    session: AsyncSession,
    user_id: UUID,
    *,
    query: str,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    return await search_repo.search_conversations(
        session, user_id, query=query, limit=limit, cursor=cursor
    )
