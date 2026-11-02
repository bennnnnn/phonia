from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.timezone import resolve_timezone
from app.core.ttl_cache import TtlCache
from app.models.orm import Chat, Message
from app.repositories.keyset import after, decode_cursor, encode_cursor, page_of

# Same process just created this chat. The send that follows should not pay
# another Neon round trip to prove the caller owns it.
_CHAT_CACHE_TTL_SECONDS = 120.0
# Chats created on one process within the TTL; far above normal traffic.
_CHAT_CACHE_MAX_ENTRIES = 10_000
_chat_cache: TtlCache[UUID, Chat] = TtlCache(
    ttl_seconds=_CHAT_CACHE_TTL_SECONDS,
    max_entries=_CHAT_CACHE_MAX_ENTRIES,
)


def _remember_chat(chat: Chat) -> None:
    _chat_cache.put(chat.id, chat)


def _cached_chat(chat_id: UUID, user_id: UUID) -> Chat | None:
    chat = _chat_cache.get(chat_id)
    if chat is None:
        return None
    if chat.user_id != user_id:
        _chat_cache.pop(chat_id)
        return None
    return chat


async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    model: str,
) -> Chat:
    chat = Chat(user_id=user_id, model=model)
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    _remember_chat(
        Chat(
            id=chat.id,
            user_id=chat.user_id,
            model=chat.model,
        )
    )
    return chat


def peek_recent_chat(chat_id: UUID, user_id: UUID) -> Chat | None:
    """Detached chat remembered at create time. Reads only."""
    return _cached_chat(chat_id, user_id)


def forget_chat(chat_id: UUID) -> None:
    _chat_cache.pop(chat_id)


def forget_user_chats(user_id: UUID) -> None:
    _chat_cache.drop_where(lambda chat: chat.user_id == user_id)


async def get_by_id(session: AsyncSession, chat_id: UUID, user_id: UUID) -> Chat | None:
    result = await session.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
    return result.scalar_one_or_none()


# What a chat list shows; ``summary`` (up to 6,000 characters) is read only for a prompt.
_LIST_COLUMNS = load_only(
    Chat.id,
    Chat.user_id,
    Chat.title,
    Chat.model,
    Chat.pinned,
    Chat.archived,
    Chat.created_at,
    Chat.updated_at,
    raiseload=True,
)


async def list_for_user(
    session: AsyncSession,
    user_id: UUID,
    limit: int | None = 200,
    *,
    include_archived: bool = False,
    with_summary: bool = False,
) -> list[Chat]:
    """The user's chats with messages: list columns only, unless ``with_summary`` (export)."""
    has_messages = exists().where(Message.chat_id == Chat.id)
    stmt = (
        select(Chat)
        .where(Chat.user_id == user_id)
        .where(has_messages)
        .order_by(Chat.pinned.desc(), Chat.updated_at.desc(), Chat.id.desc())
    )
    if not with_summary:
        stmt = stmt.options(_LIST_COLUMNS)
    if not include_archived:
        stmt = stmt.where(Chat.archived.is_(False))
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_pinned(session: AsyncSession, user_id: UUID) -> list[Chat]:
    """The user's pinned, unarchived chats with messages, newest first; list columns only."""
    has_messages = exists().where(Message.chat_id == Chat.id)
    result = await session.execute(
        select(Chat)
        .options(_LIST_COLUMNS)
        .where(Chat.user_id == user_id, Chat.pinned.is_(True), Chat.archived.is_(False))
        .where(has_messages)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
    )
    return list(result.scalars().all())


async def list_recent_page(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Chat], str | None]:
    """One page of the drawer's dated chats (unpinned, unarchived), newest first.

    Returns the chats and the cursor for the next page (None: the last).
    """
    has_messages = exists().where(Message.chat_id == Chat.id)
    stmt = (
        select(Chat)
        .options(_LIST_COLUMNS)
        .where(Chat.user_id == user_id, Chat.pinned.is_(False), Chat.archived.is_(False))
        .where(has_messages)
    )
    if cursor is not None:
        at, ids = decode_cursor(cursor, ids=1)
        stmt = stmt.where(after((Chat.updated_at, Chat.id), at, ids))
    stmt = stmt.order_by(Chat.updated_at.desc(), Chat.id.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    return page_of(rows, limit, lambda chat: encode_cursor(chat.updated_at, chat.id))


async def list_archived_page(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Chat], str | None]:
    """One page of archived chats, newest first, and the cursor for the next (None: the last)."""
    has_messages = exists().where(Message.chat_id == Chat.id)
    stmt = (
        select(Chat)
        .options(_LIST_COLUMNS)
        .where(Chat.user_id == user_id, Chat.archived.is_(True))
        .where(has_messages)
    )
    if cursor is not None:
        at, ids = decode_cursor(cursor, ids=1)
        stmt = stmt.where(after((Chat.updated_at, Chat.id), at, ids))
    stmt = stmt.order_by(Chat.updated_at.desc(), Chat.id.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    return page_of(rows, limit, lambda chat: encode_cursor(chat.updated_at, chat.id))


async def touch_by_id(session: AsyncSession, chat_id: UUID, *, commit: bool = True) -> None:
    """Update updated_at with a direct UPDATE — avoids a separate SELECT round-trip.

    `commit=False` lets the caller batch this with other writes into a single
    commit (e.g. turn finalize does message create + touch + usage add → one
    commit instead of three Neon round-trips).
    """
    from datetime import UTC, datetime

    from sqlalchemy import update as update_stmt

    await session.execute(
        update_stmt(Chat).where(Chat.id == chat_id).values(updated_at=datetime.now(UTC))
    )
    if commit:
        await session.commit()


RECENCY_BUCKETS = ("today", "yesterday", "last_7_days", "this_month", "older")


def group_by_recency(
    chats: list[Chat],
    *,
    user_timezone: str | None = None,
    now: datetime | None = None,
) -> dict[str, list[Chat]]:
    """Bucket non-pinned chats by last activity in the user's timezone.

    - today: since local midnight today
    - yesterday: previous calendar day
    - last_7_days: 2-7 days ago (excludes today/yesterday)
    - this_month: earlier in the current calendar month
    - older: before this month
    """
    tz = resolve_timezone(user_timezone)
    if now is None:
        now_local = datetime.now(tz)
    else:
        aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        now_local = aware.astimezone(tz)

    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    last_7_days_start = today_start - timedelta(days=7)
    month_start = today_start.replace(day=1)

    grouped: dict[str, list[Chat]] = {key: [] for key in RECENCY_BUCKETS}
    for chat in chats:
        updated = chat.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        updated_local = updated.astimezone(tz)
        if updated_local >= today_start:
            grouped["today"].append(chat)
        elif updated_local >= yesterday_start:
            grouped["yesterday"].append(chat)
        elif updated_local >= last_7_days_start:
            grouped["last_7_days"].append(chat)
        elif updated_local >= month_start:
            grouped["this_month"].append(chat)
        else:
            grouped["older"].append(chat)
    return grouped


async def set_title(session: AsyncSession, chat: Chat, title: str) -> Chat:
    chat.title = title
    await session.commit()
    await session.refresh(chat)
    return chat


async def set_title_if_empty(
    session: AsyncSession,
    chat_id: UUID,
    title: str,
    *,
    user_id: UUID,
    commit: bool = True,
) -> bool:
    """Apply a generated title atomically so a concurrent rename always wins."""
    stmt = (
        update(Chat)
        .where(
            Chat.id == chat_id,
            Chat.user_id == user_id,
            or_(Chat.title.is_(None), Chat.title == ""),
        )
        .values(title=title)
        .execution_options(synchronize_session=False)
    )
    result = cast(CursorResult[Any], await session.execute(stmt))
    if commit:
        await session.commit()
    return result.rowcount > 0


async def set_pinned(session: AsyncSession, chat: Chat, pinned: bool) -> Chat:
    stmt = update(Chat).where(Chat.id == chat.id, Chat.user_id == chat.user_id)
    if pinned:
        stmt = stmt.where(Chat.archived.is_(False))
    await session.execute(stmt.values(pinned=pinned).execution_options(synchronize_session=False))
    await session.commit()
    await session.refresh(chat)
    return chat


async def set_archived(session: AsyncSession, chat: Chat, archived: bool) -> Chat:
    stmt = (
        update(Chat)
        .where(Chat.id == chat.id, Chat.user_id == chat.user_id)
        .values(archived=archived)
    )
    if archived:
        # Explicitly clear the database value even if this ORM object saw an
        # unpinned chat before another request pinned it.
        stmt = stmt.values(pinned=False)
    await session.execute(stmt.execution_options(synchronize_session=False))
    await session.commit()
    await session.refresh(chat)
    return chat


async def archive_all_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    commit: bool = True,
) -> int:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Chat)
            .where(Chat.user_id == user_id, Chat.archived.is_(False))
            .values(archived=True, pinned=False)
            .execution_options(synchronize_session=False)
        ),
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return int(result.rowcount or 0)


async def set_archived_many(
    session: AsyncSession, user_id: UUID, chat_ids: list[UUID], *, archived: bool
) -> list[UUID]:
    """Archive (and unpin) or unarchive the user's chats among ``chat_ids``; the ids changed.

    The caller owns the commit (one transaction for the whole selection).
    """
    values: dict[str, bool] = {"archived": archived}
    if archived:
        values["pinned"] = False
    result = await session.execute(
        update(Chat)
        .where(Chat.user_id == user_id, Chat.id.in_(chat_ids))
        .values(**values)
        .returning(Chat.id)
        .execution_options(synchronize_session=False)
    )
    return list(result.scalars().all())


async def delete_many(session: AsyncSession, user_id: UUID, chat_ids: list[UUID]) -> list[UUID]:
    """Delete the user's chats among ``chat_ids`` (messages cascade); the ids deleted.

    The caller owns the commit, then forgets each id (``forget_chat``).
    """
    result = await session.execute(
        delete(Chat).where(Chat.user_id == user_id, Chat.id.in_(chat_ids)).returning(Chat.id)
    )
    return list(result.scalars().all())


async def delete_all_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    commit: bool = True,
) -> int:
    result = cast(
        CursorResult[Any],
        await session.execute(delete(Chat).where(Chat.user_id == user_id)),
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    forget_user_chats(user_id)
    return int(result.rowcount or 0)


async def delete_abandoned_drafts(session: AsyncSession, cutoff: datetime, *, limit: int) -> int:
    """Delete up to ``limit`` chats made before ``cutoff`` that never got a message.

    The phone makes a chat on the first keystroke and drops it unsent with a best-effort
    delete; a killed app or a failed delete left a row the user can neither see nor
    delete. A file belongs to a message, so a chat with none holds no stored bytes.
    """
    abandoned = (
        select(Chat.id)
        .where(Chat.created_at < cutoff)
        .where(~exists().where(Message.chat_id == Chat.id))
        .limit(limit)
    )
    result = cast(
        CursorResult[Any], await session.execute(delete(Chat).where(Chat.id.in_(abandoned)))
    )
    return result.rowcount or 0
