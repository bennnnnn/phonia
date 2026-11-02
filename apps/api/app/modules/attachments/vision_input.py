"""Photos as a vision model receives them, inside the turn's last user message.

The text part is the prompt's own user message with its image markers taken out,
so a document excerpt sent beside a photo (or a file in a later turn that rereads
an earlier photo) is not lost; only words that exist just in what the model is
asked (camera maths' ``Solve:`` line) are added after it.

A phone photo can be 10 MB and a send can carry ten: sent as they were, the
base64 copies and the request body held about 370 MB on a 1 GB machine. Each
photo is decoded once on a worker thread (with the gallery's pixel guard), turned
upright, shrunk to ``attachment_vision_max_edge`` and re-encoded: JPEG, or PNG
when it has transparent pixels (JPEG would paint them black; every provider
takes PNG). The raw bytes are let go as soon as their photo is encoded. The
encoded total is capped per turn by ``attachment_vision_max_turn_bytes``; a photo
past it, or one that cannot be decoded, is left out and the model is told.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from app.core.blocking import run_blocking
from app.core.config import Settings
from app.gateways.storage_gateway import StorageGateway
from app.modules.attachments.image_decode import decode_upright, has_transparency
from app.modules.attachments.markers import _strip_image_markers
from app.modules.attachments.vision_notes import PHOTOS_LEFT_OUT_NOTE, VISION_NOTE
from app.services.prompt_safety import content_has_attachment_marker, text_before_attachment_markers

logger = logging.getLogger(__name__)

_DEFAULT_QUESTION = "What's in this image?"
_JPEG_QUALITY = 85
_FILE_MARKERS = ("[File:", "[File attached:", "[File (")


def vision_prompt_text(existing: Any, caption: str) -> str:
    """The text part of a vision message built from the prompt's user message.

    ``existing`` is that message's content as the prompt built it (file excerpts
    already wrapped as untrusted data); ``caption`` is what the model is asked
    this turn. Image markers go: the photos themselves follow the text.
    """
    asked = caption.strip()
    if not isinstance(existing, str):
        return _strip_image_markers(asked) or _DEFAULT_QUESTION
    prose = text_before_attachment_markers(existing).strip()
    if any(marker in existing for marker in _FILE_MARKERS):
        body = _strip_image_markers(existing)
    else:
        # Photos only: the wrapped attachment block would be an empty frame.
        body = prose if content_has_attachment_marker(existing) else existing.strip()
    extra = ""
    if asked and asked not in existing:
        extra = asked[len(prose) :].strip() if prose and asked.startswith(prose) else asked
    text = f"{body}\n\n{extra}".strip() if extra else body
    return text or _DEFAULT_QUESTION


def encode_for_vision(data: bytes, *, max_edge: int, max_pixels: int) -> tuple[str, bytes]:
    """(mime, encoded bytes) of one photo, upright and at most ``max_edge`` on its long side.

    CPU-bound: call it from a worker thread. Raises when the bytes do not decode.
    """
    image = decode_upright(data, max_edge, max_pixels=max_pixels)
    try:
        image.thumbnail((max_edge, max_edge))
        out = io.BytesIO()
        if has_transparency(image):
            image.convert("RGBA").save(out, format="PNG", optimize=True)
            return "image/png", out.getvalue()
        image.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return "image/jpeg", out.getvalue()
    finally:
        image.close()


async def _image_parts(
    gateway: StorageGateway,
    images: list[tuple[str, str]],
    bytes_by_key: dict[str, bytes] | None,
    settings: Settings,
) -> tuple[list[dict[str, Any]], int]:
    """The encoded image parts in order, and how many photos were left out."""
    parts: list[dict[str, Any]] = []
    left_out = 0
    budget = settings.attachment_vision_max_turn_bytes
    for _content_type, storage_key in images:
        # Pop: the turn has no later use for the raw bytes once encoded.
        data = bytes_by_key.pop(storage_key, None) if bytes_by_key is not None else None
        if data is None:
            data = await gateway.read_bytes(storage_key)
        if not data:
            left_out += 1
            continue
        try:
            mime, encoded = await run_blocking(
                "images",
                encode_for_vision,
                data,
                max_edge=settings.attachment_vision_max_edge,
                max_pixels=settings.attachment_image_max_decode_pixels,
            )
        except Exception:
            logger.warning("Vision image could not be decoded storage_key=%s", storage_key)
            left_out += 1
            continue
        finally:
            del data
        url = f"data:{mime};base64,{base64.standard_b64encode(encoded).decode('ascii')}"
        if budget > 0 and len(url) > budget:
            left_out += 1
            continue
        budget -= len(url)
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts, left_out


async def inject_vision_content(
    prompt_messages: list[dict[str, Any]],
    gateway: StorageGateway,
    images: list[tuple[str, str]],
    *,
    settings: Settings,
    caption: str = "",
    bytes_by_key: dict[str, bytes] | None = None,
    at_index: int | None = None,
) -> bool:
    """Replace a user turn (the last, or ``at_index``) with multimodal content.

    Prefer *bytes_by_key* (turn-prep verify cache) over re-downloading; its
    entries are removed once encoded. Returns True when at least one image part
    was injected.
    """
    user_turns = [i for i, message in enumerate(prompt_messages) if message.get("role") == "user"]
    index = at_index if at_index in user_turns else (user_turns[-1] if user_turns else None)
    if index is None:
        return False
    image_parts, left_out = await _image_parts(gateway, images, bytes_by_key, settings)
    if not image_parts:
        return False
    text = vision_prompt_text(prompt_messages[index].get("content"), caption)
    notes = f"{VISION_NOTE} {PHOTOS_LEFT_OUT_NOTE}" if left_out else VISION_NOTE
    prompt_messages[index] = {
        "role": "user",
        "content": [{"type": "text", "text": f"{text}\n\n{notes}"}, *image_parts],
    }
    return True
