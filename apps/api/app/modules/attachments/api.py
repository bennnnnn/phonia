from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_settings_dep
from app.gateways.storage_gateway import StorageUnavailableError
from app.models.orm import User
from app.models.schemas.page import Page
from app.modules.attachments import workflow as attachment_workflow
from app.modules.attachments.schemas import (
    AttachmentListItemOut,
    AttachmentOut,
    AttachmentPresignIn,
    AttachmentPresignOut,
)
from app.modules.attachments.upload import create_presigned_upload

router = APIRouter(prefix="/attachments", tags=["attachments"])


async def require_attachments_enabled(
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Reject write endpoints when the attachments feature flag is off.
    Reads (file/url) and cancel-delete stay open so existing attachments can
    still be retrieved and pending uploads cleaned up after a flag flip."""
    if not settings.attachments_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attachments are disabled",
        )


def _storage_http_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Attachment storage is temporarily unavailable. Please try again.",
        headers={"Retry-After": "5"},
    )


@contextmanager
def _workflow_http_errors() -> Iterator[None]:
    """Answer a workflow refusal with its status, and a storage outage with 503."""
    try:
        yield
    except StorageUnavailableError as exc:
        raise _storage_http_error() from exc


@router.get("", response_model=Page[AttachmentListItemOut])
async def list_attachments(
    category: str | None = Query(default=None, pattern="^(images|files)$"),
    source: str | None = Query(default=None, pattern="^(upload|generated)$"),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Page[AttachmentListItemOut]:
    """One page of the user's attachments, newest first; ``cursor`` reads the next.

    ``q`` is a case-insensitive substring over filename, content type, and
    the linked message (covers image-gen prompts).
    """
    query = q.strip() if q else None
    if not query:
        query = None
    return await attachment_workflow.list_attachments(
        session,
        settings,
        user,
        category=category,
        source=source,
        q=query,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/presign",
    response_model=AttachmentPresignOut,
    dependencies=[Depends(require_attachments_enabled)],
)
async def presign_upload(
    body: AttachmentPresignIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> AttachmentPresignOut:
    try:
        return await create_presigned_upload(
            session,
            settings,
            user=user,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
            filename=body.filename,
        )
    except StorageUnavailableError as exc:
        raise _storage_http_error() from exc


@router.put(
    "/{attachment_id}/upload",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_attachments_enabled)],
)
async def upload_attachment_bytes(
    attachment_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    with _workflow_http_errors():
        await attachment_workflow.store_local_upload(
            session,
            settings,
            user,
            attachment_id,
            request.stream(),
        )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Cancel a pending upload, or delete a Library attachment and its chat marker."""
    with _workflow_http_errors():
        await attachment_workflow.delete_attachment(
            session,
            settings,
            user,
            attachment_id,
        )


@router.post(
    "/{attachment_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_attachments_enabled)],
)
async def confirm_upload(
    attachment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Verify bytes stored at presigned URL match the declared content type."""
    with _workflow_http_errors():
        await attachment_workflow.confirm_upload(
            session,
            settings,
            user,
            attachment_id,
        )


@router.get("/{attachment_id}/file", response_model=None)
async def serve_attachment_file(
    attachment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    w: int | None = Query(default=None, ge=1, le=512),
) -> FileResponse | RedirectResponse | Response:
    with _workflow_http_errors():
        access = await attachment_workflow.get_file_access(
            session,
            settings,
            user,
            attachment_id,
            width=w,
        )
    if access.body is not None:
        return Response(
            content=access.body,
            media_type=access.content_type,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=86400",
            },
        )
    if access.local_path is not None:
        return FileResponse(
            access.local_path,
            media_type=access.content_type,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=86400",
            },
        )
    if access.redirect_url is None:
        raise RuntimeError("Attachment access result has no target")
    return RedirectResponse(
        url=access.redirect_url,
        status_code=status.HTTP_302_FOUND,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{attachment_id}/url", response_model=AttachmentOut)
async def download_url(
    attachment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> AttachmentOut:
    with _workflow_http_errors():
        return await attachment_workflow.get_download(
            session,
            settings,
            user,
            attachment_id,
        )
