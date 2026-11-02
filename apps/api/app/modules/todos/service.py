"""Public todo operations for other product modules.

This module does not import chat, so live talk can call it without a circular
import.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import TodoItem
from app.modules.todos import repository as todos_repo


async def list_owned_todos(
    session: AsyncSession, user_id: UUID, *, limit: int, offset: int = 0
) -> list[TodoItem]:
    """Read a page of a user's to-dos without advancing recurrence."""
    return await todos_repo.list_for_user(session, user_id, limit=limit, offset=offset)


async def delete_user_rows(session: AsyncSession, user_id: UUID) -> None:
    """Every to-do of a deleted account; no commit (``account.lifecycle``)."""
    await todos_repo.delete_all_for_user(session, user_id)
