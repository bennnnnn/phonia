from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Text,
    exists,
    func,
    literal,
    null,
    or_,
    select,
    union_all,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Chat, Message
from app.repositories.keyset import after, decode_cursor, encode_cursor, page_of

# A title hit has no message; this id sorts it after any message hit in the same chat.
_NO_MESSAGE = UUID(int=0)


def _trgm_match(column: Any, query: str) -> ColumnElement[bool]:
    """pg_trgm `%` operator — uses GIN trigram indexes on title/content."""
    return cast(ColumnElement[bool], column.op("%")(query))


async def search_conversations(
    session: AsyncSession, user_id: UUID, query: str, limit: int = 20, cursor: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """Search chat titles and message bodies as one recency-ordered timeline.

    Title and message hits are unioned, then the cursor and limit apply once. Returns
    the page and the cursor for the next (None: the last): one row past the page is
    read instead of counting every hit, which no plan could stop early. Message bodies
    match by substring through the user-scoped trigram index
    (``ix_messages_user_content_trgm``); trigram similarity (``%``) almost never matches
    a long body and kept other users' rows in the candidates. Title-only rows omit
    chats that already have a matching message.
    """
    q = query.strip()
    if not q:
        return [], None

    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    msg_where = (
        Message.user_id == user_id,
        Message.content.ilike(pattern, escape="\\"),
    )
    title_match = or_(_trgm_match(Chat.title, q), Chat.title.ilike(pattern, escape="\\"))
    message_hit = exists(select(1).where(Message.chat_id == Chat.id, *msg_where))

    title_stmt = select(
        literal("title").label("match_type"),
        sql_cast(null(), Message.id.type).label("message_id"),
        Chat.id.label("chat_id"),
        Chat.title.label("chat_title"),
        sql_cast(Chat.title, Text).label("content"),
        literal("chat").label("role"),
        func.coalesce(Chat.updated_at, Chat.created_at).label("created_at"),
        Chat.archived.label("archived"),
    ).where(
        Chat.user_id == user_id,
        Chat.title.isnot(None),
        Chat.title != "",
        title_match,
        ~message_hit,
    )
    msg_stmt = (
        select(
            literal("message").label("match_type"),
            Message.id.label("message_id"),
            Chat.id.label("chat_id"),
            Chat.title.label("chat_title"),
            Message.content.label("content"),
            Message.role.label("role"),
            Message.created_at.label("created_at"),
            Chat.archived.label("archived"),
        )
        .join(Chat, Message.chat_id == Chat.id)
        .where(Chat.user_id == user_id, *msg_where)
    )
    combined = union_all(msg_stmt, title_stmt).subquery("search_hits")
    message_key = func.coalesce(
        combined.c.message_id, literal(_NO_MESSAGE, type_=combined.c.message_id.type)
    )
    order = (combined.c.created_at, combined.c.chat_id, message_key)
    stmt = select(combined).order_by(*(column.desc() for column in order))
    if cursor is not None:
        at, ids = decode_cursor(cursor, ids=2)
        stmt = stmt.where(after(order, at, ids))
    rows = (await session.execute(stmt.limit(limit + 1))).all()
    page, next_cursor = page_of(
        rows,
        limit,
        lambda row: encode_cursor(row.created_at, row.chat_id, row.message_id or _NO_MESSAGE),
    )

    results: list[dict[str, Any]] = []
    for row in page:
        raw = row.content or ""
        content = _snippet(raw, q, 120) if row.match_type == "message" else raw
        created = row.created_at or datetime.now(UTC)
        results.append(
            {
                "match_type": row.match_type,
                "message_id": row.message_id,
                "chat_id": row.chat_id,
                "chat_title": row.chat_title,
                "content": content,
                "role": row.role,
                "created_at": created,
                "archived": bool(row.archived),
            }
        )
    return results, next_cursor


def _snippet(content: str, query: str, max_len: int = 120) -> str:
    """Extract a short snippet around the first match of query."""
    idx = content.lower().find(query.lower())
    if idx == -1:
        return content[:max_len]
    start = max(0, idx - 40)
    end = min(len(content), idx + len(query) + 80)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet += "…"
    return snippet
