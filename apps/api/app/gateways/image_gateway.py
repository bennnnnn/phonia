"""OpenRouter text-to-image HTTP calls (provider boundary)."""

from __future__ import annotations

import base64
import binascii
import logging

from app.core.attachment_limits import MAX_ATTACHMENT_SIZE
from app.core.config import Settings
from app.gateways import safe_fetch
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

_OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"
_GENERATE_TIMEOUT = 120.0
# The finished picture is a few MB on the provider's CDN; the whole download,
# redirects included, gets this long (each read still has _GENERATE_TIMEOUT).
_RESULT_DOWNLOAD_DEADLINE = 60.0
# How a provider says a prompt broke its content rules (OpenAI's content_policy_violation,
# OpenRouter's moderation "flagged" error); a refusal, not a failure to retry.
_REFUSAL_WORDS = ("content_policy", "content policy", "moderation", "flagged", "safety system")


class ImageContentBlockedError(Exception):
    """The provider refused the prompt under its content rules."""


def _is_content_refusal(status_code: int, body: str) -> bool:
    lowered = body.lower()
    return status_code in (400, 403, 451) and any(word in lowered for word in _REFUSAL_WORDS)


async def generate_via_openrouter(
    settings: Settings,
    *,
    prompt: str,
    model: str,
    aspect_ratio: str | None = None,
    reference_images: list[tuple[bytes, str]] | None = None,
) -> tuple[bytes, str] | None:
    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "output_format": "png",
    }
    if aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio
    if reference_images:
        payload["input_references"] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"},
            }
            for raw, mime in reference_images
        ]

    try:
        response = await get_pooled_client(_GENERATE_TIMEOUT).post(
            _OPENROUTER_IMAGES_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code >= 400:
            logger.warning(
                "OpenRouter image generation failed model=%s status=%s body=%s",
                model,
                response.status_code,
                response.text[:500],
            )
            if _is_content_refusal(response.status_code, response.text):
                raise ImageContentBlockedError(model)
        response.raise_for_status()
        data = response.json()
        items = data.get("data")
        if not isinstance(items, list) or not items:
            logger.warning("OpenRouter image generation returned no data model=%s", model)
            return None
        first = items[0]
        if not isinstance(first, dict):
            return None
        b64_json = first.get("b64_json")
        if isinstance(b64_json, str) and b64_json.strip():
            try:
                raw = base64.b64decode(b64_json, validate=True)
            except (ValueError, binascii.Error):
                logger.warning("OpenRouter image generation returned invalid b64_json")
                return None
            if raw:
                # Every attachment is held to MAX_ATTACHMENT_SIZE, at presign and on its
                # bytes (modules/attachments/upload.py); a generated image is too, or an
                # oversized provider response would reach storage unchecked.
                if len(raw) > MAX_ATTACHMENT_SIZE:
                    logger.warning(
                        "OpenRouter image generation b64_json exceeds size cap model=%s bytes=%s",
                        model,
                        len(raw),
                    )
                    return None
                media_type = first.get("media_type")
                return raw, media_type if isinstance(media_type, str) else "image/png"
        url = first.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return await _download_result(url, model)
        logger.warning("OpenRouter image generation response missing image payload model=%s", model)
        return None
    except ImageContentBlockedError:
        raise
    except Exception:
        logger.exception("Image generation failed model=%s prompt_len=%s", model, len(prompt))
        return None


async def _download_result(url: str, model: str) -> tuple[bytes, str] | None:
    """The image a provider returned as a URL; None when it is empty or over the size cap.

    One byte past the cap is read, so an oversized body fails the check instead of the
    whole body landing in memory first.
    """
    async with safe_fetch.fetch_client(_GENERATE_TIMEOUT) as client:
        img_resp = await safe_fetch.fetch_safely(
            client,
            url,
            deadline_seconds=_RESULT_DOWNLOAD_DEADLINE,
            max_body_bytes=MAX_ATTACHMENT_SIZE + 1,
        )
    img_resp.raise_for_status()
    content_type = img_resp.headers.get("content-type", "image/png").split(";")[0].strip().lower()
    if not img_resp.content:
        logger.warning("OpenRouter image generation response missing image payload model=%s", model)
        return None
    if len(img_resp.content) > MAX_ATTACHMENT_SIZE:
        logger.warning(
            "OpenRouter image generation URL response exceeds size cap model=%s bytes=%s",
            model,
            len(img_resp.content),
        )
        return None
    return img_resp.content, content_type or "image/png"
