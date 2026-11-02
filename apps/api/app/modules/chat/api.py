from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_redis, get_settings_dep
from app.core.dev_guards import require_dev_privilege_access
from app.core.etag import conditional_json
from app.models.orm import User
from app.models.schemas import (
    ArchiveUpdate,
    ChatBulkAction,
    ChatBulkOut,
    ChatCreate,
    ChatListOut,
    ChatOut,
    ChatRename,
    EmailDraftUpdate,
    FeedbackUpdate,
    MessageOut,
    MessagePageOut,
    PinUpdate,
    UsageOut,
)
from app.models.schemas.page import Page
from app.modules.chat import service as chats_service

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_chat(
    body: ChatCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatOut:
    chat = await chats_service.create_chat(
        session,
        user,
        model=body.model,
    )
    return ChatOut.model_validate(chat)


@router.get("", response_model=ChatListOut)
async def list_chats(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(
        default=chats_service.DEFAULT_CHAT_LIST_LIMIT,
        ge=1,
        le=chats_service.DEFAULT_CHAT_LIST_LIMIT,
    ),
    cursor: str | None = Query(default=None, max_length=200),
    # The phone's IANA zone, bounded like a chat turn's: its days head the drawer's groups.
    client_timezone: str | None = Query(default=None, max_length=64),
) -> Response:
    chats = await chats_service.list_chats_grouped(
        session, user, limit=limit, cursor=cursor, client_timezone=client_timezone
    )
    # The ETag hashes the grouped body, so a list grouped in another zone never gets a 304.
    return conditional_json(request, chats)


@router.get("/archived", response_model=Page[ChatOut])
async def list_archived_chats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=chats_service.ARCHIVED_CHAT_LIST_LIMIT, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
) -> Page[ChatOut]:
    """Archived chats past the drawer's first page (``archived_next_cursor``)."""
    return await chats_service.list_archived_chats(session, user, limit=limit, cursor=cursor)


@router.post("/archive-all", status_code=status.HTTP_204_NO_CONTENT)
async def archive_all_chats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await chats_service.archive_all_chats(session, user)


@router.post("/bulk", response_model=ChatBulkOut)
async def bulk_chats(
    body: ChatBulkAction,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatBulkOut:
    """Archive, unarchive or delete the drawer's selection in one request."""
    changed = await chats_service.bulk_chats(
        session, user, action=body.action, chat_ids=body.chat_ids
    )
    return ChatBulkOut(changed=changed)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_chats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    await chats_service.delete_all_chats(session, user, settings=settings)


@router.patch("/{chat_id}", response_model=ChatOut)
async def rename_chat(
    chat_id: UUID,
    body: ChatRename,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatOut:
    chat = await chats_service.rename_chat(session, user, chat_id, body.title)
    return ChatOut.model_validate(chat)


@router.patch("/{chat_id}/pin", response_model=ChatOut)
async def pin_chat(
    chat_id: UUID,
    body: PinUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatOut:
    chat = await chats_service.pin_chat(session, user, chat_id, pinned=body.pinned)
    return ChatOut.model_validate(chat)


@router.patch("/{chat_id}/archive", response_model=ChatOut)
async def archive_chat(
    chat_id: UUID,
    body: ArchiveUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatOut:
    chat = await chats_service.archive_chat(session, user, chat_id, archived=body.archived)
    return ChatOut.model_validate(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID,
    if_empty: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    await chats_service.delete_chat(session, user, chat_id, settings=settings, if_empty=if_empty)


@router.get("/usage/today", response_model=UsageOut)
async def today_usage(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> UsageOut:
    return await chats_service.today_usage(session, redis, settings, user)


@router.post("/usage/today/reset", response_model=UsageOut)
async def reset_today_usage(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> UsageOut:
    require_dev_privilege_access(request, settings, user)
    return await chats_service.reset_today_usage(session, redis, settings, user)


@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(
    chat_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatOut:
    chat = await chats_service.get_chat(session, user, chat_id)
    return ChatOut.model_validate(chat)


@router.get("/{chat_id}/messages", response_model=MessagePageOut)
async def list_messages(
    request: Request,
    chat_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    limit: int = Query(default=40, ge=1, le=200),
    before: UUID | None = None,
    after: UUID | None = None,
    around: UUID | None = None,
) -> Response:
    if sum(cursor is not None for cursor in (before, after, around)) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use one of before, after and around.",
        )
    page = await chats_service.list_messages_page(
        session, redis, user, chat_id, limit=limit, before=before, after=after, around=around
    )
    return conditional_json(request, page)


@router.patch("/{chat_id}/messages/{message_id}/feedback", response_model=MessageOut)
async def set_message_feedback(
    chat_id: UUID,
    message_id: UUID,
    body: FeedbackUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> MessageOut:
    message = await chats_service.set_message_feedback(
        session, redis, user, chat_id, message_id, body.feedback
    )
    return MessageOut.model_validate(message)


@router.patch("/{chat_id}/messages/{message_id}/email", response_model=MessageOut)
async def update_message_email(
    chat_id: UUID,
    message_id: UUID,
    body: EmailDraftUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> MessageOut:
    message = await chats_service.update_message_email(
        session,
        redis,
        user,
        chat_id,
        message_id,
        to=body.to,
        subject=body.subject,
        body=body.body,
    )
    return MessageOut.model_validate(message)
