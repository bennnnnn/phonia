"""Every non-chat model call adds its cost to the global spend counter.

Embeddings, OCR, memory, titles, compression and follow-ups used
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
        (_complete_structured, "memory-model"),  # memory, follow-ups, classifiers
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


# ── stream attempts no reply kept ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "usage, prompt_chars, cause, tokens",
    [
        ({"input": 2_000, "output": 30}, 400, "cap", (2_000, 30)),  # reported usage wins
        ({"input": 2_000}, 400, "server", (2_000, 0)),  # reported, whatever the cause
        ({}, 4_000, "cap", (1_000, 0)),  # ran, no usage: the prompt's estimate
        ({}, 4_000, "empty", (1_000, 0)),
        ({}, 4_000, "timeout", (1_000, 0)),
        ({}, 4_000, None, (1_000, 0)),  # stopped before its text
        ({}, 4_000, "request", None),  # refused: nothing ran
        ({}, 4_000, "rate_limit", None),
        ({}, 4_000, "connection", None),
        ({}, 4_000, "server", None),
    ],
)
def test_discarded_attempt_cost(
    usage: dict[str, int], prompt_chars: int, cause: str | None, tokens: tuple[int, int] | None
) -> None:
    cost = llm_spend.discarded_attempt_cost_usd("free-chat", usage, prompt_chars, cause)
    if tokens is None:
        assert cost == 0.0
    else:
        expected = estimate_cost_usd("free-chat", input_tokens=tokens[0], output_tokens=tokens[1])
        assert cost == pytest.approx(expected)


def _delta_chunk(content: str | None, usage: SimpleNamespace | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=usage)


class _Stream:
    def __init__(self, chunks: list[SimpleNamespace], error: Exception | None = None) -> None:
        self._chunks = list(chunks)
        self._error = error

    def __aiter__(self) -> "_Stream":
        return self

    async def __anext__(self) -> SimpleNamespace:
        if self._chunks:
            return self._chunks.pop(0)
        if self._error is not None:
            raise self._error
        raise StopAsyncIteration


async def _stream_reply(providers: list[Any], usage: dict[str, int]) -> str:
    fake = AsyncMock(side_effect=providers)
    with patch.object(litellm_gateway, "acompletion", fake):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "x" * 4_000}],
                max_tokens=50,
                usage=usage,
                fallback_aliases=["free-chat"],
            )
        ]
    return "".join(tokens)


async def test_a_discarded_stream_attempt_counts_toward_global_spend(model_spend_redis) -> None:
    """The first model answered only whitespace (with usage), the backup answered: the
    user is charged the backup alone, global spend gets the discarded attempt too."""
    empty = _Stream([_delta_chunk("  "), _delta_chunk(None, _usage(5_000, 7))])
    answered = _Stream([_delta_chunk("Hello."), _delta_chunk(None, _usage(4_000, 3))])
    usage: dict[str, int] = {}

    assert await _stream_reply([empty, answered], usage) == "Hello."

    assert usage == {"input": 4_000, "output": 3}  # the user's quota: the kept attempt
    # Finalize charges the kept one; the meter adds only the discarded one.
    assert await _metered(model_spend_redis) == _cost("smart-chat", 5_000, 7)


async def test_a_discarded_attempt_without_usage_counts_its_prompt(model_spend_redis) -> None:
    empty = _Stream([_delta_chunk("   ")])  # ran, ended with no text and no usage
    answered = _Stream([_delta_chunk("Hello.")])

    assert await _stream_reply([empty, answered], {}) == "Hello."

    assert await _metered(model_spend_redis) == _cost("smart-chat", 1_000, 0)


async def test_a_refused_attempt_adds_nothing(model_spend_redis) -> None:
    refused = type("BadRequest", (Exception,), {"status_code": 400})("bad request")
    answered = _Stream([_delta_chunk("Hello.")])

    assert await _stream_reply([refused, answered], {}) == "Hello."

    assert await _metered(model_spend_redis) == 0


async def test_a_reply_cut_off_after_its_text_is_left_to_finalize(model_spend_redis) -> None:
    text = "The answer is 4. " * 40  # past any think hold: the reply has started
    broken = _Stream([_delta_chunk(text, _usage(5_000, 2))], error=RuntimeError("reset"))
    usage: dict[str, int] = {}

    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _stream_reply([broken], usage)

    assert usage == {"input": 5_000, "output": 2}  # finalize charges the partial reply
    assert await _metered(model_spend_redis) == 0


async def test_stream_calls_disable_litellm_and_sdk_retries() -> None:
    fake = AsyncMock(return_value=_Stream([_delta_chunk("Hi.")]))
    with patch.object(litellm_gateway, "acompletion", fake):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=50,
            )
        ]
    assert tokens == ["Hi."]
    assert fake.await_args is not None
    kwargs = fake.await_args.kwargs
    assert (kwargs["num_retries"], kwargs["max_retries"]) == (0, 0)


@pytest.mark.parametrize("call", [_complete_text, _complete_structured, _vision])
async def test_completion_calls_disable_litellm_and_sdk_retries(model_spend_redis, call) -> None:
    fake = AsyncMock(return_value=_completion('{"needs_search": false}'))
    with patch.object(litellm_gateway, "acompletion", fake):
        await call()
    assert fake.await_args is not None
    kwargs = fake.await_args.kwargs
    assert (kwargs["num_retries"], kwargs["max_retries"]) == (0, 0)
