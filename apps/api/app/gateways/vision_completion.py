"""Non-streaming image-input completion, with one fallback vision model.

Provider calls go through ``litellm_gateway``, which re-exports this module, so
it is imported at call time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import Settings
from app.gateways import llm_spend, mock_llm
from app.models.model_catalog import vision_backup_alias

logger = logging.getLogger(__name__)

# A second image-capable model from another company (memory's fallback is text-only).
FALLBACK_VISION_ALIAS = vision_backup_alias()

# Every caller reads what is on the page (camera scans, scanned PDFs): the same
# photo must give the same transcription, so sampling is greedy.
READING_TEMPERATURE = 0.0


async def vision_completion(
    *,
    settings: Settings,
    model_alias: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    response_format: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> Any | None:
    """Non-streaming vision completion (image input) against a vision route.

    Returns the LiteLLM response object, or None on provider
    outage/timeout. This is the gateway seam for image-input completions
    (camera math OCR, scanned-PDF OCR) so services don't call
    ``litellm.acompletion`` directly (layering: external IO belongs in gateways).

    ``timeout_seconds`` is the whole call's budget. A provider error retries
    once against ``FALLBACK_VISION_ALIAS`` in whatever time is left; a timeout
    does not retry, because the budget is spent. Otherwise None on failure
    (OCR is best-effort and must never raise into the chat path).
    """
    if mock_llm.should_mock_llm(settings):
        return None
    from app.gateways import litellm_gateway as gateway

    aliases = [model_alias]
    if FALLBACK_VISION_ALIAS != model_alias:
        aliases.append(FALLBACK_VISION_ALIAS)
    timeout = (
        settings.background_llm_timeout_seconds if timeout_seconds is None else timeout_seconds
    )
    try:
        async with asyncio.timeout(max(0.0, timeout)):
            for index, alias in enumerate(aliases):
                route = gateway.resolve_route(alias)
                kwargs = gateway._litellm_kwargs(
                    settings, route, thinking=False
                )  # no key: ModelUnavailable
                params: dict[str, Any] = dict(
                    model=route.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=READING_TEMPERATURE,
                    **kwargs,
                )
                if response_format is not None:
                    params["response_format"] = response_format
                try:
                    response = await gateway.acompletion(**params)
                except (TimeoutError, gateway.ModelUnavailableError):
                    raise
                except Exception:
                    if index < len(aliases) - 1:
                        logger.warning(
                            "Vision LLM %s failed; retrying with fallback %s",
                            alias,
                            aliases[index + 1],
                            exc_info=True,
                        )
                        continue
                    logger.warning("Vision LLM %s failed", alias, exc_info=True)
                    return None
                llm_spend.meter_model_call(alias, response)
                return response
    except TimeoutError:
        logger.warning("Vision LLM %s timed out after %ss", model_alias, timeout)
        return None
    return None
