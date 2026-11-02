"""Text-to-image product service (validation, provider call, chat persistence)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.aio import finish_despite_cancel
from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.exceptions import DomainError
from app.gateways import image_gateway, mock_llm
from app.gateways.storage_gateway import (
    StorageGateway,
    UnconfiguredStorageGateway,
    get_storage_gateway,
)
from app.models.model_catalog import get as get_model
from app.models.model_catalog import openrouter_slug
from app.models.orm import Attachment, Message, User
from app.modules.attachments import service as attachments_service
from app.modules.attachments.markers import image_marker
from app.modules.attachments.service import (
    MAX_ATTACHMENT_SIZE,
    ReferenceCopy,
    StoredImage,
    bytes_match_claimed,
    is_image_content_type,
    normalize_content_type,
)
from app.modules.billing import can_use
from app.modules.chat import finish_turn
from app.modules.conversation import history, turn_record
from app.modules.images.intent import image_reference_ids as image_reference_ids
from app.modules.images.turn_references import shown_in_chat, turn_reference_ids
from app.services import quota as quota_service
from app.services.quota import counters

logger = logging.getLogger(__name__)

_MAX_PROMPT_LEN = 2000
_USER_MESSAGE_PREFIX = "Generate image: "
_IMAGE_MODEL_ALIAS = "image-gen-model"

AspectRatio = Literal["1:1", "16:9", "9:16", "4:3", "3:4"]
_ALLOWED_ASPECT_RATIOS: frozenset[str] = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"})


class ImageGenerationError(DomainError):
    """An image generation refusal."""


async def _rollback_written_bytes(gateway: StorageGateway, storage_key: str | None) -> None:
    """Delete an object that persisting never named (the reaper sees rows only), or queue it.

    Without this an object written before a failed persist leaked for ever.
    """
    if not storage_key:
        return
    try:
        await gateway.delete_bytes(storage_key)
    except Exception:
        logger.exception("Failed to delete orphaned generated image %s", storage_key)
        await attachments_service.queue_storage_deletes([storage_key])


def normalize_aspect_ratio(value: str | None) -> AspectRatio | None:
    if not value:
        return None
    trimmed = value.strip()
    if trimmed in _ALLOWED_ASPECT_RATIOS:
        return cast(AspectRatio, trimmed)
    return None


async def generate_image(
    settings: Settings,
    *,
    prompt: str,
    aspect_ratio: str | None = None,
    reference_images: list[tuple[bytes, str]] | None = None,
) -> tuple[bytes, str] | None:
    """Return (image_bytes, content_type) or None on failure."""
    if not settings.image_generation_enabled:
        return None
    cleaned = prompt.strip()
    if not cleaned or len(cleaned) > _MAX_PROMPT_LEN:
        logger.warning("Image generation rejected: prompt length=%s", len(cleaned))
        return None
    if mock_llm.should_mock_llm(settings):
        return mock_llm.mock_image_bytes(), "image/png"
    if not settings.openrouter_api_key:
        return None

    model = (settings.image_generation_model or openrouter_slug(_IMAGE_MODEL_ALIAS)).strip()
    return await image_gateway.generate_via_openrouter(
        settings,
        prompt=cleaned,
        model=model,
        aspect_ratio=normalize_aspect_ratio(aspect_ratio),
        reference_images=reference_images,
    )


async def generate_for_chat(
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    prompt: str,
    aspect_ratio: str | None = None,
    user_message_content: str | None = None,
    create_user_message: bool = True,
    reference_attachment_ids: list[UUID] | None = None,
) -> tuple[Message, Message]:
    """Plan/quota/storage/persist path for POST /images/generate.

    Returns (user_message, assistant_message). Raises ImageGenerationError on
    expected failures; unexpected exceptions are re-raised after quota refund.

    ``user_message_content`` is the composer text shown in the user bubble
    (e.g. \"create a cat image\"). Falls back to ``Generate image: …`` only
    when the caller did not pass the original wording. Set
    ``create_user_message=False`` when regenerating — only a new assistant row
    is written. A turn that saved the user's message sets off a typed turn's jobs
    (its title, memory, indexing); a regenerate or the tool loop's picture does not.

    DB sessions open only around ownership checks and persistence — the image
    provider HTTP call runs with no pool checkout held.
    """
    gateway, references, redis = await _authorize_generation(
        settings,
        user=user,
        chat_id=chat_id,
        create_user_message=create_user_message,
        reference_attachment_ids=reference_attachment_ids,
    )
    written = _WrittenBytes(gateway)
    async with _ReservedQuota(redis, user, settings, undo=written.delete_all) as slot:
        cleaned = prompt.strip()
        if not cleaned:
            raise ImageGenerationError("Prompt is required", status_code=400)
        stored = await _generate_and_store(
            settings,
            written,
            user_id=user.id,
            prompt=cleaned,
            aspect_ratio=aspect_ratio,
            references=references,
            copy_references=create_user_message,
        )
        # A Cancel that lands while the turn saves lets the save finish: the picture is
        # the user's then, and its slot is kept.
        saving = _persist_turn(
            stored,
            user_id=user.id,
            chat_id=chat_id,
            prompt=cleaned,
            user_message_content=user_message_content,
            create_user_message=create_user_message,
        )
        user_message, assistant_message, prior_count = await finish_despite_cancel(
            saving, then=slot.keep
        )

    await _record_spend(redis)
    if create_user_message:
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


async def _authorize_generation(
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    create_user_message: bool,
    reference_attachment_ids: list[UUID] | None,
) -> tuple[StorageGateway, list[tuple[Attachment, bytes]], Redis]:
    """Every gate before a slot is taken: flags, plan, chat, storage, references, spend.

    Returns the storage gateway, the owned reference images and Redis. A
    regenerate with no reference ids reuses the images of the last user turn.
    """
    if not settings.image_generation_enabled:
        raise ImageGenerationError("Not available", status_code=404, code="not_available")
    if not settings.attachments_enabled:
        raise ImageGenerationError("Attachments are disabled", status_code=503)
    if not can_use(user, "image_generation", settings):
        raise ImageGenerationError(
            quota_service.IMAGE_GENERATION_NOT_IN_PLAN_MESSAGE, status_code=403, code="not_in_plan"
        )

    async with SessionLocal() as session:
        chat = await history.get_chat(session, chat_id, user.id)
        if chat is None:
            raise ImageGenerationError("Chat not found", status_code=404)
        if reference_attachment_ids is None and not create_user_message:
            prior = await history.last_user_message(session, chat_id)
            reference_attachment_ids = await turn_reference_ids(session, prior)

    gateway = get_storage_gateway(settings)
    if isinstance(gateway, UnconfiguredStorageGateway):
        raise ImageGenerationError("Attachment storage is not configured", status_code=503)

    references = await load_reference_images(
        gateway, user_id=user.id, attachment_ids=reference_attachment_ids or []
    )

    redis = get_redis_client()
    if await quota_service.global_spend_exceeded(redis, settings):
        raise ImageGenerationError(
            quota_service.IMAGE_GENERATION_SPEND_CAP_MESSAGE, status_code=429, code="spend_cap"
        )
    return gateway, references, redis


# A plan or cap refusal from inside the turn keeps its slot (nothing there raises one today).
_SLOT_KEPT_ON_STATUS = (403, 429)


class _ReservedQuota:
    """``async with``: hold one of today's image-generation slots for the block.

    Entering refuses with 429 at the plan's cap. When the block raises anything
    (a cancellation too), ``undo`` runs first, then the slot is given back to
    the day it was taken from unless the error is a 403 or 429
    ImageGenerationError. An exception out of ``undo`` skips the refund; it,
    or one out of the refund, propagates in place of the block's. A class
    rather than ``@asynccontextmanager``, whose generator would turn a
    StopAsyncIteration out of Redis into a RuntimeError.
    """

    def __init__(
        self, redis: Redis, user: User, settings: Settings, *, undo: Callable[[], Awaitable[None]]
    ) -> None:
        self.redis = redis
        self.user = user
        self.settings = settings
        self.undo = undo
        self.day: date | None = None
        self.kept = False

    def keep(self) -> None:
        """The picture is saved: nothing after this undoes it or gives the slot back."""
        self.kept = True

    async def __aenter__(self) -> _ReservedQuota:
        self.day = await counters.reserve("image_generation", self.redis, self.user, self.settings)
        if not self.day:
            raise ImageGenerationError(
                counters.limit_message("image_generation", self.user),
                status_code=429,
                code="daily_limit",
                feature="image_generation",
            )
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object
    ) -> None:
        if exc is None or self.kept:
            return
        await self.undo()
        if not (isinstance(exc, ImageGenerationError) and exc.status_code in _SLOT_KEPT_ON_STATUS):
            await counters.refund("image_generation", self.redis, self.user.id, day=self.day)


class _WrittenBytes:
    """Storage objects this turn wrote, deleted in write order if the turn fails."""

    def __init__(self, gateway: StorageGateway) -> None:
        self.gateway = gateway
        self.keys: list[str] = []

    async def write(self, storage_key: str, data: bytes) -> None:
        await self.gateway.write_bytes(storage_key, data)
        self.keys.append(storage_key)

    async def delete_all(self) -> None:
        for key in self.keys:
            await _rollback_written_bytes(self.gateway, key)


@dataclass(frozen=True)
class _StoredImage:
    """The generated image in storage, and the reference copies written beside it."""

    image: StoredImage
    reference_copies: list[ReferenceCopy]


async def _generate_and_store(
    settings: Settings,
    written: _WrittenBytes,
    *,
    user_id: UUID,
    prompt: str,
    aspect_ratio: str | None,
    references: list[tuple[Attachment, bytes]],
    copy_references: bool,
) -> _StoredImage:
    """Call the provider, check the image, and write it (and reference copies) to storage."""
    # Provider HTTP — no DB session held.
    try:
        generated = await generate_image(
            settings,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            reference_images=[(raw, row.content_type) for row, raw in references] or None,
        )
    except asyncio.CancelledError:
        # Cancelled mid-call, the provider may still finish and bill it: the global spend
        # cap is a safety limit, so it counts the call. The user's day does not.
        await finish_despite_cancel(_record_spend(get_redis_client()))
        raise
    except image_gateway.ImageContentBlockedError as exc:
        raise ImageGenerationError(
            "That picture can't be made: it breaks the image service's content rules.",
            status_code=422,
            code="content_blocked",
            feature="image_generation",
        ) from exc
    image_bytes, content_type = _checked_image(generated)

    presigned = await written.gateway.presign_upload(
        user_id=str(user_id), content_type=content_type, size_bytes=len(image_bytes)
    )
    attachment_id = UUID(presigned.attachment_id)
    await written.write(presigned.storage_key, image_bytes)

    reference_copies: list[ReferenceCopy] = []
    if copy_references:
        for source, raw in references:
            ref_id = uuid4()
            ref_key = f"{user_id}/{ref_id}"
            await written.write(ref_key, raw)
            reference_copies.append(ReferenceCopy(source, ref_id, ref_key))
    image = StoredImage(attachment_id, presigned.storage_key, content_type, len(image_bytes))
    return _StoredImage(image, reference_copies)


async def _record_spend(redis: Redis) -> None:
    """One picture toward the global daily spend cap; a failure is logged, not raised."""
    try:
        await quota_service.record_global_spend(redis, quota_service.IMAGE_GEN_SPEND_USD)
    except Exception:
        logger.exception("record_global_spend failed after image generation")


def _checked_image(generated: tuple[bytes, str] | None) -> tuple[bytes, str]:
    """The provider's bytes and normalized type; 502 when they are not a usable image."""
    if not generated:
        raise ImageGenerationError("Could not generate image", status_code=502)
    image_bytes, content_type = generated
    content_type = normalize_content_type(content_type)
    # The last check on size, as every upload gets at presign and on its bytes
    # (modules/attachments/upload.py). The gateway already rejects an oversized
    # response; this keeps the invariant here rather than trusting it upstream.
    if len(image_bytes) > MAX_ATTACHMENT_SIZE:
        raise ImageGenerationError(
            "Generated image exceeds the maximum allowed size",
            status_code=502,
        )
    if not is_image_content_type(content_type):
        raise ImageGenerationError("Generated file is not an image", status_code=502)
    if not bytes_match_claimed(content_type, image_bytes):
        raise ImageGenerationError("Generated image failed validation", status_code=502)
    return image_bytes, content_type


async def _persist_turn(
    stored: _StoredImage,
    *,
    user_id: UUID,
    chat_id: UUID,
    prompt: str,
    user_message_content: str | None,
    create_user_message: bool,
) -> tuple[Message, Message, int]:
    """Save the user turn (or reuse the last one), the reply and its image in one commit.

    Returns the two messages and how many the chat held before this turn.
    """
    async with SessionLocal() as session:
        prior_count = await history.message_count(session, chat_id)
        if create_user_message:
            user_message = await _create_user_message(
                session,
                user_id=user_id,
                chat_id=chat_id,
                prompt=prompt,
                user_message_content=user_message_content,
                reference_copies=stored.reference_copies,
            )
        else:
            existing = await history.last_user_message(session, chat_id)
            if existing is None:
                raise ImageGenerationError("No user message to attach image to", status_code=404)
            user_message = existing
        assistant_message = await turn_record.add_turn_message(
            session,
            chat_id=chat_id,
            user_id=user_id,
            role="assistant",
            content=image_marker(stored.image.attachment_id),
            model=get_model(_IMAGE_MODEL_ALIAS).id,
        )
        await attachments_service.add_server_images(
            session,
            user_id=user_id,
            images=[stored.image],
            source="generated",
            label=prompt,
            message_id=assistant_message.id,
        )
        # Persist the turn and its reference copies atomically. If a write fails,
        # session close rolls back rows before byte cleanup.
        await session.commit()
    return user_message, assistant_message, prior_count


async def _create_user_message(
    session: AsyncSession,
    *,
    user_id: UUID,
    chat_id: UUID,
    prompt: str,
    user_message_content: str | None,
    reference_copies: list[ReferenceCopy],
) -> Message:
    """The user's bubble, with hidden copies of its reference images on it."""
    bubble = (user_message_content or f"{_USER_MESSAGE_PREFIX}{prompt}").strip()
    if not bubble:
        bubble = f"{_USER_MESSAGE_PREFIX}{prompt}"
    # "Black" after a cat picture edits the picture right above; repeating it
    # in the user's bubble only shows it twice. A photo the user attached
    # stays in their bubble.
    in_chat = await shown_in_chat(session, chat_id, [copy.source for copy in reference_copies])
    for copy in reference_copies:
        if copy.source.id not in in_chat:
            bubble += f"\n{image_marker(copy.attachment_id)}"
    user_message = await turn_record.add_turn_message(
        session, chat_id=chat_id, user_id=user_id, role="user", content=bubble
    )
    # Independent hidden copies keep an edit/regenerate usable if its original
    # Library item or earlier image is later deleted. They are on the user row
    # either way, so regenerate finds them without a marker in the text.
    if reference_copies:
        await attachments_service.add_reference_copies(
            session, message_id=user_message.id, copies=reference_copies
        )
    return user_message


async def load_reference_images(
    gateway: StorageGateway, *, user_id: UUID, attachment_ids: list[UUID]
) -> list[tuple[Attachment, bytes]]:
    """Resolve only owned, bounded image bytes; never fetch client-supplied URLs."""
    ids = list(dict.fromkeys(attachment_ids))
    if len(ids) > 2:
        raise ImageGenerationError("Use at most two reference images", status_code=400)
    if not ids:
        return []
    async with SessionLocal() as session:
        rows = await attachments_service.get_by_ids(session, ids, user_id)
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        raise ImageGenerationError("Reference image not found", status_code=404)
    result = []
    for ref_id in ids:
        row = by_id[ref_id]
        if not is_image_content_type(row.content_type):
            raise ImageGenerationError("Reference must be an image", status_code=400)
        raw = await gateway.read_bytes(row.storage_key)
        if (
            not raw
            or len(raw) > MAX_ATTACHMENT_SIZE
            or not bytes_match_claimed(row.content_type, raw)
        ):
            raise ImageGenerationError("Reference image is unavailable or invalid", status_code=400)
        result.append((row, raw))
    return result
