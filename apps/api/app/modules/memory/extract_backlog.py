"""Unprocessed user lines for a memory extraction pass.

Each job must see every user message since the previous successful pass, not
only the current turn. Redis stores a per-chat cursor; the payload transcript
is the fallback when Redis or Neon is unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis_client
from app.modules.conversation import history as chat_history
from app.modules.memory.text import memory_extract_user_text
from app.services.text_normalize import cap_text_head_tail

logger = logging.getLogger(__name__)

_MEMORY_TRANSCRIPT_MAX_CHARS = 4000
_MEMORY_EXTRACT_BACKLOG = 20
# The user line and reply before a "forget that", each cut to this many characters.
_EARLIER_EXCHANGE_MESSAGES = 2
_EARLIER_LINE_MAX_CHARS = 600
_CURSOR_TTL_SECONDS = 60 * 60 * 24 * 60
# A failed model pass keeps the cursor so the next turn retries the same lines.
# After this many failures in a row the lines are skipped, so one line the model
# always fails on cannot hold back every later line in the chat.
FAILED_PASS_LIMIT = 3
_FAILED_PASS_TTL_SECONDS = 60 * 60 * 24


def _cursor_key(user_id: UUID, chat_id: UUID) -> str:
    return f"memory:extract_cursor:{user_id}:{chat_id}"


def _failed_pass_key(user_id: UUID, chat_id: UUID) -> str:
    return f"memory:extract_failures:{user_id}:{chat_id}"


def parse_extract_cursor(raw: str | None) -> tuple[datetime | None, UUID | None]:
    if not raw:
        return None, None
    stamp, sep, id_part = raw.partition("|")
    if not sep or not id_part:
        return None, None
    try:
        return datetime.fromisoformat(stamp), UUID(id_part)
    except ValueError:
        return None, None


def format_extract_cursor(created_at: datetime, message_id: UUID) -> str:
    return f"{created_at.isoformat()}|{message_id}"


def format_user_memory_transcript(user_texts: list[str]) -> str:
    lines: list[str] = []
    for raw in user_texts:
        cleaned = memory_extract_user_text(raw)
        if cleaned:
            lines.append(f"User: {cleaned}")
    return "\n".join(lines)


async def history_chat_transcript(
    session: AsyncSession,
    chat_id: UUID,
    *,
    newer_than: datetime | None,
) -> str:
    """A past chat's most recent user lines, capped like a live pass.

    Lines written at or before ``newer_than`` (the user's last hand edit to
    memory) are left out, so reading them cannot undo that edit.
    """
    rows = await chat_history.user_lines_since(
        session, chat_id, newer_than=newer_than, limit=_MEMORY_EXTRACT_BACKLOG
    )
    return cap_text_head_tail(
        format_user_memory_transcript([row.content for row in rows]),
        _MEMORY_TRANSCRIPT_MAX_CHARS,
    )


async def expand_memory_extract_transcript(
    session: AsyncSession,
    *,
    user_id: UUID,
    chat_id: UUID,
    fallback_transcript: str,
) -> tuple[str, str | None]:
    """Return ``(transcript, cursor_to_stamp_or_none)``.

    Cursor is stamped by the caller only after the LLM pass succeeds.
    """
    after_created_at, after_id = await _read_cursor(user_id, chat_id)
    try:
        rows = await chat_history.user_lines_since(
            session,
            chat_id,
            after_created_at=after_created_at,
            after_id=after_id,
            limit=_MEMORY_EXTRACT_BACKLOG,
        )
    except Exception:
        logger.debug("memory extract backlog list failed chat_id=%s", chat_id, exc_info=True)
        return cap_text_head_tail(fallback_transcript, _MEMORY_TRANSCRIPT_MAX_CHARS), None

    texts = [row.content for row in rows]
    built = format_user_memory_transcript(texts)
    if not built:
        built = fallback_transcript
    newest_cursor: str | None = None
    if rows:
        last = rows[-1]
        newest_cursor = format_extract_cursor(last.created_at, last.id)
    return cap_text_head_tail(built, _MEMORY_TRANSCRIPT_MAX_CHARS), newest_cursor


async def exchange_before_unread(session: AsyncSession, *, user_id: UUID, chat_id: UUID) -> str:
    """The exchange just before the pass's unread lines: what "forget that" points at.

    Those lines were read by an earlier pass. They are context, never a source of
    facts: "Remember I'm vegetarian", "Got it", then "Actually, forget that".
    """
    after_created_at, after_id = await _read_cursor(user_id, chat_id)
    try:
        unread = await chat_history.user_lines_since(
            session,
            chat_id,
            after_created_at=after_created_at,
            after_id=after_id,
            limit=_MEMORY_EXTRACT_BACKLOG,
        )
        if not unread:
            return ""
        earlier = await chat_history.messages_before(
            session, chat_id, unread[0], limit=_EARLIER_EXCHANGE_MESSAGES
        )
    except Exception:
        logger.debug("memory extract earlier exchange failed chat_id=%s", chat_id, exc_info=True)
        return ""
    lines: list[str] = []
    for message in earlier:
        text = memory_extract_user_text(message.content)[:_EARLIER_LINE_MAX_CHARS].strip()
        if text and message.role in ("user", "assistant"):
            lines.append(f"{message.role.capitalize()}: {text}")
    return "\n".join(lines)


async def _read_cursor(user_id: UUID, chat_id: UUID) -> tuple[datetime | None, UUID | None]:
    try:
        raw = await get_redis_client().get(_cursor_key(user_id, chat_id))
        if isinstance(raw, bytes):
            raw = raw.decode()
        return parse_extract_cursor(raw if isinstance(raw, str) else None)
    except Exception:
        logger.debug("memory extract cursor read failed chat_id=%s", chat_id, exc_info=True)
        return None, None


async def stamp_extract_cursor(user_id: UUID, chat_id: UUID, cursor: str) -> None:
    try:
        await get_redis_client().set(
            _cursor_key(user_id, chat_id),
            cursor,
            ex=_CURSOR_TTL_SECONDS,
        )
    except Exception:
        logger.debug("memory extract cursor write failed chat_id=%s", chat_id, exc_info=True)


async def note_failed_extract_pass(user_id: UUID, chat_id: UUID) -> bool:
    """Count a model failure for this chat. True when its lines should be skipped."""
    key = _failed_pass_key(user_id, chat_id)
    try:
        redis = get_redis_client()
        # One transaction: a crash between the two left a count that never expired.
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, _FAILED_PASS_TTL_SECONDS)
            failures = int((await pipe.execute())[0])
        if failures < FAILED_PASS_LIMIT:
            return False
        await redis.delete(key)
    except Exception:
        # Without Redis the cursor cannot be kept either, so nothing is held back.
        logger.debug("memory extract failure count failed chat_id=%s", chat_id, exc_info=True)
    return True


async def clear_failed_extract_passes(user_id: UUID, chat_id: UUID) -> None:
    try:
        await get_redis_client().delete(_failed_pass_key(user_id, chat_id))
    except Exception:
        logger.debug("memory extract failure reset failed chat_id=%s", chat_id, exc_info=True)
