"""Presign + pending-row orchestration for attachment uploads."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.redis import get_redis_client
from app.exceptions import DomainError
from app.gateways.storage_gateway import UnconfiguredStorageGateway, get_storage_gateway
from app.models.orm import User
from app.modules.attachments import repository as attachments_repo
from app.modules.attachments.content import MAX_ATTACHMENT_SIZE
from app.modules.attachments.content_types import (
    is_allowed_content_type,
    normalize_content_type,
)
from app.modules.attachments.models import ORIGINAL_FILENAME_MAX_CHARS
from app.modules.attachments.quota import has_current_upload_reservation, upload_counter
from app.modules.attachments.schemas import AttachmentPresignOut
from app.services.quota import counters


class AttachmentUploadError(DomainError):
    """An upload refusal; the phone names the type, size and daily limit by code."""


def sanitize_original_filename(name: str | None) -> str | None:
    """Basename only, cut to the column's width. Reject empty / traversal names."""
    if name is None:
        return None
    base = name.strip().replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not base or base in (".", ".."):
        return None
    return base[:ORIGINAL_FILENAME_MAX_CHARS]


async def create_presigned_upload(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    content_type: str,
    size_bytes: int,
    filename: str | None = None,
) -> AttachmentPresignOut:
    """Validate, reserve image quota, presign storage, and create a pending row."""
    if not is_allowed_content_type(content_type):
        raise AttachmentUploadError(
            "Unsupported content type", status_code=400, code="unsupported_type"
        )
    if size_bytes <= 0 or size_bytes > MAX_ATTACHMENT_SIZE:
        raise AttachmentUploadError("Invalid file size", status_code=400, code="invalid_size")

    normalized = normalize_content_type(content_type)

    gateway = get_storage_gateway(settings)
    if isinstance(gateway, UnconfiguredStorageGateway):
        raise AttachmentUploadError(
            "Attachment storage is not configured",
            status_code=503,
        )

    redis = get_redis_client()
    counter = upload_counter(normalized)
    reserved_day = await counters.reserve(counter, redis, user, settings)
    if not reserved_day:
        raise AttachmentUploadError(
            counters.limit_message(counter, user), status_code=429, code="daily_limit"
        )

    try:
        presigned = await gateway.presign_upload(
            user_id=str(user.id),
            content_type=normalized,
            size_bytes=size_bytes,
        )
        attachment_id = UUID(presigned.attachment_id)
        await attachments_repo.create_pending(
            session,
            attachment_id=attachment_id,
            user_id=user.id,
            storage_key=presigned.storage_key,
            content_type=normalized,
            size_bytes=size_bytes,
            original_filename=sanitize_original_filename(filename),
            commit=False,
        )
        await session.commit()
    except Exception:
        await counters.refund(counter, redis, user.id, day=reserved_day)
        raise

    return AttachmentPresignOut(
        attachment_id=attachment_id,
        upload_url=presigned.upload_url,
        storage_key=presigned.storage_key,
        headers=presigned.headers,
        api_upload=presigned.api_upload,
    )


async def cancel_pending_upload(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    attachment_id: UUID,
) -> None:
    """Delete a pending upload's bytes/row and refund the image quota slot if any."""
    row = await attachments_repo.get_by_id(session, attachment_id, user.id)
    if row is None:
        raise AttachmentUploadError("Not found", status_code=404)
    if row.message_id is not None:
        raise AttachmentUploadError(
            "Attachment is already linked to a message",
            status_code=409,
        )

    # The conditional DELETE also fences a concurrent send that links this row.
    removed = await attachments_repo.delete_unlinked_returning(session, [attachment_id])
    if not removed:
        raise AttachmentUploadError("Attachment is no longer pending", status_code=409)
    from app.modules.attachments.lifecycle import (
        delete_storage_keys,
        enqueue_failed_storage_deletes,
    )

    failed = await delete_storage_keys(settings, removed)
    await enqueue_failed_storage_deletes(failed)
    if has_current_upload_reservation(row):
        await counters.refund(upload_counter(row.content_type), get_redis_client(), user.id)
