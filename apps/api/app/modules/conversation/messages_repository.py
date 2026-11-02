from datetime import datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Message
from app.repositories.keyset import InvalidCursorError


class _AnchorKey(NamedTuple):
    """A page anchor's sort key: what a page needs of it, not its body."""

    created_at: datetime
    id: UUID


async def create(
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
    message = Message(
        chat_id=chat_id,
        user_id=user_id,
        role=role,
        content=content,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        completion=completion,
    )
    if message_id is not None:
        message.id = message_id
    session.add(message)
    if commit:
        await session.commit()
        await session.refresh(message)
    else:
        await session.flush()
    return message


async def list_recent(
    session: AsyncSession,
    chat_id: UUID,
    *,
    limit: int,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def list_user_contents_since(
    session: AsyncSession,
    chat_id: UUID,
    *,
    after_created_at: datetime | None = None,
    after_id: UUID | None = None,
    newer_than: datetime | None = None,
    limit: int = 20,
) -> list[Message]:
    """User messages in a chat after an extract cursor, oldest first.

    With no cursor, returns the most recent ``limit`` user lines (still oldest
    first) so a first pass or Redis miss still covers skipped turns.
    ``newer_than`` leaves out every line written at or before that time.
    """
    page_size = max(limit, 1)
    scope = [Message.chat_id == chat_id, Message.role == "user"]
    if newer_than is not None:
        scope.append(Message.created_at > newer_than)
    if after_created_at is not None and after_id is not None:
        result = await session.execute(
            select(Message)
            .where(
                *scope,
                or_(
                    Message.created_at > after_created_at,
                    and_(
                        Message.created_at == after_created_at,
                        Message.id > after_id,
                    ),
                ),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(page_size)
        )
        return list(result.scalars().all())
    result = await session.execute(
        select(Message)
        .where(*scope)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(page_size)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def list_page(
    session: AsyncSession,
    chat_id: UUID,
    *,
    limit: int,
    before_id: UUID | None = None,
) -> tuple[list[Message], bool]:
    """Return a chronological slice of messages (newest page or older-than cursor).

    A ``before_id`` that is not in the chat (a regenerate replaced that reply) raises
    ``InvalidCursorError``: an empty last page would tell the phone it reached the start.
    """
    anchor = await _anchor(session, chat_id, before_id) if before_id is not None else None
    return await _page_before(session, chat_id, limit=limit, anchor=anchor)


async def _page_before(
    session: AsyncSession, chat_id: UUID, *, limit: int, anchor: _AnchorKey | None
) -> tuple[list[Message], bool]:
    capped = max(1, min(limit, 200))
    statement = select(Message).where(Message.chat_id == chat_id)
    if anchor is not None:
        # Tuple cursor (created_at, id): same-timestamp rows stay stable across pages.
        statement = statement.where(
            or_(
                Message.created_at < anchor.created_at,
                and_(
                    Message.created_at == anchor.created_at,
                    Message.id < anchor.id,
                ),
            )
        )
    result = await session.execute(
        statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(capped + 1)
    )
    rows = list(result.scalars().all())
    has_more = len(rows) > capped
    if has_more:
        rows = rows[:capped]
    rows.reverse()
    return rows, has_more


async def _anchor(session: AsyncSession, chat_id: UUID, message_id: UUID) -> _AnchorKey:
    """The anchor's sort key; ``InvalidCursorError`` when the chat no longer holds it."""
    result = await session.execute(
        select(Message.created_at, Message.id).where(
            Message.id == message_id, Message.chat_id == chat_id
        )
    )
    row = result.one_or_none()
    if row is None:
        raise InvalidCursorError()
    return _AnchorKey(created_at=row.created_at, id=row.id)


def _after(anchor: _AnchorKey, *, inclusive: bool = False) -> ColumnElement[bool]:
    """Rows after ``anchor`` in (created_at, id) order."""
    same_time = Message.id >= anchor.id if inclusive else Message.id > anchor.id
    return or_(
        Message.created_at > anchor.created_at,
        and_(Message.created_at == anchor.created_at, same_time),
    )


async def list_after(
    session: AsyncSession, chat_id: UUID, *, limit: int, after_id: UUID
) -> tuple[list[Message], bool]:
    """The ``limit`` messages after ``after_id``, oldest first, and whether more follow."""
    capped = max(1, min(limit, 200))
    anchor = await _anchor(session, chat_id, after_id)
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id, _after(anchor))
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(capped + 1)
    )
    rows = list(result.scalars().all())
    return rows[:capped], len(rows) > capped


async def list_around(
    session: AsyncSession, chat_id: UUID, *, limit: int, around_id: UUID
) -> tuple[list[Message], bool, bool]:
    """A window of ``limit`` messages with ``around_id`` in its middle, oldest first,
    whether older ones precede it and whether newer ones follow (code-health audit
    NET-18: a search hit deep in a chat was reached 40 messages at a time)."""
    capped = max(1, min(limit, 200))
    anchor = await _anchor(session, chat_id, around_id)
    older: list[Message] = []
    has_older = False
    if before := (capped - 1) // 2:
        older, has_older = await _page_before(session, chat_id, limit=before, anchor=anchor)
    # The anchor and what follows it fill the rest of the window.
    room = capped - len(older)
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id, _after(anchor, inclusive=True))
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(room + 1)
    )
    newer = list(result.scalars().all())
    return older + newer[:room], has_older, len(newer) > room


async def list_after_key(
    session: AsyncSession,
    chat_id: UUID,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[Message]:
    """Up to ``limit`` messages after the ``(created_at, id)`` key, oldest first.

    The export pages by the last row read: an offset skipped a message whenever an
    earlier one went away mid-export (a regenerate replaces a reply).
    """
    if limit <= 0:
        return []
    statement = select(Message).where(Message.chat_id == chat_id)
    if after is not None:
        statement = statement.where(_after(_AnchorKey(created_at=after[0], id=after[1])))
    result = await session.execute(
        statement.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit)
    )
    return list(result.scalars().all())


async def list_range(
    session: AsyncSession,
    chat_id: UUID,
    *,
    offset: int,
    limit: int,
) -> list[Message]:
    """Oldest-first slice of a chat's messages — used by history compression.

    Ordered by ``(created_at, id)``: two messages created in the same millisecond come
    back in either order by time alone, and offset paging would then skip or repeat a
    row at a page boundary. The id is the tiebreaker every message query here uses.
    """
    if limit <= 0:
        return []
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_before(
    session: AsyncSession,
    chat_id: UUID,
    *,
    before_created_at: datetime,
    before_id: UUID,
    limit: int,
) -> list[Message]:
    """Up to ``limit`` messages strictly before a cursor, oldest first."""
    if limit <= 0:
        return []
    result = await session.execute(
        select(Message)
        .where(
            Message.chat_id == chat_id,
            or_(
                Message.created_at < before_created_at,
                and_(
                    Message.created_at == before_created_at,
                    Message.id < before_id,
                ),
            ),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def get_last_user(session: AsyncSession, chat_id: UUID) -> Message | None:
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_recent_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
) -> list[Message]:
    """Newest messages across the user's chats (chat-history RAG backfill)."""
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user_id, Message.role.in_(("user", "assistant")))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_assistant_ids_since(
    session: AsyncSession,
    user_id: UUID,
    *,
    since: datetime,
) -> list[UUID]:
    """Ids of the user's replies created at or after ``since`` (account delete)."""
    result = await session.execute(
        select(Message.id).where(
            Message.user_id == user_id,
            Message.role == "assistant",
            Message.created_at >= since,
        )
    )
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, message_id: UUID, chat_id: UUID) -> Message | None:
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )
    return result.scalar_one_or_none()


async def get_for_user(session: AsyncSession, message_id: UUID, user_id: UUID) -> Message | None:
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_message(session: AsyncSession, message: Message) -> None:
    await session.delete(message)
    await session.commit()


async def chat_has_messages(session: AsyncSession, chat_id: UUID) -> bool:
    """Whether the chat holds any message: stops at the first row, where a count reads all."""
    result = await session.execute(select(exists().where(Message.chat_id == chat_id)))
    return bool(result.scalar_one())


async def count_for_chat(session: AsyncSession, chat_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
    )
    return result.scalar_one()


async def update_content(
    session: AsyncSession,
    message: Message,
    content: str,
    *,
    commit: bool = True,
) -> Message:
    message.content = content
    if commit:
        await session.commit()
        await session.refresh(message)
    else:
        await session.flush()
    return message


async def set_feedback(
    session: AsyncSession,
    message_id: UUID,
    chat_id: UUID,
    feedback: str | None,
) -> Message | None:
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )
    message = result.scalar_one_or_none()
    if message is None:
        return None
    if message.role != "assistant":
        # Only a reply is rated; the service turns this into a 422.
        return message
    message.feedback = feedback
    await session.commit()
    await session.refresh(message)
    return message
