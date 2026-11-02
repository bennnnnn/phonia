"""Read a photographed problem back as plain text, with a subject's prompt.

This is not the math scanner: it does not call Mathpix and it asks for no
equation kinds. Chemistry and physics confirm the text with the student, and
the chat then solves that text like a typed question.
"""

from __future__ import annotations

import base64
import logging

from app.core.config import Settings
from app.gateways import litellm_gateway, mock_llm
from app.gateways.model_output import parse_model_json, unwrap_model_fence
from app.models.model_catalog import vision_alias

logger = logging.getLogger(__name__)

MAX_READING = 2000
_MATH_KINDS = frozenset({"equation", "system", "inequality"})


def reading_from_vision(raw: str) -> str:
    """Plain problem text. A math-kind JSON object is not a reading."""
    text = unwrap_model_fence(raw, "json")
    if text.startswith("{") and text.endswith("}"):
        try:
            data = parse_model_json(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            kind = data.get("kind")
            if "lhs" in data or (isinstance(kind, str) and kind in _MATH_KINDS):
                return ""
            for key in ("problem", "text", "reading"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    text = value.strip()
                    break
            else:
                return ""
    if len(text) > MAX_READING:
        text = text[:MAX_READING].rstrip()
    return text


async def read_problem_text(
    settings: Settings,
    *,
    prompt: str,
    content_type: str,
    data: bytes,
    mock_reading: str,
    timeout_seconds: float | None = None,
) -> str:
    """The written problem, or empty when the page cannot be read.

    ``timeout_seconds`` (default ``math_image_extract_timeout_seconds``) is
    the whole read's budget, the backup vision model included.
    """
    if not data:
        return ""
    if mock_llm.should_mock_llm(settings):
        return mock_reading
    try:
        mime = content_type.split(";")[0].strip() or "image/jpeg"
        encoded = base64.standard_b64encode(data).decode("ascii")
        response = await litellm_gateway.vision_completion(
            settings=settings,
            model_alias=vision_alias(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            max_tokens=512,
            timeout_seconds=(
                settings.math_image_extract_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            ),
        )
    except Exception:
        logger.warning("scan text read failed", exc_info=True)
        return ""
    if response is None:
        return ""
    try:
        raw = response.choices[0].message.content or ""
    except Exception:
        logger.warning("scan text read had no text", exc_info=True)
        return ""
    return reading_from_vision(raw)
