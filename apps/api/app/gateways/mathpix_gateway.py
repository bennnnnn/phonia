"""Mathpix ``v3/text`` OCR — server-side only, never from the mobile app.

Student homework photos always send ``metadata.improve_mathpix = false`` so
the image is not persisted for Mathpix QA. Failures return None; callers
fall back to vision-chat.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

MATHPIX_OCR_URL = "https://api.mathpix.com/v3/text"


@dataclass(frozen=True)
class MathpixOcrResult:
    text: str
    latex: str
    confidence: float | None


def is_configured(settings: Settings) -> bool:
    return bool(
        settings.mathpix_enabled
        and settings.mathpix_app_id.strip()
        and settings.mathpix_app_key.strip()
    )


def _as_confidence(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _as_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


async def ocr_image(
    settings: Settings,
    *,
    content_type: str,
    data: bytes,
) -> MathpixOcrResult | None:
    """Best-effort math transcription. Never raises into the chat path."""
    if not data or not is_configured(settings):
        return None
    mime = content_type.split(";")[0].strip() or "image/jpeg"
    encoded = base64.standard_b64encode(data).decode("ascii")
    payload = {
        "src": f"data:{mime};base64,{encoded}",
        "formats": ["text", "latex_styled"],
        "metadata": {"improve_mathpix": False},
    }
    timeout = max(1.0, settings.mathpix_timeout_seconds)
    try:
        client = get_pooled_client(timeout)
        response = await client.post(
            MATHPIX_OCR_URL,
            json=payload,
            headers={
                "app_id": settings.mathpix_app_id.strip(),
                "app_key": settings.mathpix_app_key.strip(),
            },
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        logger.warning("mathpix ocr failed", exc_info=True)
        return None
    if not isinstance(body, dict):
        return None
    if body.get("error"):
        logger.warning("mathpix ocr error: %s", body.get("error"))
        return None
    text = _as_text(body.get("text"))
    latex = _as_text(body.get("latex_styled"))
    if not text and not latex:
        return None
    return MathpixOcrResult(
        text=text or latex,
        latex=latex,
        confidence=_as_confidence(body.get("confidence")),
    )
