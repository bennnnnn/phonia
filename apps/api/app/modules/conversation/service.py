"""What chat and the other modules write to a user's chats and messages.

The writes conversation keeps (structure ticket ST-03); its repositories stay private.
A function that takes ``commit`` leaves the commit to a caller that owns the
transaction (CLAUDE.md, "Transaction ownership").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Chat, Message
from app.modules.conversation import chats_repository as _chats
from app.modules.conversation import messages_repository as _messages


async def create_chat(session: AsyncSession, *, user_id: UUID, model: str) -> Chat:
    return await _chats.create(session, user_id=user_id, model=model)


async def touch_chat(session: AsyncSession, chat_id: UUID, *, commit: bool = True) -> None:
    """The chat moves up the drawer: a reply or a picture turn is its last activity."""
    await _chats.touch_by_id(session, chat_id, commit=commit)


async def set_title(session: AsyncSession, chat: Chat, title: str) -> Chat:
    return await _chats.set_title(session, chat, title)


async def set_title_if_empty(
    session: AsyncSession, chat_id: UUID, title: str, *, user_id: UUID, commit: bool = True
) -> bool:
    """The generated title, unless the user named the chat first; whether it was set."""
    return await _chats.set_title_if_empty(session, chat_id, title, user_id=user_id, commit=commit)


async def set_pinned(session: AsyncSession, chat: Chat, pinned: bool) -> Chat:
    return await _chats.set_pinned(session, chat, pinned)


async def set_archived(session: AsyncSession, chat: Chat, archived: bool) -> Chat:
    return await _chats.set_archived(session, chat, archived)


async def archive_all_chats(session: AsyncSession, user_id: UUID, *, commit: bool = True) -> int:
    return await _chats.archive_all_for_user(session, user_id, commit=commit)


async def set_archived_many(
    session: AsyncSession, user_id: UUID, chat_ids: list[UUID], *, archived: bool
) -> list[UUID]:
    """The ids of the user's chats among ``chat_ids`` that changed."""
    return await _chats.set_archived_many(session, user_id, chat_ids, archived=archived)


async def delete_chats(session: AsyncSession, user_id: UUID, chat_ids: list[UUID]) -> list[UUID]:
    """The ids of the user's chats among ``chat_ids`` that were deleted."""
    return await _chats.delete_many(session, user_id, chat_ids)


async def delete_all_chats(session: AsyncSession, user_id: UUID, *, commit: bool = True) -> int:
    return await _chats.delete_all_for_user(session, user_id, commit=commit)


def forget_chat(chat_id: UUID) -> None:
    """Drop the chat this process remembers (it was deleted)."""
    _chats.forget_chat(chat_id)


async def delete_abandoned_drafts(session: AsyncSession, cutoff: datetime, *, limit: int) -> int:
    """Chats never sent to, older than ``cutoff`` (data retention); no commit."""
    return await _chats.delete_abandoned_drafts(session, cutoff, limit=limit)


async def create_message(
    session: AsyncSession,
    *,
    chat_id: UUID,
    user_id: UUID,
    role: str,
    content: str,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    commit: bool = True,
    message_id: UUID | None = None,
    completion: str | None = None,
) -> Message:
    return await _messages.create(
        session,
        chat_id=chat_id,
        user_id=user_id,
        role=role,
        content=content,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        commit=commit,
        message_id=message_id,
        completion=completion,
    )


async def delete_message(session: AsyncSession, message: Message) -> None:
    await _messages.delete_message(session, message)


async def update_content(
    session: AsyncSession, message: Message, content: str, *, commit: bool = True
) -> Message:
    return await _messages.update_content(session, message, content, commit=commit)


async def set_feedback(
    session: AsyncSession, message_id: UUID, chat_id: UUID, feedback: str | None
) -> Message | None:
    """The reply's rating, or None when the message is not in the chat."""
    return await _messages.set_feedback(session, message_id, chat_id, feedback)


async def edit_recent_reply(
    session: AsyncSession,
    chat_id: UUID,
    *,
    containing: str,
    edit: Callable[[str], str],
    scan: int = 30,
) -> bool:
    """Rewrite the chat's recent reply that holds ``containing``; commits. Whether it changed.

    A card the user acted on in another module (a reminder card saved by its tap) is
    stored as acted on; conversation keeps the only writes to its messages (audit ARCH-08).
    """
    for message in await _messages.list_recent(session, chat_id, limit=scan):
        if message.role != "assistant" or containing not in (message.content or ""):
            continue
        updated = edit(message.content)
        if updated == message.content:
            return False
        await _messages.update_content(session, message, updated)
        return True
    return False
