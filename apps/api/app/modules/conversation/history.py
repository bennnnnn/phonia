"""What chat and the other modules read of a user's chats and messages.

Conversation owns the chats, messages and message chunks (code-health audit ARCH-08;
structure ticket ST-03): their repositories sit in this module and stay private. Chat,
images, live talk, to-dos, memory, attachments and the account read through these
operations and write through ``service``; a turn chat did not stream saves through
``turn_record``, and memory forgets past snippets through ``history_rag``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Chat, Message
from app.modules.conversation import chats_repository as _chats
from app.modules.conversation import messages_repository as _messages


async def get_chat(session: AsyncSession, chat_id: UUID, user_id: UUID) -> Chat | None:
    """The user's chat, or None when it is not theirs or is gone."""
    return await _chats.get_by_id(session, chat_id, user_id)


async def recent_messages(session: AsyncSession, chat_id: UUID, *, limit: int) -> list[Message]:
    """The chat's last ``limit`` messages, oldest first."""
    return await _messages.list_recent(session, chat_id, limit=limit)


async def last_user_message(session: AsyncSession, chat_id: UUID) -> Message | None:
    """The chat's latest message from the user."""
    return await _messages.get_last_user(session, chat_id)


async def message_in_chat(session: AsyncSession, message_id: UUID, chat_id: UUID) -> Message | None:
    """The message, when it belongs to this chat."""
    return await _messages.get_by_id(session, message_id, chat_id)


async def message_for_user(
    session: AsyncSession, message_id: UUID, user_id: UUID
) -> Message | None:
    """The message, when it is in one of the user's chats."""
    return await _messages.get_for_user(session, message_id, user_id)


async def user_lines_since(
    session: AsyncSession,
    chat_id: UUID,
    *,
    after_created_at: datetime | None = None,
    after_id: UUID | None = None,
    newer_than: datetime | None = None,
    limit: int = 20,
) -> list[Message]:
    """The user's messages after an extract cursor, oldest first (memory's backlog)."""
    return await _messages.list_user_contents_since(
        session,
        chat_id,
        after_created_at=after_created_at,
        after_id=after_id,
        newer_than=newer_than,
        limit=limit,
    )


async def messages_before(
    session: AsyncSession, chat_id: UUID, message: Message, *, limit: int
) -> list[Message]:
    """Up to ``limit`` messages just before ``message``, oldest first."""
    return await _messages.list_before(
        session,
        chat_id,
        before_created_at=message.created_at,
        before_id=message.id,
        limit=limit,
    )


async def chats_for_export(session: AsyncSession, user_id: UUID, *, limit: int) -> list[Chat]:
    """The user's chats, archived ones too, each with its summary (the data export)."""
    return await _chats.list_for_user(
        session, user_id, limit=limit, include_archived=True, with_summary=True
    )


async def messages_page(
    session: AsyncSession, chat_id: UUID, *, offset: int, limit: int
) -> list[Message]:
    """An oldest-first slice of the chat's messages (the export pages through them)."""
    return await _messages.list_range(session, chat_id, offset=offset, limit=limit)


def forget_user_chats(user_id: UUID) -> None:
    """Drop the user's chats this process remembers (the account is being deleted)."""
    _chats.forget_user_chats(user_id)


def peek_recent_chat(chat_id: UUID, user_id: UUID) -> Chat | None:
    """The chat as this process last read it, without a query; None when not remembered."""
    return _chats.peek_recent_chat(chat_id, user_id)


async def pinned_chats(session: AsyncSession, user_id: UUID) -> list[Chat]:
    """The user's pinned chats (the drawer's top)."""
    return await _chats.list_pinned(session, user_id)


async def recent_chats_page(
    session: AsyncSession, user_id: UUID, *, limit: int, cursor: str | None = None
) -> tuple[list[Chat], str | None]:
    """A page of the user's unarchived chats, newest activity first, and the next cursor."""
    return await _chats.list_recent_page(session, user_id, limit=limit, cursor=cursor)


async def archived_chats_page(
    session: AsyncSession, user_id: UUID, *, limit: int, cursor: str | None = None
) -> tuple[list[Chat], str | None]:
    """A page of the user's archived chats, and the next cursor."""
    return await _chats.list_archived_page(session, user_id, limit=limit, cursor=cursor)


def chats_by_recency(
    chats: list[Chat], *, user_timezone: str | None = None, now: datetime | None = None
) -> dict[str, list[Chat]]:
    """The chats in the drawer's day groups (today, yesterday, …) in the user's zone."""
    return _chats.group_by_recency(chats, user_timezone=user_timezone, now=now)


async def message_count(session: AsyncSession, chat_id: UUID) -> int:
    """How many messages the chat holds."""
    return await _messages.count_for_chat(session, chat_id)


async def messages_page_before(
    session: AsyncSession, chat_id: UUID, *, limit: int, before_id: UUID | None = None
) -> tuple[list[Message], bool]:
    """A page of messages before ``before_id`` (the newest page without it), oldest
    first, and whether older ones remain."""
    return await _messages.list_page(session, chat_id, limit=limit, before_id=before_id)


async def messages_after(
    session: AsyncSession, chat_id: UUID, *, limit: int, after_id: UUID
) -> tuple[list[Message], bool]:
    """A page of messages after ``after_id``, oldest first, and whether newer ones remain."""
    return await _messages.list_after(session, chat_id, limit=limit, after_id=after_id)


async def messages_around(
    session: AsyncSession, chat_id: UUID, *, limit: int, around_id: UUID
) -> tuple[list[Message], bool, bool]:
    """A page with ``around_id`` in its middle, and whether older and newer ones remain."""
    return await _messages.list_around(session, chat_id, limit=limit, around_id=around_id)


async def reply_ids_since(session: AsyncSession, user_id: UUID, *, since: datetime) -> list[UUID]:
    """The ids of the user's assistant messages written since ``since``."""
    return await _messages.list_assistant_ids_since(session, user_id, since=since)
