"""Reference-photo lookup — search + SSRF-safe mirror + chat persistence.

Separate product path from ``generation.py`` (AI creation). Finds a
real photo via Tavily image search, mirrors the bytes into Recall's own
storage (SSRF-safe fetch, size/type validated exactly like any other
attachment upload), and attaches it to the chat as an ``[Image: …]`` marker
— the client never renders a third-party URL directly.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.exceptions import DomainError
from app.gateways import image_search_gateway, safe_fetch
from app.gateways.storage_gateway import (
    StorageGateway,
    UnconfiguredStorageGateway,
    get_storage_gateway,
)
from app.models.orm import Message, User
from app.modules.attachments import service as attachments_service
from app.modules.attachments.markers import image_marker
from app.modules.attachments.service import (
    MAX_ATTACHMENT_SIZE,
    StoredImage,
    bytes_match_claimed,
    is_image_content_type,
    normalize_content_type,
)
from app.modules.chat import finish_turn
from app.modules.conversation import history as chat_history
from app.modules.conversation import turn_record
from app.services import quota as quota_service
from app.services.quota import counters

logger = logging.getLogger(__name__)

_IMAGE_SEARCH_MODEL_ALIAS = "image-search-model"
_USER_MESSAGE_PREFIX = "Show me: "
_FETCH_MAX_REDIRECTS = 5
# Wikimedia answers a bare client 403, and Britannica sent "compressed" bytes
# that would not decode: every Einstein photo failed and the turn drew one
# instead. Images are already compressed, so ask for the bytes as they are.
_FETCH_HEADERS = {
    "User-Agent": "RecallPhotos/1.0 (reference photos in a chat app)",
    "Accept": "image/*",
    "Accept-Encoding": "identity",
}


class ImageSearchError(DomainError):
    """A reference-photo lookup refusal."""


def _photo_limit_refusal(user: User) -> ImageSearchError:
    """Today's photo lookups are used up: 429 ``daily_limit``, naming the feature."""
    return ImageSearchError(
        counters.limit_message("image_search", user),
        status_code=429,
        code="daily_limit",
        feature="photo_lookup",
    )


async def _rollback_written_bytes(gateway: StorageGateway, storage_keys: list[str]) -> None:
    """Delete object storage if persist failed after write_bytes.

    The orphan reaper only sees attachment rows. A write with no row (or a
    failed persist) would leak the object forever without this rollback.
    """
    failed: list[str] = []
    for key in storage_keys:
        try:
            await gateway.delete_bytes(key)
        except Exception:
            logger.exception("Failed to delete orphaned reference-photo bytes %s", key)
            failed.append(key)
    # No row will ever name them: only the retry queue finds them again.
    await attachments_service.queue_storage_deletes(failed)


async def _fetch_one_image(
    client: httpx.AsyncClient,
    hit: image_search_gateway.ImageSearchHit,
    *,
    deadline_seconds: float,
) -> tuple[bytes, str] | None:
    """Best-effort SSRF-safe fetch + validation of one candidate image URL.

    Any failure (network, oversized, wrong content-type, spoofed bytes)
    returns None so the caller tries the next candidate instead of erroring
    the whole turn over one bad search result.
    """
    try:
        response = await safe_fetch.fetch_safely(
            client,
            hit.image_url,
            deadline_seconds=deadline_seconds,
            max_redirects=_FETCH_MAX_REDIRECTS,
            max_body_bytes=MAX_ATTACHMENT_SIZE,
            headers=_FETCH_HEADERS,
        )
        if response.status_code >= 400 or not response.content:
            return None
        content_type = normalize_content_type(response.headers.get("content-type", "image/jpeg"))
        data = response.content
    except Exception:
        logger.warning("Reference-photo candidate fetch failed", exc_info=True)
        return None
    if len(data) > MAX_ATTACHMENT_SIZE or not is_image_content_type(content_type):
        return None
    if not bytes_match_claimed(content_type, data):
        return None
    return data, content_type


async def _fetch_candidates(
    settings: Settings,
    hits: list[image_search_gateway.ImageSearchHit],
    *,
    max_images: int,
) -> list[tuple[bytes, str]]:
    """The first ``max_images`` usable photos, fetched side by side under one deadline.

    One after another, a slow host used its whole 8 s before the next candidate was
    tried, so an answer photo (which waits 6 s) went out empty even when the next
    candidate would have arrived at once.
    """
    deadline = settings.image_search_fetch_timeout_seconds
    fetched: list[tuple[bytes, str]] = []
    async with safe_fetch.fetch_client(deadline) as client:
        pending = {
            asyncio.create_task(_fetch_one_image(client, hit, deadline_seconds=deadline))
            for hit in hits
        }
        try:
            async with asyncio.timeout(deadline):
                while pending and len(fetched) < max_images:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    fetched.extend(found for task in done if (found := task.result()) is not None)
        except TimeoutError:
            logger.info("Reference-photo candidates ran past %ss", deadline)
        finally:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    return fetched[:max_images]


async def _find_photos(
    settings: Settings, query: str, *, max_images: int
) -> list[tuple[bytes, str]]:
    """Search and fetch up to ``max_images`` usable photos. No DB session is held."""
    hits = await image_search_gateway.search_images(
        settings, query, max_results=settings.image_search_max_results
    )
    if not hits:
        raise ImageSearchError("Could not find a reference photo", status_code=502)
    fetched = await _fetch_candidates(settings, hits, max_images=max_images)
    if not fetched:
        raise ImageSearchError("Could not find a usable reference photo", status_code=502)
    return fetched


async def _upload_photos(
    gateway: StorageGateway,
    user: User,
    fetched: list[tuple[bytes, str]],
    *,
    written_keys: list[str],
) -> list[StoredImage]:
    """Write the photos' bytes to storage, with no database transaction open."""
    stored: list[StoredImage] = []
    for data, content_type in fetched:
        presigned = await gateway.presign_upload(
            user_id=str(user.id),
            content_type=content_type,
            size_bytes=len(data),
        )
        await gateway.write_bytes(presigned.storage_key, data)
        written_keys.append(presigned.storage_key)
        stored.append(
            StoredImage(
                attachment_id=UUID(presigned.attachment_id),
                storage_key=presigned.storage_key,
                content_type=content_type,
                size_bytes=len(data),
            )
        )
    return stored


async def _add_photo_rows(
    session: AsyncSession,
    user: User,
    stored: list[StoredImage],
    *,
    label: str,
    message_id: UUID | None,
) -> None:
    """The stored photos' rows, kept out of the Library; no commit.

    Inserted after every upload finished: the R2 writes for photos two and three used
    to run inside the transaction holding photo one's row.
    """
    await attachments_service.add_server_images(
        session,
        user_id=user.id,
        images=stored,
        source="search",
        label=label,
        message_id=message_id,
        in_library=False,
    )


async def search_and_attach_for_chat(
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    query: str,
    user_message_content: str | None = None,
    create_user_message: bool = True,
) -> tuple[Message, Message]:
    """Plan/quota/storage/persist path for a reference-photo lookup turn.

    Returns (user_message, assistant_message). Raises ``ImageSearchError`` on
    expected failures (not found, quota, storage); unexpected exceptions are
    re-raised after quota refund. Mirrors ``image_generation.generate_for_chat``'s
    shape — the "provider call" here is a Tavily image search followed by an
    SSRF-safe fetch of the winning photo(s), never an AI generation, and runs
    with no DB session held.
    """
    if not settings.image_search_enabled:
        raise ImageSearchError("Not available", status_code=404, code="not_available")
    if not settings.attachments_enabled:
        raise ImageSearchError("Attachments are disabled", status_code=503)

    cleaned = query.strip()
    if not cleaned:
        raise ImageSearchError("Query is required", status_code=400)

    async with SessionLocal() as session:
        chat = await chat_history.get_chat(session, chat_id, user.id)
        if chat is None:
            raise ImageSearchError("Chat not found", status_code=404)

    gateway = get_storage_gateway(settings)
    if isinstance(gateway, UnconfiguredStorageGateway):
        raise ImageSearchError("Attachment storage is not configured", status_code=503)

    redis = get_redis_client()
    if await quota_service.global_spend_exceeded(redis, settings):
        raise ImageSearchError(
            quota_service.IMAGE_SEARCH_SPEND_CAP_MESSAGE,
            status_code=429,
            code="spend_cap",
        )
    day = await counters.reserve("image_search", redis, user, settings)
    if not day:
        raise _photo_limit_refusal(user)

    written_keys: list[str] = []
    try:
        # Provider HTTP (search + candidate fetches) — no DB session held.
        fetched = await _find_photos(
            settings, cleaned, max_images=settings.image_search_max_results
        )
        stored = await _upload_photos(gateway, user, fetched, written_keys=written_keys)
        async with SessionLocal() as session:
            prior_count = await chat_history.message_count(session, chat_id)
            if create_user_message:
                bubble = (user_message_content or f"{_USER_MESSAGE_PREFIX}{cleaned}").strip()
                if not bubble:
                    bubble = f"{_USER_MESSAGE_PREFIX}{cleaned}"
                user_message = await turn_record.add_turn_message(
                    session, chat_id=chat_id, user_id=user.id, role="user", content=bubble
                )
            else:
                existing = await chat_history.last_user_message(session, chat_id)
                if existing is None:
                    raise ImageSearchError("No user message to attach image to", status_code=404)
                user_message = existing

            markers = "\n".join(image_marker(photo.attachment_id) for photo in stored)
            assistant_message = await turn_record.add_turn_message(
                session,
                chat_id=chat_id,
                user_id=user.id,
                role="assistant",
                content=markers,
                model=_IMAGE_SEARCH_MODEL_ALIAS,
            )
            await _add_photo_rows(
                session, user, stored, label=cleaned, message_id=assistant_message.id
            )
            # Persist the turn atomically. If a write fails, session close rolls
            # back rows before byte cleanup.
            await session.commit()
    except BaseException:
        # Any failure, an ImageSearchError or a cancellation too: drop the
        # bytes written so far and give the day's slot back.
        await _rollback_written_bytes(gateway, written_keys)
        await counters.refund("image_search", redis, user.id, day=day)
        raise

    try:
        await quota_service.record_global_spend(redis, quota_service.IMAGE_SEARCH_SPEND_USD)
    except Exception:
        logger.exception("record_global_spend failed after photo lookup")
    if create_user_message:
        # As a typed turn's: its title, memory and indexing (code-health audit ARCH-08).
        await finish_turn(
            redis,
            settings,
            user=user,
            chat_id=chat_id,
            user_message=user_message.content,
            assistant=assistant_message,
            prior_count=prior_count,
        )
    return user_message, assistant_message


async def photos_for_answer(settings: Settings, *, user: User, query: str) -> list[UUID]:
    """One real photo for an answer about something worth seeing, stored but not linked.

    The reply's finalize links it to the assistant message. Best-effort: when
    lookup is off, storage is missing, the daily limit is spent or nothing
    usable is found, this returns [] and the answer goes out without a photo.
    """
    cleaned = " ".join(query.split())[:120]
    if not (settings.image_search_enabled and settings.attachments_enabled and cleaned):
        return []
    gateway = get_storage_gateway(settings)
    if isinstance(gateway, UnconfiguredStorageGateway):
        return []
    redis = get_redis_client()
    if await quota_service.global_spend_exceeded(redis, settings):
        return []
    day = await counters.reserve("image_search", redis, user, settings)
    if not day:
        return []

    written_keys: list[str] = []
    try:
        fetched = await _find_photos(settings, cleaned, max_images=1)
        stored = await _upload_photos(gateway, user, fetched, written_keys=written_keys)
        async with SessionLocal() as session:
            await _add_photo_rows(session, user, stored, label=cleaned, message_id=None)
            await session.commit()
    except ImageSearchError:
        await _rollback_written_bytes(gateway, written_keys)
        await counters.refund("image_search", redis, user.id, day=day)
        return []
    except Exception:
        logger.exception("Answer photo lookup failed")
        await _rollback_written_bytes(gateway, written_keys)
        await counters.refund("image_search", redis, user.id, day=day)
        return []
    except BaseException:
        await _rollback_written_bytes(gateway, written_keys)
        await counters.refund("image_search", redis, user.id, day=day)
        raise

    try:
        await quota_service.record_global_spend(redis, quota_service.IMAGE_SEARCH_SPEND_USD)
    except Exception:
        logger.exception("record_global_spend failed after answer photo")
    return [photo.attachment_id for photo in stored]
