"""Plain text completion for background work, with one fallback alias.

Titles and summaries call ``complete_text``. A hung or failing provider falls over to
the background fallback alias instead of stalling the job worker.
"""

import asyncio
import logging
from typing import Any

from app.core.config import Settings
from app.gateways import llm_spend, mock_llm
from app.gateways.structured_completion import fallback_alias

logger = logging.getLogger(__name__)


async def acompletion_with_fallback(
    settings: Settings,
    primary_alias: str,
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    response_format: dict[str, str] | None = None,
) -> Any | None:
    """Run acompletion against the primary background alias; on provider outage
    retry once against the fallback alias. Returns the LiteLLM response object,
    or None if both fail. Used by the background paths (titles, summaries,
    project extraction) so a single-provider DeepSeek incident doesn't silently
    stall every background pipeline.
    """
    # Imported at call time: litellm_gateway re-exports this module.
    from app.gateways import litellm_gateway as gateway

    fallback = fallback_alias(settings, primary_alias)
    for alias in (primary_alias, fallback):
        if alias is None:
            continue
        try:
            route = gateway.resolve_route(alias)
            kwargs = gateway._litellm_kwargs(settings, route, thinking=False)
            params: dict[str, Any] = dict(
                model=route.model, messages=messages, max_tokens=max_tokens, **kwargs
            )
            if response_format is not None:
                params["response_format"] = response_format
            async with asyncio.timeout(settings.background_llm_timeout_seconds):
                response = await gateway.acompletion(**params)
            llm_spend.meter_model_call(alias, response)
            return response
        except TimeoutError:
            if alias == primary_alias and fallback is not None:
                logger.warning(
                    "Background LLM %s timed out after %ss; retrying with fallback %s",
                    primary_alias,
                    settings.background_llm_timeout_seconds,
                    fallback,
                )
                continue
            logger.warning(
                "Background LLM %s timed out after %ss",
                alias,
                settings.background_llm_timeout_seconds,
            )
            return None
        except Exception:
            if alias == primary_alias and fallback is not None:
                logger.warning(
                    "Background LLM %s unavailable; retrying with fallback %s",
                    primary_alias,
                    fallback,
                )
                continue
            logger.exception("Background LLM %s failed", alias)
            return None
    return None


async def complete_text(
    *,
    settings: Settings,
    model_alias: str,
    messages: list[dict[str, str]],
    max_tokens: int = 256,
) -> str | None:
    """Return assistant text content from a non-streaming completion (or None)."""
    if mock_llm.should_mock_llm(settings):
        return None
    response = await acompletion_with_fallback(
        settings, model_alias, messages=messages, max_tokens=max_tokens
    )
    if response is None:
        return None
    try:
        return (response.choices[0].message.content or "").strip() or None
    except Exception:
        logger.exception("Text completion failed to parse response for %s", model_alias)
        return None
