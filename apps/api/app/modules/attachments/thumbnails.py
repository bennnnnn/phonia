"""Gallery and chat thumbnails (``GET /attachments/{id}/file?w=``).

Every ``?w=`` request used to download the whole object and decode it on the
default thread pool, so a Library page of 30 tiles meant 30 full downloads and
decodes at once. A width now rounds up to one of a few sizes; each size is made
once, kept beside the original under ``{storage_key}.thumbs/`` and read from there
afterwards. Making one waits on a process-wide limit
(``attachment_thumbnail_concurrency``). The caller checks ownership first.
"""

from __future__ import annotations

import asyncio
import io
import logging
import weakref

from app.core.blocking import run_blocking
from app.core.config import Settings
from app.gateways.storage_gateway import StorageGateway
from app.modules.attachments.image_decode import (
    DEFAULT_IMAGE_MAX_DECODE_PIXELS,
    decode_upright,
)

logger = logging.getLogger(__name__)

GALLERY_THUMB_MIN_EDGE = 32
GALLERY_THUMB_MAX_EDGE = 512
# The sizes a request rounds up to: the phone asks for 2x its layout width, so
# without a ladder every device and column count would make its own copy.
THUMB_EDGES = (64, 128, 256, 384, GALLERY_THUMB_MAX_EDGE)
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# One limiter per event loop and limit: an asyncio primitive belongs to one loop.
_limiters: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[int, asyncio.Semaphore]] = (
    weakref.WeakKeyDictionary()
)


def resize_image_bytes(
    data: bytes,
    edge: int,
    *,
    max_pixels: int = DEFAULT_IMAGE_MAX_DECODE_PIXELS,
) -> tuple[bytes, str]:
    """Downscale an image for gallery tiles. Returns (bytes, content_type).

    CPU-bound: call it from a worker thread (``decode_upright`` has the guards).
    """
    size = max(GALLERY_THUMB_MIN_EDGE, min(GALLERY_THUMB_MAX_EDGE, edge))
    image = decode_upright(data, size, max_pixels=max_pixels)
    try:
        image.thumbnail((size, size))
        out = io.BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
        converted = image.convert("RGB") if image.mode != "RGB" else image
        converted.save(out, format="JPEG", quality=80, optimize=True)
        return out.getvalue(), "image/jpeg"
    finally:
        image.close()


def thumbnail_edge(width: int | None) -> int | None:
    """The stored size serving a ``?w=`` request: the smallest one at least as wide."""
    if width is None or width <= 0:
        return None
    wanted = max(GALLERY_THUMB_MIN_EDGE, min(GALLERY_THUMB_MAX_EDGE, width))
    return next(edge for edge in THUMB_EDGES if edge >= wanted)


def thumbnail_prefix(storage_key: str) -> str:
    """Where an object's thumbnails live; deleting the object deletes this prefix."""
    return f"{storage_key}.thumbs/"


def thumbnail_key(storage_key: str, edge: int) -> str:
    return f"{thumbnail_prefix(storage_key)}w{edge}"


def _limiter(settings: Settings) -> asyncio.Semaphore:
    limit = max(1, settings.attachment_thumbnail_concurrency)
    by_limit = _limiters.setdefault(asyncio.get_running_loop(), {})
    limiter = by_limit.get(limit)
    if limiter is None:
        limiter = by_limit[limit] = asyncio.Semaphore(limit)
    return limiter


def _thumbnail_type(body: bytes) -> str:
    return "image/png" if body.startswith(_PNG_MAGIC) else "image/jpeg"


async def thumbnail_bytes(
    gateway: StorageGateway, settings: Settings, storage_key: str, edge: int
) -> tuple[bytes, str] | None:
    """The thumbnail and its type, made and stored on first request; None if the image is gone.

    A failed resize raises (the caller answers 422). Storing the copy is best-effort.
    """
    key = thumbnail_key(storage_key, edge)
    cached = await gateway.read_bytes(key)
    if cached:
        return cached, _thumbnail_type(cached)
    async with _limiter(settings):
        # Another request may have made it while this one waited.
        cached = await gateway.read_bytes(key)
        if cached:
            return cached, _thumbnail_type(cached)
        data = await gateway.read_bytes(storage_key)
        if data is None:
            return None
        body, content_type = await run_blocking(
            "images",
            resize_image_bytes,
            data,
            edge,
            max_pixels=settings.attachment_image_max_decode_pixels,
        )
        del data
    try:
        await gateway.write_bytes(key, body)
    except Exception:
        logger.warning("Thumbnail store failed key=%s", key, exc_info=True)
    return body, content_type


async def delete_thumbnails(gateway: StorageGateway, storage_key: str) -> bool:
    """Best-effort; False when the delete failed (the caller queues a retry)."""
    try:
        await gateway.delete_prefix(thumbnail_prefix(storage_key))
    except Exception:
        logger.warning("Thumbnail delete failed storage_key=%s", storage_key, exc_info=True)
        return False
    return True
