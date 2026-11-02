"""Vision OCR for image-only PDFs — same extract path as text-layer PDFs."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.core.document_executor import run_document
from app.gateways import litellm_gateway, mock_llm
from app.gateways.model_output import unwrap_model_fence
from app.models.model_catalog import vision_alias
from app.modules.attachments.pdf_render import render_in_worker

# Re-exported: callers and tests render through this module.
from app.modules.attachments.pdf_render import (
    render_pdf_pages_and_count as render_pdf_pages_and_count,
)
from app.modules.attachments.text_extract import MAX_EXTRACT_CHARS, ExtractedText

logger = logging.getLogger(__name__)

_OCR_PROMPT = (
    "Transcribe all readable text from this PDF page. "
    "Preserve headings, lists, and paragraph breaks. "
    "If the page is blank or has no text, reply with exactly [empty]. "
    "Do not describe the layout — transcribe only."
)

_OCR_CONCURRENCY = 2


def _page_text_from_response(response: Any) -> str | None:
    try:
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        return None
    raw = unwrap_model_fence(raw, "text")
    lowered = raw.lower()
    if not raw or lowered in {"[empty]", "empty", "(empty)"}:
        return None
    return raw


async def _ocr_one_page(
    settings: Settings,
    mime: str,
    image: bytes,
) -> str | None:
    encoded = base64.standard_b64encode(image).decode("ascii")
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _OCR_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                },
            ],
        }
    ]
    response = await litellm_gateway.vision_completion(
        settings=settings,
        model_alias=vision_alias(),
        messages=messages,
        max_tokens=2048,
        timeout_seconds=settings.attachment_ocr_page_timeout_seconds,
    )
    if response is None:
        return None
    return _page_text_from_response(response)


async def ocr_scanned_pdf(
    settings: Settings,
    data: bytes,
    *,
    max_chars: int | None = None,
    max_pages: int | None = None,
) -> ExtractedText | None:
    """Best-effort page OCR — never raises into the chat or index path."""
    if not data or not settings.attachment_ocr_enabled:
        return None
    if mock_llm.should_mock_llm(settings):
        return None
    chars = MAX_EXTRACT_CHARS if max_chars is None else max_chars
    pages_limit = settings.attachment_ocr_max_pages if max_pages is None else max_pages
    timeout = settings.attachment_ocr_timeout_seconds
    if pages_limit > settings.attachment_ocr_max_pages:
        timeout = max(timeout, settings.attachment_ocr_index_timeout_seconds)
    try:
        async with asyncio.timeout(timeout):
            # In a document worker, killed at the timeout: a render thread outlived it.
            pages, total_pages = await run_document(
                render_in_worker,
                data,
                pages_limit,
                settings.attachment_ocr_render_scale,
                settings.attachment_ocr_max_page_pixels,
                timeout=timeout,
            )
            if not pages:
                return None
            sem = asyncio.Semaphore(_OCR_CONCURRENCY)

            async def _one(item: tuple[str, bytes]) -> str | None:
                async with sem:
                    return await _ocr_one_page(settings, item[0], item[1])

            texts = await gather_or_cancel(*(_one(page) for page in pages))
    except TimeoutError:
        logger.warning("Scanned-PDF OCR timed out")
        return None
    except Exception:
        logger.warning("Scanned-PDF OCR failed", exc_info=True)
        return None

    parts = [text.strip() for text in texts if text and text.strip()]
    joined = "\n\n".join(parts).strip()
    if not joined:
        return None
    return ExtractedText(
        text=joined[:chars],
        char_capped=len(joined) > chars,
        page_capped=total_pages > pages_limit,
        via_ocr=True,
    )
