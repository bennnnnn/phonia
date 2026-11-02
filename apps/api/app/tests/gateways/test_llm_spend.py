"""Every non-chat model call adds its cost to the global spend counter.

Embeddings, OCR, memory, titles, suggestions, compression and follow-ups used
to spend without counting, so ``DAILY_GLOBAL_SPEND_USD`` saw a fraction of the
day. The chat turn's own calls are charged at finalize and must not count twice.
"""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.background_tasks import drain_background_tasks
from app.core.config import Settings
from app.core.spend_counter import get_global_spend_micro_usd, usd_to_micro_usd
from app.gateways import embedding_gateway, litellm_gateway, llm_spend
from app.gateways.tool_completion import NO_TOOL_NAME
from app.models.model_catalog import estimate_cost_usd
from app.models.schemas import ConversationReference

_SETTINGS = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")


def _usage(prompt: Any, completion: Any) -> SimpleNamespace:
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)


def _completion(content: str, *, prompt: int = 1_000, completion: int = 200) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=_usage(prompt, completion),
    )


def _cost(alias: str, prompt: int, completion: int) -> int:
    usd = estimate_cost_usd(alias, input_tokens=prompt, output_tokens=completion)
    assert usd, f"{alias} has catalog prices"
    return usd_to_micro_usd(usd)


async def _metered(model_spend_redis) -> int:
    await drain_background_tasks(timeout_seconds=2)
    return await get_global_spend_micro_usd(model_spend_redis)


@pytest.mark.parametrize(
    "alias, response, expected_usd",
    [
        ("memory-model", _completion("{}", prompt=1_000_000, completion=0), 0.03),
        ("title-model", _completion("t", prompt=0, completion=1_000_000), 0.13),
        ("vision-chat", _completion("t", prompt=500_000, completion=500_000), 0.08),
        ("fallback-memory-model", _completion("t", prompt=1_000_000, completion=0), 0.10),
        ("fallback-vision-model", _completion("t", prompt=0, completion=1_000_000), 0.50),
        ("embedding-model", SimpleNamespace(usage=_usage(1_000_000, None)), 0.02),
        ("no-such-alias", _completion("t"), 0.0),
        ("memory-model", SimpleNamespace(usage=None), 0.0),
        ("memory-model", MagicMock(), 0.0),  # a test double reports no real tokens
        ("memory-model", SimpleNamespace(usage=_usage(True, -5)), 0.0),
        ("memory-model", None, 0.0),
    ],
)
def test_response_cost_usd_prices_reported_tokens(
    alias: str, response: object, expected_usd: float
) -> None:
    assert llm_spend.response_cost_usd(alias, response) == pytest.approx(expected_usd)


async def test_meter_model_call_adds_to_todays_spend(model_spend_redis) -> None:
    llm_spend.meter_model_call("memory-model", _completion("{}"))
    llm_spend.meter_model_call("memory-model", _completion("{}"))

    assert await _metered(model_spend_redis) == 2 * _cost("memory-model", 1_000, 200)


async def test_meter_model_call_never_fails_the_call(model_spend_redis) -> None:
    broken = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch.object(llm_spend, "record_global_spend", broken):
        llm_spend.meter_model_call("memory-model", _completion("{}"))
        await drain_background_tasks(timeout_seconds=2)

    broken.assert_awaited_once()


async def _complete_text() -> None:
    await litellm_gateway.complete_text(
        settings=_SETTINGS,
        model_alias="title-model",
        messages=[{"role": "user", "content": "x"}],
    )


async def _complete_structured() -> None:
    await litellm_gateway.complete_structured(
        settings=_SETTINGS,
        model_alias="memory-model",
        messages=[{"role": "user", "content": "x"}],
        schema=ConversationReference,
    )


async def _vision() -> None:
    await litellm_gateway.vision_completion(
        settings=_SETTINGS,
        model_alias="vision-chat",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=64,
    )


@pytest.mark.parametrize(
    "call, alias",
    [
        (_complete_text, "title-model"),  # titles, compression
        (_complete_structured, "memory-model"),  # memory, suggestions, follow-ups, classifiers
        (_vision, "vision-chat"),  # scanned-PDF OCR, scan reads
    ],
)
async def test_gateway_completions_are_metered(model_spend_redis, call, alias: str) -> None:
    response = _completion('{"needs_search": false}')
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=response)):
        await call()

    assert await _metered(model_spend_redis) == _cost(alias, 1_000, 200)


async def test_embeddings_are_metered(model_spend_redis) -> None:
    response = SimpleNamespace(
        data=[{"embedding": [0.1] * 8}], usage=SimpleNamespace(prompt_tokens=40_000)
    )
    with patch.object(embedding_gateway, "aembedding", AsyncMock(return_value=response)):
        vec = await embedding_gateway.embed_text(_SETTINGS, "remember this")

    assert vec == [0.1] * 8
    assert await _metered(model_spend_redis) == _cost("embedding-model", 40_000, 0)


async def test_a_chat_turns_tool_round_is_left_to_finalize(model_spend_redis) -> None:
    """Tool rounds go into the turn's usage, which finalize charges once."""
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": NO_TOOL_NAME, "arguments": "{}"},
    }
    message = SimpleNamespace(content=None, tool_calls=[call])
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=_usage(3_000, 40),
    )
    usage: dict[str, int] = {}
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=response)):
        await litellm_gateway.complete_with_tools(
            settings=_SETTINGS,
            model_alias="free-chat",
            messages=[{"role": "user", "content": "x"}],
            tools=[],
            max_tokens=64,
            usage=usage,
        )

    assert usage == {"input": 3_000, "output": 40}
    await asyncio.sleep(0)
    assert await _metered(model_spend_redis) == 0
