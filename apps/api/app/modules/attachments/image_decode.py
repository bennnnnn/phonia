"""Decode an uploaded image once, bounded and upright, for thumbnails and vision.

CPU-bound: call from a worker thread. The header is read first; a JPEG is set to
decode at a reduced scale, then anything that would still decode past
``max_pixels`` is refused. A sub-MB PNG can declare 13000x13000 (Pillow only
warns below ~179 MP). The EXIF orientation is applied, so a phone photo taken
in portrait is not shown or read sideways. A GIF gives its first frame.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

# Matches Settings.attachment_image_max_decode_pixels for direct callers.
DEFAULT_IMAGE_MAX_DECODE_PIXELS = 16_000_000


class ImageTooLargeError(ValueError):
    """The image would decode to more pixels than the budget allows."""


def decode_upright(data: bytes, edge: int, *, max_pixels: int) -> PILImage:
    """The image loaded at no more than ~2x ``edge`` (JPEG draft), EXIF-rotated.

    The caller still shrinks it to ``edge``; ``max_pixels`` of 0 disables the guard.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as opened:
        if opened.format == "JPEG":
            opened.draft("RGB", (edge, edge))
        width, height = opened.size
        if max_pixels > 0 and width * height > max_pixels:
            raise ImageTooLargeError(f"image decodes to {width}x{height}")
        opened.load()
        # exif_transpose returns a new image (or a copy), detached from the file.
        return ImageOps.exif_transpose(opened)


def has_transparency(image: PILImage) -> bool:
    """True when some pixel is not fully opaque (JPEG would paint it black)."""
    if image.mode in ("RGBA", "LA", "PA"):
        # One band: (min, max) of the alpha channel.
        low = image.getchannel("A").getextrema()[0]
        return isinstance(low, int | float) and low < 255
    return image.mode == "P" and "transparency" in image.info
