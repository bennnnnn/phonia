"""Attachment gallery, upload verification, and download policy."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import presence_cache
from app.core.config import Settings
from app.core.redis import get_redis_client
from app.exceptions import DomainError
from app.gateways.storage_gateway import (
    LocalStorageGateway,
    StorageUnavailableError,
    get_storage_gateway,
)
from app.models.orm import Attachment, User
from app.models.schemas.page import Page
from app.modules.attachments import chunks_repository as chunks_repo
from app.modules.attachments import repository as attachments_repo
from app.modules.attachments.content import (
    MAX_ATTACHMENT_SIZE,
    ensure_verified_or_purge,
    purge_invalid_upload,
)
from app.modules.attachments.content_types import bytes_match_claimed, is_image_content_type
from app.modules.attachments.lifecycle import delete_storage_keys, enqueue_failed_storage_deletes
from app.modules.attachments.markers import strip_attachment_from_content
from app.modules.attachments.quota import has_current_upload_reservation, upload_counter
from app.modules.attachments.schemas import AttachmentListItemOut, AttachmentOut
from app.modules.attachments.thumbnails import thumbnail_bytes, thumbnail_edge
from app.modules.attachments.upload import AttachmentUploadError, cancel_pending_upload
from app.modules.conversation import history as chat_history
from app.services.quota import counters

logger = logging.getLogger(__name__)


class AttachmentWorkflowError(DomainError):
    """An attachment read, upload or delete refusal."""


@dataclass(frozen=True)
class FileAccess:
    content_type: str
    local_path: Path | None = None
    redirect_url: str | None = None
    body: bytes | None = None


async def _refund_upload(
    user: User,
    row: Attachment,
) -> None:
    if has_current_upload_reservation(row):
        await counters.refund(upload_counter(row.content_type), get_redis_client(), user.id)


async def _verified_row(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
):
    row = await attachments_repo.get_by_id(session, attachment_id, user.id)
    # End the read before any storage I/O: a thumbnail (R2 reads, a resize queued two at
    # a time, an R2 write) held this pooled connection idle in transaction throughout.
    await session.commit()
    if row is None:
        raise AttachmentWorkflowError("Not found", status_code=404)
    gateway = get_storage_gateway(settings)
    if row.verified_at is None:
        if isinstance(gateway, LocalStorageGateway):
            raise AttachmentWorkflowError(
                "The attachment has not finished uploading", status_code=409
            )
        error, removed = await ensure_verified_or_purge(
            gateway,
            session,
            attachment_id=attachment_id,
            content_type=row.content_type,
            storage_key=row.storage_key,
            declared_size=row.size_bytes,
        )
        if error:
            if removed:
                await _refund_upload(user, row)
            raise AttachmentWorkflowError(error, status_code=400)
    return row, gateway


async def list_attachments(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    category: str | None,
    source: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> Page[AttachmentListItemOut]:
    # The cursor follows the last row read, a row dropped below for a lost file included.
    rows, next_cursor = await attachments_repo.list_for_gallery(
        session,
        user.id,
        category=category,
        source=source,
        q=q,
        limit=limit,
        cursor=cursor,
    )
    message_ids = [row.message_id for row in rows if row.message_id is not None]
    chat_meta = await attachments_repo.chat_meta_for_message_ids(session, message_ids)
    gateway = get_storage_gateway(settings)
    items: list[AttachmentListItemOut] = []
    for row in rows:
        if (
            isinstance(gateway, LocalStorageGateway)
            and gateway.resolve_local_path(row.storage_key) is None
        ):
            # Neon still has the row after /tmp (or a moved datadir) lost the blob.
            await _drop_row_for_missing_file(session, row.id)
            continue
        url = f"/attachments/{row.id}/file"
        chat_id, chat_title = (
            chat_meta.get(row.message_id, (None, None)) if row.message_id else (None, None)
        )
        items.append(
            AttachmentListItemOut(
                id=row.id,
                content_type=row.content_type,
                size_bytes=row.size_bytes,
                download_url=url,
                source=row.source,
                created_at=row.created_at,
                chat_id=chat_id,
                message_id=row.message_id,
                original_filename=row.original_filename,
                chat_title=chat_title,
            )
        )
    return Page(items=items, next_cursor=next_cursor)


async def delete_attachment(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
) -> None:
    """Cancel a pending upload or remove a Library item (bytes, row, chat marker)."""
    row = await attachments_repo.get_by_id(session, attachment_id, user.id)
    if row is None:
        raise AttachmentWorkflowError("Not found", status_code=404)
    if row.message_id is None:
        try:
            await cancel_pending_upload(session, settings, user=user, attachment_id=attachment_id)
        except AttachmentUploadError as exc:
            raise AttachmentWorkflowError(
                exc.message, status_code=exc.status_code, code=exc.code
            ) from exc
        return
    await _delete_library_attachment(session, settings, user, row)


async def _delete_library_attachment(
    session: AsyncSession,
    settings: Settings,
    user: User,
    row: Attachment,
) -> None:
    message_id = row.message_id
    storage_key = row.storage_key
    # A document's chunks go with its row: the chat may have no indexed file left.
    indexed_in: UUID | None = None
    if message_id is not None:
        message = await chat_history.message_for_user(session, message_id, user.id)
        if message is not None:
            if not is_image_content_type(row.content_type):
                indexed_in = message.chat_id
            next_content = strip_attachment_from_content(message.content, row.id)
            if next_content:
                message.content = next_content
            else:
                await session.delete(message)
    await attachments_repo.delete_rows(session, [row.id], commit=False)
    await session.commit()
    if indexed_in is not None:
        # Else the chat's remembered "has documents" kept every turn embedding its
        # question and telling the model no excerpt of the deleted file matched.
        await presence_cache.forget_presence(presence_cache.documents_key(indexed_in))
    failed = await delete_storage_keys(settings, [storage_key] if storage_key else [])
    await enqueue_failed_storage_deletes(failed)


class _UploadTooLarge(Exception):
    pass


async def _read_upload_capped(stream: AsyncIterator[bytes], max_bytes: int) -> bytes:
    """Read the body without buffering past the declared/max size."""
    parts: list[bytes] = []
    size = 0
    async for chunk in stream:
        if not chunk:
            continue
        size += len(chunk)
        if size > max_bytes:
            raise _UploadTooLarge
        parts.append(chunk)
    return b"".join(parts)


async def store_local_upload(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
    stream: AsyncIterator[bytes],
) -> None:
    row = await attachments_repo.get_by_id(session, attachment_id, user.id, for_update=True)
    if row is None:
        raise AttachmentWorkflowError("Not found", status_code=404)
    gateway = get_storage_gateway(settings)
    if not isinstance(gateway, LocalStorageGateway):
        raise AttachmentWorkflowError("Use presigned upload", status_code=501)
    if row.message_id is not None:
        raise AttachmentWorkflowError("Attachment is already linked to a message", status_code=409)

    cap = min(MAX_ATTACHMENT_SIZE, max(row.size_bytes, 0))
    detail: str | None = None
    try:
        data = await _read_upload_capped(stream, cap)
    except _UploadTooLarge:
        data = b""
        detail = "Invalid upload size"
    if detail is None:
        if not data or len(data) > MAX_ATTACHMENT_SIZE:
            detail = "Invalid upload size"
        elif len(data) != row.size_bytes:
            detail = "Uploaded size does not match the declared size"
        elif not bytes_match_claimed(row.content_type, data):
            detail = "Uploaded bytes do not match the declared content type"
    if row.verified_at is not None:
        if detail is None and await gateway.read_bytes(row.storage_key) == data:
            return
        raise AttachmentWorkflowError("The attachment has already been uploaded", status_code=409)
    if detail:
        removed = await purge_invalid_upload(
            gateway,
            session,
            attachment_id=row.id,
            storage_key=row.storage_key,
        )
        if removed:
            await _refund_upload(user, row)
        raise AttachmentWorkflowError(detail, status_code=400)

    await gateway.write_bytes(row.storage_key, data)
    await attachments_repo.mark_verified(session, row.id)


async def confirm_upload(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
) -> None:
    row = await attachments_repo.get_by_id(session, attachment_id, user.id)
    await session.commit()  # the check below downloads the whole object: no transaction open
    if row is None:
        raise AttachmentWorkflowError("Not found", status_code=404)
    gateway = get_storage_gateway(settings)
    if isinstance(gateway, LocalStorageGateway):
        if row.verified_at is None:
            raise AttachmentWorkflowError(
                "The attachment has not finished uploading", status_code=409
            )
        return
    error, removed = await ensure_verified_or_purge(
        gateway,
        session,
        attachment_id=attachment_id,
        content_type=row.content_type,
        storage_key=row.storage_key,
        declared_size=row.size_bytes,
    )
    if error:
        if removed:
            await _refund_upload(user, row)
        raise AttachmentWorkflowError(error, status_code=400)


async def _drop_row_for_missing_file(session: AsyncSession, attachment_id: UUID) -> None:
    """Remove a gallery row whose bytes are already gone (best-effort)."""
    try:
        await attachments_repo.delete_rows(session, [attachment_id], commit=True)
    except Exception:
        logger.exception("Failed to drop missing-file attachment row %s", attachment_id)


async def get_file_access(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
    *,
    width: int | None = None,
) -> FileAccess:
    row, gateway = await _verified_row(session, settings, user, attachment_id)
    edge = thumbnail_edge(width)
    if edge is not None and is_image_content_type(row.content_type):
        try:
            thumb = await thumbnail_bytes(gateway, settings, row.storage_key, edge)
        except StorageUnavailableError:
            raise
        except Exception:
            logger.exception("Thumbnail resize failed attachment_id=%s", attachment_id)
            raise AttachmentWorkflowError("Could not resize image", status_code=422) from None
        if thumb is None:
            await _drop_row_for_missing_file(session, row.id)
            raise AttachmentWorkflowError("File missing", status_code=404)
        body, content_type = thumb
        return FileAccess(content_type=content_type, body=body)
    if isinstance(gateway, LocalStorageGateway):
        path = gateway.resolve_local_path(row.storage_key)
        if path is None:
            logger.warning(
                "attachment blob missing on disk attachment_id=%s storage_key=%s",
                attachment_id,
                row.storage_key,
            )
            await _drop_row_for_missing_file(session, row.id)
            raise AttachmentWorkflowError("File missing", status_code=404)
        return FileAccess(content_type=row.content_type, local_path=path)
    return FileAccess(
        content_type=row.content_type,
        redirect_url=await gateway.presign_download(row.storage_key),
    )


async def get_download(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
) -> AttachmentOut:
    row, gateway = await _verified_row(session, settings, user, attachment_id)
    url = (
        f"/attachments/{attachment_id}/file"
        if isinstance(gateway, LocalStorageGateway)
        else await gateway.presign_download(row.storage_key)
    )
    indexed = True
    if not is_image_content_type(row.content_type):
        try:
            indexed = await chunks_repo.has_chunks_for_attachment(session, user.id, attachment_id)
        except Exception:
            logger.warning("attachment indexed probe failed id=%s", attachment_id, exc_info=True)
            indexed = False
    return AttachmentOut(
        id=row.id,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        download_url=url,
        created_at=row.created_at,
        indexed=indexed,
        original_filename=row.original_filename,
    )
