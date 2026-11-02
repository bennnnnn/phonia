"""Assemble a user's data export: everything Phonia stores about them.

Profile and settings, chats and messages, every memory row and memory area,
to-dos, attachments, daily usage, push devices (no token) and
product events (the newest, when capped). Every query is scoped to the caller's
user id. Lists page by key, not offset. The file is streamed from the request; an
export built by a background job into storage is a later change.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.gateways.storage_gateway import StorageGateway, get_storage_gateway
from app.models.orm import (
    Chat,
    Memory,
    Message,
    ProductEvent,
    TodoItem,
    User,
)
from app.modules import memory as memory_service
from app.modules.attachments import service as attachments_service
from app.modules.conversation import history as chat_history
from app.modules.todos import service as todos_service
from app.repositories import product_events as product_events_repo
from app.repositories import push_tokens as push_tokens_repo
from app.repositories import usage as usage_repo

logger = logging.getLogger(__name__)

# Bound memory/time for a single export request — messages are paged per chat.
EXPORT_MAX_CHATS = 500
EXPORT_MAX_MESSAGES_PER_CHAT = 2_000
EXPORT_MESSAGE_PAGE_SIZE = 200
EXPORT_MEMORY_PAGE_SIZE = 200
# Every row: up to 150 active facts plus muted ones and superseded history.
# The old cap of 50 cut most users' memory out of their own export.
EXPORT_MAX_MEMORIES = 5_000
EXPORT_MAX_TODOS = 2_000
EXPORT_TODO_PAGE_SIZE = 200
EXPORT_MAX_ATTACHMENTS = 2_000
EXPORT_MAX_PRODUCT_EVENTS = 2_000
EXPORT_MAX_USAGE_DAYS = 3_660

# Profile and settings the user entered or chose. Sign-in subject ids and
# billing bookkeeping are identifiers for other systems, not user content.
_PROFILE_FIELDS = (
    "email",
    "name",
    "avatar_url",
    "plan",
    "emoji_use",
    "custom_instructions",
    "locale",
    "timezone",
    "age",
    "country",
    "job",
    "memory_enabled",
    "follow_up_suggestions_enabled",
    "memory_include_sensitive",
    "web_search_enabled",
    "ai_data_consent_at",
    "push_notifications_enabled",
    "push_reminders_enabled",
    "email_reminders_enabled",
    "reminder_lead_minutes",
    "quiet_hours_enabled",
    "quiet_hours_start_minute",
    "quiet_hours_end_minute",
    "tts_voice",
    "created_at",
    "updated_at",
)


def _json_safe(value: Any) -> Any:
    """JSON value for one column. An odd type becomes None, never a broken stream."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    return None


def _user_payload(user: User) -> dict[str, Any]:
    return {name: _json_safe(getattr(user, name, None)) for name in _PROFILE_FIELDS}


def _chat_header(chat: Chat) -> dict[str, Any]:
    return {
        "id": str(chat.id),
        "title": chat.title,
        "pinned": chat.pinned,
        # Rolling summary of older messages kept for the model's context.
        "summary": _json_safe(chat.summary),
        "created_at": chat.created_at.isoformat(),
        "updated_at": chat.updated_at.isoformat(),
    }


def _message_payload(message: Message) -> dict[str, Any]:
    # The id joins a message to the attachments whose message_id names it.
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "model": message.model,
        "feedback": _json_safe(message.feedback),
        "created_at": message.created_at.isoformat(),
    }


def _memory_payload(memory: Memory) -> dict[str, Any]:
    return {
        "type": memory.type,
        "topic": _json_safe(memory.topic),
        "status": _json_safe(memory.status),
        "sensitivity": _json_safe(memory.sensitivity),
        "text": memory.text,
        "confidence": float(memory.confidence) if memory.confidence is not None else None,
        "created_at": memory.created_at.isoformat(),
        "updated_at": _json_safe(memory.updated_at),
    }


def _memory_area_payload(area: Any) -> dict[str, Any]:
    return {"key": area.key, "title": area.title, "summary": area.summary}


def _usage_payload(row: Any) -> dict[str, Any]:
    return {
        "day": _json_safe(row.date),
        "input_tokens": _json_safe(row.input_tokens),
        "output_tokens": _json_safe(row.output_tokens),
    }


def _push_device_payload(row: Any) -> dict[str, Any]:
    # The Expo token is a delivery credential for the device; leave it out.
    return {"platform": _json_safe(row.platform), "updated_at": _json_safe(row.updated_at)}


def _todo_payload(todo: TodoItem) -> dict[str, Any]:
    return {
        "id": str(todo.id),
        "content": todo.content,
        "topic": todo.topic,
        "checked": todo.checked,
        "due_at": todo.due_at.isoformat() if todo.due_at is not None else None,
        "recurrence_rule": _json_safe(todo.recurrence_rule),
        "chat_id": str(todo.chat_id) if todo.chat_id is not None else None,
        "sort_order": todo.sort_order,
        "created_at": todo.created_at.isoformat(),
        "updated_at": todo.updated_at.isoformat(),
    }


def _product_event_payload(event: ProductEvent) -> dict[str, Any]:
    return {
        "name": event.name,
        "properties": event.properties,
        "platform": event.platform,
        "app_version": event.app_version,
        "installation_id": event.installation_id,
        "client_at": event.client_at.isoformat() if event.client_at is not None else None,
        "recorded_at": event.recorded_at.isoformat(),
    }


def _export_limits(settings: Settings) -> dict[str, int]:
    return {
        "max_chats": EXPORT_MAX_CHATS,
        "max_messages_per_chat": EXPORT_MAX_MESSAGES_PER_CHAT,
        "max_memories": EXPORT_MAX_MEMORIES,
        "max_todos": EXPORT_MAX_TODOS,
        "max_attachments": EXPORT_MAX_ATTACHMENTS,
        "max_product_events": EXPORT_MAX_PRODUCT_EVENTS,
        "attachment_download_url_ttl_seconds": settings.r2_presign_expiry_seconds,
    }


def _export_notes(settings: Settings) -> list[str]:
    """What a reader of the file needs to know about it, in plain words."""
    minutes = max(1, settings.r2_presign_expiry_seconds // 60)
    return [
        f"Each attachment's download_url works for {minutes} minutes after the export; "
        "export again to get new links.",
        'Lists are capped (export_limits); "truncated" at the end names any list that '
        "had more than its cap, so that list is not complete.",
    ]


def _note_cut(truncated: list[str], name: str, cut: bool) -> None:
    if cut and name not in truncated:
        truncated.append(name)


async def _attachment_payload(
    attachment: Any,
    *,
    settings: Settings,
    gateway: StorageGateway,
) -> dict[str, Any]:
    download_url: str | None = None
    try:
        download_url = await gateway.presign_download(attachment.storage_key)
    except Exception:
        logger.warning(
            "Export presign failed for attachment_id=%s",
            attachment.id,
            exc_info=True,
        )
    return {
        "id": str(attachment.id),
        "message_id": str(attachment.message_id) if attachment.message_id is not None else None,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "source": attachment.source,
        "original_filename": _json_safe(attachment.original_filename),
        "created_at": attachment.created_at.isoformat(),
        "download_url": download_url,
        "download_url_expires_in_seconds": settings.r2_presign_expiry_seconds,
    }


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


# One page of a list: (session, the last row's key or None, limit) -> rows.
PageReader = Callable[[AsyncSession, Any, int], Awaitable[Sequence[Any]]]


def _messages_of(chat_id: UUID) -> PageReader:
    """One chat's messages, a page at a time after the last one's (created_at, id)."""

    async def read(session: AsyncSession, after: Any, limit: int) -> Sequence[Any]:
        return await chat_history.messages_for_export(session, chat_id, after=after, limit=limit)

    return read


def _message_key(message: Message) -> tuple[datetime, UUID]:
    return message.created_at, message.id


def _row_id(row: Any) -> Any:
    return row.id


async def _paged_json(
    read: PageReader,
    payload: Callable[[Any], dict[str, Any]],
    *,
    key: Callable[[Any], Any],
    cap: int,
    page_size: int,
    session_factory: SessionFactory,
    on_cut: Callable[[bool], None],
) -> AsyncIterator[str]:
    """A list read page by page up to ``cap``, as comma-joined JSON objects.

    Each page reads after the ``key`` of the last row read (keyset): an offset skipped
    or repeated a row whenever one before it was deleted or moved mid-export. A session
    per page, closed before yielding. At the cap one more row is read, and ``on_cut``
    says whether the cap cut the list short.
    """
    read_count = 0
    after: Any = None
    first = True
    while read_count < cap:
        size = min(page_size, cap - read_count)
        async with session_factory() as session:
            rows = await read(session, after, size)
            chunks = [json.dumps(payload(row)) for row in rows]
            if rows:
                after = key(rows[-1])
        for chunk in chunks:
            if not first:
                yield ","
            first = False
            yield chunk
        read_count += len(chunks)
        if len(chunks) < size:
            return
    async with session_factory() as session:
        on_cut(bool(await read(session, after, 1)))


async def _product_event_chunks(
    user_id: UUID, session_factory: SessionFactory, truncated: list[str]
) -> list[str]:
    """The newest product events up to the cap, oldest first, as JSON objects."""
    async with session_factory() as session:
        events = await product_events_repo.list_for_user(
            session, user_id, limit=EXPORT_MAX_PRODUCT_EVENTS + 1
        )
        _note_cut(truncated, "product_events", len(events) > EXPORT_MAX_PRODUCT_EVENTS)
        # The newest cap + 1, oldest first: the one past the cap is the oldest, so it goes.
        kept = events[-EXPORT_MAX_PRODUCT_EVENTS:]
        return [json.dumps(_product_event_payload(event)) for event in kept]


async def _iter_export_json(
    user: User,
    settings: Settings,
    *,
    session_factory: SessionFactory,
) -> AsyncIterator[str]:
    # Open a session per repository call and close it before yielding so a
    # slow client download cannot pin a Neon connection for the stream lifetime.
    snapshot_time = datetime.now(UTC)
    exported_at = snapshot_time.isoformat()
    # The lists the caps in export_limits cut short, named at the end of the file.
    truncated: list[str] = []
    yield "{"
    yield f'"exported_at":{json.dumps(exported_at)},'
    yield f'"notes":{json.dumps(_export_notes(settings))},'
    yield f'"export_limits":{json.dumps(_export_limits(settings))},'
    yield f'"user":{json.dumps(_user_payload(user))},'
    yield '"chats":['

    async with session_factory() as session:
        chats = await chat_history.chats_for_export(session, user.id, limit=EXPORT_MAX_CHATS + 1)
        chat_rows = [(_chat_header(chat), chat.id) for chat in chats[:EXPORT_MAX_CHATS]]
    _note_cut(truncated, "chats", len(chats) > EXPORT_MAX_CHATS)

    for chat_index, (header, chat_id) in enumerate(chat_rows):
        if chat_index:
            yield ","
        yield json.dumps(header)[:-1]
        yield ',"messages":['

        async for chunk in _paged_json(
            _messages_of(chat_id),
            _message_payload,
            key=_message_key,
            cap=EXPORT_MAX_MESSAGES_PER_CHAT,
            page_size=EXPORT_MESSAGE_PAGE_SIZE,
            session_factory=session_factory,
            on_cut=lambda cut: _note_cut(truncated, "messages", cut),
        ):
            yield chunk
        yield "]}"

    yield '],"memories":['
    async for chunk in _paged_json(
        lambda session, after, limit: memory_service.facts_for_export(
            session, user.id, after_id=after, limit=limit
        ),
        _memory_payload,
        key=_row_id,
        cap=EXPORT_MAX_MEMORIES,
        page_size=EXPORT_MEMORY_PAGE_SIZE,
        session_factory=session_factory,
        on_cut=lambda cut: _note_cut(truncated, "memories", cut),
    ):
        yield chunk

    yield '],"memory_areas":['
    async with session_factory() as session:
        area_chunks = [
            json.dumps(_memory_area_payload(area))
            for area in await memory_service.areas_for_export(session, user.id)
        ]
    yield ",".join(area_chunks)

    yield '],"todos":['
    async for chunk in _paged_json(
        lambda session, after, limit: todos_service.todos_for_export(
            session, user.id, after_id=after, limit=limit
        ),
        _todo_payload,
        key=_row_id,
        cap=EXPORT_MAX_TODOS,
        page_size=EXPORT_TODO_PAGE_SIZE,
        session_factory=session_factory,
        on_cut=lambda cut: _note_cut(truncated, "todos", cut),
    ):
        yield chunk

    yield '],"attachments":['
    async with session_factory() as session:
        attachments = await attachments_service.list_for_user(
            session,
            user.id,
            limit=EXPORT_MAX_ATTACHMENTS + 1,
        )
        _note_cut(truncated, "attachments", len(attachments) > EXPORT_MAX_ATTACHMENTS)
        attachments = attachments[:EXPORT_MAX_ATTACHMENTS]
        # Copy scalars before close — ORM instances expire with the session.
        attachment_rows = [
            SimpleNamespace(
                id=attachment.id,
                message_id=attachment.message_id,
                storage_key=attachment.storage_key,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                source=attachment.source,
                original_filename=attachment.original_filename,
                created_at=attachment.created_at,
            )
            for attachment in attachments
        ]
    gateway = get_storage_gateway(settings)
    for attachment_index, attachment in enumerate(attachment_rows):
        if attachment_index:
            yield ","
        yield json.dumps(await _attachment_payload(attachment, settings=settings, gateway=gateway))

    yield '],"usage":['
    async with session_factory() as session:
        usage_chunks = [
            json.dumps(_usage_payload(row))
            for row in await usage_repo.list_for_user(session, user.id, limit=EXPORT_MAX_USAGE_DAYS)
        ]
    yield ",".join(usage_chunks)

    yield '],"push_devices":['
    async with session_factory() as session:
        device_chunks = [
            json.dumps(_push_device_payload(row))
            for row in await push_tokens_repo.list_for_user(session, user.id)
        ]
    yield ",".join(device_chunks)

    yield '],"product_events":['
    yield ",".join(await _product_event_chunks(user.id, session_factory, truncated))

    # Known only once everything is read, so it closes the file.
    yield f'],"truncated":{json.dumps(truncated)}}}'


async def iter_export_json(
    user: User,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Stream a valid JSON export without holding all messages in memory."""
    resolved = settings if settings is not None else get_settings()
    async for chunk in _iter_export_json(user, resolved, session_factory=SessionLocal):
        yield chunk
