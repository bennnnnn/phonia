"""Saving a turn chat did not stream: a picture, a photo lookup, a voice turn.

Conversation owns the message rows (code-health audit ARCH-08; structure ticket ST-03).
A typed turn saves in chat's ``turn_settle``. Images and live talk saved their own rows
and skipped what a typed turn does after: the chat stayed where it was in the drawer, a
chat that began with a picture got no title, and memory and chat-history search never
read the turn. They save through here now, and chat's ``finish_turn`` sets off a typed
turn's jobs.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Message
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo


async def add_turn_message(
    session: AsyncSession,
    *,
    chat_id: UUID,
    user_id: UUID,
    role: Literal["user", "assistant"],
    content: str,
    model: str | None = None,
) -> Message:
    """One message of the turn, and the chat moved up the drawer; no commit.

    The caller commits it with its own rows: a picture's attachment, a voice turn's
    reminders.
    """
    message = await messages_repo.create(
        session,
        chat_id=chat_id,
        user_id=user_id,
        role=role,
        content=content,
        model=model,
        commit=False,
    )
    await chats_repo.touch_by_id(session, chat_id, commit=False)
    return message
