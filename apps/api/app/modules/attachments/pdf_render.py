"""A PDF's pages as images, for vision OCR: what a document worker runs.

Sync and CPU-bound (pypdfium2, Pillow). Split from ``ocr`` so a worker imports only the
renderers, not the model client.
"""

from __future__ import annotations

import io
import logging
import math

logger = logging.getLogger(__name__)

_JPEG_QUALITY = 70


# Matches Settings.attachment_ocr_max_page_pixels for direct callers.
DEFAULT_MAX_PAGE_PIXELS = 4_000_000


def render_pdf_pages_and_count(
    data: bytes,
    *,
    max_pages: int,
    scale: float,
    max_pixels: int = DEFAULT_MAX_PAGE_PIXELS,
) -> tuple[list[tuple[str, bytes]], int]:
    """Render pages and the document's page count (0 if unknown). Never raises."""
    try:
        rendered, total = _render_with_pdfium(
            data, max_pages=max_pages, scale=scale, max_pixels=max_pixels
        )
        if rendered:
            return rendered, total
    except Exception:
        logger.warning("PDF page render failed; trying embedded images", exc_info=True)
    try:
        return _embedded_page_images(data, max_pages=max_pages)
    except Exception:
        logger.warning("PDF embedded-image extract failed", exc_info=True)
        return [], 0


def _page_scale(width_pt: float, height_pt: float, scale: float, max_pixels: int) -> float:
    """``scale``, reduced so the rendered page stays within ``max_pixels``.

    The page size comes from the (untrusted) PDF, so a tiny file can declare
    a page that renders to gigabytes at a fixed scale.
    """
    area = width_pt * height_pt
    if max_pixels <= 0 or area <= 0:
        return scale
    if area * scale * scale <= max_pixels:
        return scale
    return math.sqrt(max_pixels / area)


def _render_with_pdfium(
    data: bytes,
    *,
    max_pages: int,
    scale: float,
    max_pixels: int = DEFAULT_MAX_PAGE_PIXELS,
) -> tuple[list[tuple[str, bytes]], int]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    out: list[tuple[str, bytes]] = []
    try:
        total = len(pdf)
        page_count = min(total, max_pages)
        for index in range(page_count):
            page = pdf[index]
            width_pt, height_pt = page.get_size()
            bitmap = page.render(scale=_page_scale(width_pt, height_pt, scale, max_pixels))
            try:
                image = bitmap.to_pil().convert("RGB")
                buf = io.BytesIO()
                image.save(buf, format="JPEG", quality=_JPEG_QUALITY)
                out.append(("image/jpeg", buf.getvalue()))
            finally:
                bitmap.close()
                page.close()
    finally:
        pdf.close()
    return out, total


def _embedded_page_images(data: bytes, *, max_pages: int) -> tuple[list[tuple[str, bytes]], int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    out: list[tuple[str, bytes]] = []
    for page in reader.pages[:max_pages]:
        for img in getattr(page, "images", None) or []:
            raw = getattr(img, "data", None)
            if not raw:
                continue
            mime = _image_mime(raw, str(getattr(img, "name", "") or ""))
            out.append((mime, raw))
            if len(out) >= max_pages:
                return out, total
    return out, total


def _image_mime(raw: bytes, name: str) -> str:
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    lowered = name.lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def render_in_worker(
    data: bytes, max_pages: int, scale: float, max_pixels: int
) -> tuple[list[tuple[str, bytes]], int]:
    """``render_pdf_pages_and_count`` with positional arguments, as a pool job takes them."""
    return render_pdf_pages_and_count(data, max_pages=max_pages, scale=scale, max_pixels=max_pixels)
