"""What each non-chat model call cost, added to the global spend counter.

Every completion and embedding passes through a gateway, so this is the one
place that prices them all: catalog price x the provider's reported tokens,
as finalize prices a chat turn. Memory jobs, titles, compression,
follow-up questions, OCR, embeddings and the query classifiers are all metered
here. A chat turn's own stream and tool rounds are not: finalize charges them
with the turn's usage (``modules/chat/turn_settle``), so metering them here
would count them twice.

The write runs on its own task, so it never adds latency to the call it
measured or loses its result to the caller's deadline. Best-effort: a failed
write is logged.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.background_tasks import create_background_task
from app.core.redis import get_redis_client
from app.core.spend_counter import record_global_spend
from app.models.model_catalog import estimate_cost_usd

logger = logging.getLogger(__name__)

# The counter is one INCRBY; a Redis this slow is already failing other calls.
_RECORD_TIMEOUT_SECONDS = 2.0


def _tokens(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def response_cost_usd(alias: str, response: object) -> float:
    """Catalog price x the response's token usage; 0 when either is unknown."""
    usage = getattr(response, "usage", None)
    input_tokens = _tokens(getattr(usage, "prompt_tokens", None))
    output_tokens = _tokens(getattr(usage, "completion_tokens", None))
    if not input_tokens and not output_tokens:
        return 0.0
    cost = estimate_cost_usd(alias, input_tokens=input_tokens, output_tokens=output_tokens)
    return cost or 0.0


def meter_model_call(alias: str, response: object) -> None:
    """Add one provider response's cost to today's global spend, off the call's path."""
    cost = response_cost_usd(alias, response)
    if cost > 0:
        create_background_task(_record(alias, cost), name="model_spend")


async def _record(alias: str, cost: float) -> None:
    try:
        async with asyncio.timeout(_RECORD_TIMEOUT_SECONDS):
            await record_global_spend(get_redis_client(), cost)
    except Exception:
        logger.warning("Model spend not recorded alias=%s usd=%.6f", alias, cost, exc_info=True)
