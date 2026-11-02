"""A scanned PDF's vision OCR takes one of its owner's daily image-upload slots.

A PDF with no text layer is read page by page with vision (up to
``ATTACHMENT_OCR_INDEX_MAX_PAGES`` calls), so it costs like a stack of photos,
but a PDF upload took no daily slot: one user could have the index job OCR
any number of them and spend the global cap for everyone. The index job now
takes one ``image_upload`` slot (``DAILY_IMAGE_LIMIT*``) before it may OCR.
At the cap the file stays attached and its text layer, if any, is still read;
a scanned one is just not searchable that day. A PDF that turns out to have a
text layer gets its slot back; one whose OCR found nothing keeps it spent,
since its vision calls already ran.

One file takes one slot however often its index job runs: the slot is recorded
per attachment (``SET NX``), so a retry after an embedding or storage failure
reuses it instead of charging again, and a run that fails before OCR could run
gives it back. Text OCR produced is kept briefly, so that retry does not pay
for the same vision calls twice.
"""

from __future__ import annotations

import base64
import json
import logging
import zlib
from datetime import date
from uuid import UUID

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.modules.attachments.text_extract import ExtractedText
from app.repositories import users as users_repo
from app.services.quota import counters

logger = logging.getLogger(__name__)

_OCR_CONTENT_TYPE = "application/pdf"
# Outlives the daily counter, so a late retry never charges a second slot.
_SLOT_TTL_SECONDS = counters.DAILY_TTL
# Long enough for the worker's in-process retries and a dead-letter replay soon after.
_TEXT_TTL_SECONDS = 60 * 60


def _slot_key(attachment_id: UUID) -> str:
    return f"recall:attachment_ocr_slot:{attachment_id}"


def _text_key(attachment_id: UUID) -> str:
    return f"recall:attachment_ocr_text:{attachment_id}"


def _as_day(raw: object) -> date | None:
    text = raw.decode() if isinstance(raw, bytes) else raw
    try:
        return date.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None


async def reserve_ocr(
    settings: Settings, user_id: UUID, content_type: str, attachment_id: UUID
) -> date | None:
    """The UTC day this file's slot came from, or None: OCR is off, not a PDF, or at the cap."""
    if content_type != _OCR_CONTENT_TYPE or not settings.attachment_ocr_enabled:
        return None
    redis = get_redis_client()
    held = _as_day(await redis.get(_slot_key(attachment_id)))
    if held is not None:
        return held
    async with SessionLocal() as session:
        user = await users_repo.get_by_id(session, user_id)
    if user is None:
        return None
    day = await counters.reserve("image_upload", redis, user, settings)
    if day is None:
        logger.info("Scanned-PDF OCR skipped at the daily image limit user_id=%s", user_id)
        return None
    if await redis.set(_slot_key(attachment_id), day.isoformat(), nx=True, ex=_SLOT_TTL_SECONDS):
        return day
    # A concurrent run of the same file recorded its slot first: use that one.
    await counters.refund("image_upload", redis, user_id, day=day)
    return _as_day(await redis.get(_slot_key(attachment_id)))


async def refund_ocr(user_id: UUID, attachment_id: UUID, day: date | None) -> None:
    """Give this file's slot back: no vision call ran for it."""
    if day is None:
        return
    redis = get_redis_client()
    if await redis.delete(_slot_key(attachment_id)):
        await counters.refund("image_upload", redis, user_id, day=day)


async def release_unused_ocr(
    user_id: UUID, attachment_id: UUID, day: date | None, details: ExtractedText | None
) -> None:
    """Give the slot back when the PDF was read from its text layer (no vision call)."""
    if details is not None and not details.via_ocr:
        await refund_ocr(user_id, attachment_id, day)


async def remember_ocr_text(attachment_id: UUID, details: ExtractedText) -> None:
    """Keep OCR'd text for a retry of the same index job. Best-effort."""
    if not details.via_ocr or not details.text:
        return
    fields = {
        "text": details.text,
        "char_capped": details.char_capped,
        "page_capped": details.page_capped,
    }
    packed = base64.b64encode(zlib.compress(json.dumps(fields).encode())).decode("ascii")
    try:
        await get_redis_client().set(_text_key(attachment_id), packed, ex=_TEXT_TTL_SECONDS)
    except Exception:
        logger.warning("Could not keep OCR text attachment_id=%s", attachment_id, exc_info=True)


async def recall_ocr_text(attachment_id: UUID) -> ExtractedText | None:
    """OCR'd text an earlier run of this index job kept, if any."""
    try:
        packed = await get_redis_client().get(_text_key(attachment_id))
        if not isinstance(packed, str) or not packed:
            return None
        fields = json.loads(zlib.decompress(base64.b64decode(packed)))
        return ExtractedText(
            text=str(fields["text"]),
            char_capped=bool(fields.get("char_capped")),
            page_capped=bool(fields.get("page_capped")),
            via_ocr=True,
        )
    except Exception:
        logger.warning("Kept OCR text unreadable attachment_id=%s", attachment_id, exc_info=True)
        return None
