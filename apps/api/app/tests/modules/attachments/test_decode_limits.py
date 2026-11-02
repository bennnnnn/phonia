"""A small upload cannot make the server decode a huge bitmap.

* PDF OCR rendered every page at ``attachment_ocr_render_scale`` whatever its
  size: a 435-byte PDF with one 14400x14400 pt page drove peak RSS to about
  5.1 GB in a local proof (the app machine has 512 MB).
* Gallery thumbnails (``GET /attachments/{id}/file?w=``) decoded the whole
  image on the event loop: a 505 KiB 13000x13000 PNG added about 650 MB RSS
  and blocked the loop for 1.4s. Pillow only warns below ~179 MP.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.core.config import Settings
from app.modules.attachments import ocr, pdf_render
from app.modules.attachments.image_decode import ImageTooLargeError
from app.modules.attachments.thumbnails import resize_image_bytes


def _pdf_with_page(width_pt: int, height_pt: int) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width_pt, height=height_pt)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.parametrize(
    "width_pt, height_pt, scale, max_pixels, expected_size",
    [
        # A letter page at the default scale is untouched.
        (612, 792, 1.5, 4_000_000, (918, 1188)),
        # An oversized page is scaled down to the pixel budget.
        (2000, 2000, 1.5, 1_000_000, (1000, 1000)),
        (4000, 1000, 1.5, 1_000_000, (2000, 500)),
    ],
)
def test_pdf_page_render_respects_the_pixel_budget(
    width_pt: int,
    height_pt: int,
    scale: float,
    max_pixels: int,
    expected_size: tuple[int, int],
) -> None:
    pages, total = ocr.render_pdf_pages_and_count(
        _pdf_with_page(width_pt, height_pt),
        max_pages=1,
        scale=scale,
        max_pixels=max_pixels,
    )
    assert total == 1
    rendered = Image.open(io.BytesIO(pages[0][1]))
    width, height = rendered.size
    assert width * height <= max_pixels * 1.01
    assert abs(width - expected_size[0]) <= 2
    assert abs(height - expected_size[1]) <= 2


async def test_ocr_passes_the_configured_pixel_budget() -> None:
    settings = Settings(attachment_ocr_max_page_pixels=123_456, mock_llm_enabled=False)
    seen: dict[str, Any] = {}

    def fake_render(_data: bytes, **kwargs: Any) -> tuple[list[tuple[str, bytes]], int]:
        seen.update(kwargs)
        return [], 0

    with patch.object(pdf_render, "render_pdf_pages_and_count", fake_render):
        await ocr.ocr_scanned_pdf(settings, b"%PDF-1.4")
    assert seen["max_pixels"] == 123_456


def _image(fmt: str, side: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (side, side), (250, 250, 250)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize(
    "fmt, side, max_pixels, refused",
    [
        ("PNG", 600, 1_000_000, False),
        # Lossless formats decode in full: refuse past the budget.
        ("PNG", 2000, 1_000_000, True),
        ("WEBP", 2000, 1_000_000, True),
        # JPEG decodes at a reduced scale (draft), so a big photo is fine.
        ("JPEG", 4000, 1_000_000, False),
        # 0 disables the budget.
        ("PNG", 2000, 0, False),
    ],
)
def test_thumbnail_refuses_images_that_decode_past_the_budget(
    fmt: str, side: int, max_pixels: int, refused: bool
) -> None:
    data = _image(fmt, side)
    if refused:
        with pytest.raises(ImageTooLargeError):
            resize_image_bytes(data, 256, max_pixels=max_pixels)
        return
    thumb, _content_type = resize_image_bytes(data, 256, max_pixels=max_pixels)
    assert max(Image.open(io.BytesIO(thumb)).size) <= 256


async def test_thumbnail_decode_runs_off_the_event_loop() -> None:
    from app.modules.attachments import thumbnails, workflow

    row = MagicMock(content_type="image/png", storage_key="u/k")
    gateway = MagicMock()
    original = _image("PNG", 64)
    gateway.read_bytes = AsyncMock(side_effect=lambda key: original if key == "u/k" else None)
    gateway.write_bytes = AsyncMock()
    calls: list[tuple[str, str]] = []
    real_run_blocking = thumbnails.run_blocking

    async def spy(kind: Any, func: Any, /, *args: Any, **kwargs: Any) -> Any:
        calls.append((kind, func.__name__))
        return await real_run_blocking(kind, func, *args, **kwargs)

    with (
        patch.object(workflow, "_verified_row", AsyncMock(return_value=(row, gateway))),
        patch.object(thumbnails, "run_blocking", spy),
    ):
        access = await workflow.get_file_access(
            MagicMock(), Settings(), MagicMock(), uuid4(), width=128
        )
    assert ("images", "resize_image_bytes") in calls
    assert access.body
