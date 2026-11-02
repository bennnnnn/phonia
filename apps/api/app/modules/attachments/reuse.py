"""Copy a Library attachment so a new chat can link it without stealing the original."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.exceptions import AttachmentValidationError
from app.gateways.storage_gateway import get_storage_gateway
from app.models.orm import Attachment
from app.modules.attachments import repository as attachments_repo


async def ensure_unlinked_copies(
    session: AsyncSession,
    settings: Settings,
    rows: list[Attachment],
) -> list[Attachment]:
    """Keep already-unlinked rows; copy bytes + insert a hidden clone for linked ones.

    ``link_to_message`` only updates ``message_id IS NULL``. Reusing a Library
    item that is still attached to yesterday's chat needs a new row so today's
    send can link, and so deleting one chat cannot drop the other's file.

    Every copy finishes before a clone row is written: the storage copies used to run
    inside the transaction that read ``rows``, on the chat turn's critical path.
    """
    linked = [row for row in rows if row.message_id is not None]
    if not linked:
        return list(rows)
    if any(row.verified_at is None for row in linked):
        raise AttachmentValidationError("The attached file has not finished uploading.")
    await session.commit()  # end the caller's read before the storage copies
    gateway = get_storage_gateway(settings)
    copies: dict[UUID, tuple[UUID, str]] = {}
    created_keys: list[str] = []
    try:
        for row in linked:
            new_id = uuid4()
            storage_key = f"{row.user_id}/{new_id}"
            created_keys.append(storage_key)
            # Copied inside storage: a 10 MB file no longer passes through the API.
            if not await gateway.copy_bytes(row.storage_key, storage_key):
                raise AttachmentValidationError("Could not read the attached file.")
            copies[row.id] = (new_id, storage_key)
        out: list[Attachment] = []
        for row in rows:
            if row.message_id is None:
                out.append(row)
                continue
            new_id, storage_key = copies[row.id]
            out.append(
                await attachments_repo.insert_verified_clone(
                    session, src=row, new_id=new_id, storage_key=storage_key
                )
            )
        await session.commit()
    except BaseException:
        try:
            await session.rollback()
        finally:
            from app.modules.attachments.lifecycle import (
                delete_storage_keys,
                enqueue_failed_storage_deletes,
            )

            failed = await delete_storage_keys(settings, created_keys)
            await enqueue_failed_storage_deletes(failed)
        raise
    return out
