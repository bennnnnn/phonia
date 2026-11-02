"""HTTP-facing chat list / usage / message orchestration (not the stream loop)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.core.db import SessionLocal
from app.exceptions import DomainError
from app.models.orm import Chat, Message, User
from app.models.schemas import ChatListOut, ChatOut, MessageOut, MessagePageOut, UsageOut
from app.models.schemas.page import Page
from app.modules.chat import finalize_registry
from app.modules.chat.email_fence import rewrite_first_email_fence
from app.modules.chat.related_prompts import (
    RELATED_PROMPTS_TTL_SECONDS,
    forget_related_prompts,
    load_related_prompts,
)
from app.modules.chat.titles import sanitize_manual_chat_title, title_job_key
from app.modules.conversation import history as conversation_history
from app.modules.conversation import service as conversation_service
from app.repositories import usage as usage_repo
from app.services import quota as quota_service
from app.services import time_context as time_context_service
from app.services.quota import utc_today

logger = logging.getLogger(__name__)

DEFAULT_CHAT_LIST_LIMIT = 200
ARCHIVED_CHAT_LIST_LIMIT = 50


class ChatsError(DomainError):
    """A chat history refusal."""


async def create_chat(
    session: AsyncSession,
    user: User,
    *,
    model: str,
) -> Chat:
    return await conversation_service.create_chat(
        session,
        user_id=user.id,
        model=model,
    )


async def list_chats_grouped(
    session: AsyncSession,
    user: User,
    *,
    limit: int = DEFAULT_CHAT_LIST_LIMIT,
    cursor: str | None = None,
    client_timezone: str | None = None,
) -> ChatListOut:
    """The drawer's chats by recency; ``cursor`` reads the dated chats after a page.

    The first page also holds every pinned chat and the newest archived ones. The days
    are the phone's (``client_timezone``, as a chat turn sends it), the profile's when it
    sends none or no valid one: the phone files a chat it inserts itself in its own zone,
    and the profile's copy of that zone lags behind a flight until the next sync.
    """

    async def _pinned_and_archived() -> tuple[list[Chat], tuple[list[Chat], str | None]]:
        if cursor is not None:
            return [], ([], None)
        async with SessionLocal() as side_session:
            pinned = await conversation_history.pinned_chats(side_session, user.id)
            archived = await conversation_history.archived_chats_page(
                side_session, user.id, limit=ARCHIVED_CHAT_LIST_LIMIT
            )
        return pinned, archived

    (dated, next_cursor), (pinned, (archived, archived_cursor)) = await gather_or_cancel(
        conversation_history.recent_chats_page(session, user.id, limit=limit, cursor=cursor),
        _pinned_and_archived(),
    )
    zone = time_context_service.effective_timezone(user.timezone, client_timezone)
    grouped = conversation_history.chats_by_recency(dated, user_timezone=zone)
    return ChatListOut(
        pinned=[ChatOut.model_validate(c) for c in pinned],
        today=[ChatOut.model_validate(c) for c in grouped["today"]],
        yesterday=[ChatOut.model_validate(c) for c in grouped["yesterday"]],
        last_7_days=[ChatOut.model_validate(c) for c in grouped["last_7_days"]],
        this_month=[ChatOut.model_validate(c) for c in grouped["this_month"]],
        older=[ChatOut.model_validate(c) for c in grouped["older"]],
        archived=[ChatOut.model_validate(c) for c in archived],
        next_cursor=next_cursor,
        archived_next_cursor=archived_cursor,
    )


async def list_archived_chats(
    session: AsyncSession, user: User, *, limit: int, cursor: str | None
) -> Page[ChatOut]:
    """Archived chats after the drawer's first page, by cursor: none is out of reach."""
    chats, next_cursor = await conversation_history.archived_chats_page(
        session, user.id, limit=limit, cursor=cursor
    )
    return Page(items=[ChatOut.model_validate(c) for c in chats], next_cursor=next_cursor)


async def get_chat(session: AsyncSession, user: User, chat_id: UUID) -> Chat:
    chat = await conversation_history.get_chat(session, chat_id, user.id)
    if chat is None:
        raise ChatsError("Chat not found", status_code=404)
    return chat


async def rename_chat(session: AsyncSession, user: User, chat_id: UUID, title: str) -> Chat:
    chat = await get_chat(session, user, chat_id)
    cleaned = sanitize_manual_chat_title(title)
    if not cleaned:
        raise ChatsError("Invalid title", status_code=400)
    return await conversation_service.set_title(session, chat, cleaned)


async def pin_chat(session: AsyncSession, user: User, chat_id: UUID, *, pinned: bool) -> Chat:
    chat = await get_chat(session, user, chat_id)
    if pinned and chat.archived:
        raise ChatsError("Unarchive the chat before pinning", status_code=409)
    chat = await conversation_service.set_pinned(session, chat, pinned)
    if pinned and chat.archived:
        raise ChatsError("Unarchive the chat before pinning", status_code=409)
    return chat


async def archive_chat(session: AsyncSession, user: User, chat_id: UUID, *, archived: bool) -> Chat:
    chat = await get_chat(session, user, chat_id)
    return await conversation_service.set_archived(session, chat, archived)


async def archive_all_chats(session: AsyncSession, user: User) -> int:
    try:
        count = await conversation_service.archive_all_chats(session, user.id, commit=False)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return count


async def bulk_chats(
    session: AsyncSession,
    user: User,
    *,
    action: Literal["archive", "unarchive", "delete"],
    chat_ids: list[UUID],
) -> list[UUID]:
    """One transaction for the drawer's selection: the phone sent one request per chat,
    and a few hundred at once passed the REST rate limit. Ids not the user's are skipped."""
    unique = list(dict.fromkeys(chat_ids))
    try:
        if action == "delete":
            changed = await conversation_service.delete_chats(session, user.id, unique)
        else:
            changed = await conversation_service.set_archived_many(
                session, user.id, unique, archived=action == "archive"
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    if action == "delete":
        for chat_id in changed:
            conversation_service.forget_chat(chat_id)
    return changed


async def delete_all_chats(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
) -> int:
    """Remove every conversation. Library attachments stay (message_id SET NULL)."""
    _ = settings
    try:
        count = await conversation_service.delete_all_chats(session, user.id, commit=False)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return count


async def delete_chat(
    session: AsyncSession,
    user: User,
    chat_id: UUID,
    *,
    settings: Settings,
    if_empty: bool = False,
) -> None:
    """Remove the conversation. Library attachments stay (message_id SET NULL).

    ``if_empty`` keeps a chat that holds any message: the phone drops an unused draft
    with this one request, where it read a page of messages and deleted twice
    (code-health audit NET-13).
    """
    chat = await conversation_history.get_chat(session, chat_id, user.id)
    if chat is None:
        raise ChatsError("Chat not found", status_code=404)
    if if_empty and await conversation_history.message_count(session, chat_id):
        return
    # Do not detach rows or delete bytes — explicit Library delete owns that.
    # attachments.message_id SET NULLs when messages cascade.
    _ = settings
    await session.delete(chat)
    await session.commit()
    conversation_service.forget_chat(chat_id)


async def today_usage(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
) -> UsageOut:
    day = utc_today()
    db_usage = await usage_repo.get_for_date(session, user.id, day)
    input_tokens = db_usage.input_tokens if db_usage else 0
    output_tokens = db_usage.output_tokens if db_usage else 0
    limit = quota_service.daily_limit_for_user(user, settings)
    redis_used = await quota_service.get_daily_usage(redis, str(user.id))
    used_tokens = max(redis_used, input_tokens + output_tokens)
    remaining = max(0, limit - used_tokens)
    return UsageOut(
        date=day.isoformat(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        daily_limit=limit,
        used_tokens=used_tokens,
        remaining=remaining,
        context_token_budget=settings.context_token_budget,
        recent_message_window=settings.recent_message_window,
    )


async def reset_today_usage(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    user: User,
) -> UsageOut:
    if not settings.dev_auth_enabled:
        raise ChatsError("Not found", status_code=404)
    await quota_service.reset_daily_usage(redis, str(user.id))
    # L9: also clear the DB row so today_usage (called next) returns 0 —
    # otherwise the UI still shows the DB-recorded total after reset.
    await usage_repo.reset_for_date(session, user.id, utc_today())
    return await today_usage(session, redis, settings, user)


async def list_messages_page(
    session: AsyncSession,
    redis: Redis,
    user: User,
    chat_id: UUID,
    *,
    limit: int = 40,
    before: UUID | None = None,
    after: UUID | None = None,
    around: UUID | None = None,
) -> MessagePageOut:
    """The newest page, the page ``before`` or ``after`` a message, or the window ``around`` one."""
    chat = await get_chat(session, user, chat_id)
    # End the ownership read before waiting: up to 20 s for a stream and its save, with
    # this connection idle in transaction while the save needed one from the same pool.
    await session.commit()
    await finalize_registry.wait_for_inflight_stream(chat_id)
    await finalize_registry.wait_for_pending_finalize(chat_id, redis)
    has_more_after = False
    if around is not None:
        msgs, has_more, has_more_after = await conversation_history.messages_around(
            session, chat_id, limit=limit, around_id=around
        )
    elif after is not None:
        msgs, has_more_after = await conversation_history.messages_after(
            session, chat_id, limit=limit, after_id=after
        )
        has_more = True
    else:
        msgs, has_more = await conversation_history.messages_page_before(
            session, chat_id, limit=limit, before_id=before
        )
    newest = before is None and after is None and around is None

    if not chat.title and newest and msgs:
        user_msg = next((m for m in msgs if m.role == "user"), None)
        asst_msg = next((m for m in msgs if m.role == "assistant"), None)
        if user_msg and asst_msg:
            dedupe_key = f"topic_backfill:{chat_id}"
            try:
                claimed = await redis.set(dedupe_key, "1", nx=True, ex=300)
                # The first reply's own title job, queued or running, is the same job:
                # a page read before it lands used to pay for a second title call.
                if claimed:
                    await jobs.enqueue(
                        redis,
                        "topic",
                        {
                            "chat_id": str(chat_id),
                            "user_id": str(user.id),
                            "user_message": user_msg.content,
                            "assistant_message": asst_msg.content,
                        },
                        dedupe_key=title_job_key(chat_id),
                    )
            except Exception:
                logger.warning("Title backfill enqueue failed chat_id=%s", chat_id, exc_info=True)

    outs = [MessageOut.model_validate(m) for m in msgs]
    if newest or (around is not None and not has_more_after):
        await _attach_cached_related_prompts(redis, outs)
    return MessagePageOut(messages=outs, has_more=has_more, has_more_after=has_more_after)


async def follow_up_reply_ids(session: AsyncSession, user_id: UUID) -> list[str]:
    """The user's replies whose follow-up questions may still be cached.

    They are written from the conversation and keyed by message id, so an account
    delete would otherwise leave them in Redis for up to a week. Read before the
    user's messages are deleted; ``forget_follow_up_questions`` drops them.
    """
    since = datetime.now(UTC) - timedelta(seconds=RELATED_PROMPTS_TTL_SECONDS)
    message_ids = await conversation_history.reply_ids_since(session, user_id, since=since)
    return [str(message_id) for message_id in message_ids]


async def forget_follow_up_questions(redis: Redis, reply_ids: list[str]) -> int:
    """Drop the cached follow-up questions under these replies (``follow_up_reply_ids``)."""
    return await forget_related_prompts(redis, reply_ids)


async def _attach_cached_related_prompts(redis: Redis, messages: list[MessageOut]) -> None:
    """Newest page only. A cache miss leaves the field empty and does not call a model."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role != "assistant":
            continue
        prompts = await load_related_prompts(redis, str(message.id))
        if prompts:
            messages[index] = message.model_copy(update={"related_prompts": prompts})
        return


async def set_message_feedback(
    session: AsyncSession,
    redis: Redis,
    user: User,
    chat_id: UUID,
    message_id: UUID,
    feedback: str | None,
) -> Message:
    await get_chat(session, user, chat_id)
    message = await conversation_service.set_feedback(session, message_id, chat_id, feedback)
    if message is None:
        await session.rollback()  # nothing was written; no transaction across the wait
        await finalize_registry.wait_for_pending_finalize(chat_id, redis)
        message = await conversation_service.set_feedback(session, message_id, chat_id, feedback)
    if message is None:
        raise ChatsError("Message not found", status_code=404)
    if message.role != "assistant":
        raise ChatsError("Only a reply can be rated", status_code=422)
    return message


async def update_message_email(
    session: AsyncSession,
    redis: Redis,
    user: User,
    chat_id: UUID,
    message_id: UUID,
    *,
    to: str | None,
    subject: str | None,
    body: str,
) -> Message:
    """Rewrite the first ```email fence on an assistant message. Not arbitrary content PATCH."""
    await get_chat(session, user, chat_id)
    message = await conversation_history.message_in_chat(session, message_id, chat_id)
    if message is None:
        await session.commit()  # end the reads; no transaction across the wait
        await finalize_registry.wait_for_pending_finalize(chat_id, redis)
        message = await conversation_history.message_in_chat(session, message_id, chat_id)
    if message is None:
        raise ChatsError("Message not found", status_code=404)
    if message.role != "assistant":
        raise ChatsError("Only assistant email drafts can be updated", status_code=400)
    rewritten = rewrite_first_email_fence(message.content, to=to, subject=subject, body=body)
    if rewritten is None:
        raise ChatsError("No email draft on this message", status_code=400)
    if rewritten == message.content:
        return message
    return await conversation_service.update_content(session, message, rewritten)
