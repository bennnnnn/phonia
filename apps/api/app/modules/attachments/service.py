"""Public attachment operations for other product modules.

Other modules may import this file. They may not import the repository or the
extractor directly, and they do not compose its writes: each operation here says what
it does to the user's files (code-health audit ARCH-05). One that takes the caller's
session and says "no commit" joins the caller's unit of work, which commits it or rolls
it back.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.attachment_limits import MAX_ATTACHMENT_SIZE as MAX_ATTACHMENT_SIZE
from app.core.config import Settings
from app.models.orm import Attachment
from app.modules.attachments import jobs as _jobs
from app.modules.attachments import lifecycle as _lifecycle
from app.modules.attachments import rag as _rag
from app.modules.attachments import repository as _repo
from app.modules.attachments.content_types import bytes_match_claimed as bytes_match_claimed
from app.modules.attachments.content_types import is_image_content_type as is_image_content_type
from app.modules.attachments.content_types import (
    normalize_content_type as normalize_content_type,
)
from app.modules.attachments.models import ORIGINAL_FILENAME_MAX_CHARS


@dataclass(frozen=True, slots=True)
class StoredImage:
    """Image bytes the server put in storage and checked itself."""

    attachment_id: UUID
    storage_key: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ReferenceCopy:
    """A private copy of a reference image, its bytes already stored under ``storage_key``."""

    source: Attachment
    attachment_id: UUID
    storage_key: str


async def add_server_images(
    session: AsyncSession,
    *,
    user_id: UUID,
    images: Sequence[StoredImage],
    source: Literal["generated", "search"],
    label: str,
    message_id: UUID | None = None,
    in_library: bool = True,
) -> None:
    """Rows for images the server made or fetched; no commit.

    They are verified at once, so ``/file`` never downloads them again to check, and with
    ``message_id`` they are already on that message. ``label`` (the prompt or the search)
    names them in the Library.
    """
    filename = label.replace("\n", " ").strip()[:ORIGINAL_FILENAME_MAX_CHARS] or None
    for image in images:
        await _repo.insert_verified(
            session,
            attachment_id=image.attachment_id,
            user_id=user_id,
            storage_key=image.storage_key,
            content_type=image.content_type,
            size_bytes=image.size_bytes,
            source=source,
            original_filename=filename,
            library_visible=in_library,
            message_id=message_id,
        )


async def add_reference_copies(
    session: AsyncSession, *, message_id: UUID, copies: Sequence[ReferenceCopy]
) -> None:
    """Hidden copies of reference images on the user's message; no commit.

    Each is its own row over its own bytes, so an edit or a regenerate still finds its
    reference after the original is deleted.
    """
    for copy in copies:
        await _repo.insert_verified_clone(
            session,
            src=copy.source,
            new_id=copy.attachment_id,
            storage_key=copy.storage_key,
            message_id=message_id,
        )


async def claim_profile_photo(session: AsyncSession, attachment_id: UUID, user_id: UUID) -> bool:
    """Take the user's upload for their profile photo; no commit.

    Only a finished image upload that no message carries qualifies; it is locked and
    leaves the Library. False when it does not qualify.
    """
    photo = await _repo.get_by_id(session, attachment_id, user_id, for_update=True)
    if (
        photo is None
        or photo.verified_at is None
        or photo.message_id is not None
        or photo.source != "upload"
        or not is_image_content_type(photo.content_type)
        or not 0 < photo.size_bytes <= MAX_ATTACHMENT_SIZE
    ):
        return False
    await _repo.hide_from_gallery(session, photo)
    return True


async def link_to_message(
    session: AsyncSession,
    *,
    user_id: UUID,
    attachment_ids: list[UUID],
    message_id: UUID,
    commit: bool = True,
) -> int:
    """Join the user's attachments to the message just created; how many were joined."""
    return await _repo.link_to_message(
        session,
        user_id=user_id,
        attachment_ids=attachment_ids,
        message_id=message_id,
        commit=commit,
    )


async def mark_verified_many(session: AsyncSession, attachment_ids: list[UUID]) -> None:
    """Record that these uploads' bytes matched their declared type and size; commits."""
    await _repo.mark_verified_many(session, attachment_ids)


async def get_by_ids(
    session: AsyncSession, attachment_ids: list[UUID], user_id: UUID
) -> list[Attachment]:
    """The user's attachments among these ids, in no particular order."""
    return await _repo.get_by_ids(session, attachment_ids, user_id)


async def list_for_message_ids(session: AsyncSession, message_ids: list[UUID]) -> list[Attachment]:
    """The attachments these messages carry."""
    return await _repo.list_for_message_ids(session, message_ids)


async def list_for_user(
    session: AsyncSession, user_id: UUID, *, limit: int | None = None
) -> list[Attachment]:
    """Every attachment the user owns, sent or not, oldest first (the data export)."""
    return await _repo.list_for_user(session, user_id, limit=limit)


async def chat_has_document_chunks(user_id: UUID, chat_id: UUID) -> bool:
    """Whether this chat has searchable document text."""
    return await _rag.chat_has_document_chunks(user_id, chat_id)


async def enqueue_index_jobs(
    settings: Settings, *, user_id: UUID, chat_id: UUID, attachment_ids: list[str]
) -> None:
    """Index a turn's documents once its user message committed; never raises."""
    await _jobs.enqueue_index_jobs(
        settings, user_id=user_id, chat_id=chat_id, attachment_ids=attachment_ids
    )


async def delete_account_files(settings: Settings, storage_keys: list[str]) -> None:
    """Delete a deleted account's stored files, once its rows are committed; never raises."""
    await _lifecycle.delete_objects_of_deleted_rows(settings, storage_keys)


async def sweep_account_storage(settings: Settings, user_id: UUID) -> int:
    """Delete every object left under a deleted account's prefix (its ``storage_sweep``)."""
    return await _lifecycle.sweep_user_storage(settings, user_id)


async def queue_storage_deletes(storage_keys: list[str]) -> None:
    """Objects whose delete failed and that no row names any more: the reaper retries them."""
    await _lifecycle.enqueue_failed_storage_deletes(storage_keys)


async def delete_user_rows(session: AsyncSession, user_id: UUID) -> list[str]:
    """Every attachment row of a deleted account; no commit (``account.lifecycle``).

    Returns the storage keys they named, for ``delete_account_files`` once the account's
    delete commits: the files go only with the rows, never before them. Under the user's
    row lock no attachment can be added between the read and the delete.
    """
    rows = await _repo.list_for_user(session, user_id)
    await _repo.delete_all_for_user(session, user_id)
    return [row.storage_key for row in rows if row.storage_key]
