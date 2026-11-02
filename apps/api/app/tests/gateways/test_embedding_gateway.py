"""embed_many: the one bounded embedding fan-out (attachments, chat history, memory).

Inputs go to the provider ``embedding_batch_size`` at a time. Every test here
patches ``aembedding`` (or ``embed_text``), so no test reaches the network.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways import embedding_gateway, llm_spend

_EMBED_TEXT = "app.gateways.embedding_gateway.embed_text"
_LIVE: dict[str, Any] = {"mock_llm_enabled": False, "openrouter_api_key": "test-key"}


def _settings(**overrides: Any) -> Settings:
    return Settings(**(_LIVE | overrides))


def _vector_for(text: str) -> list[float]:
    return [float(len(text)), 0.5]


class _Provider:
    """A fake ``aembedding``: records each request, answers in reverse order with indexes."""

    def __init__(self, *, fail_when: str | None = None, delay: float = 0.0) -> None:
        self.requests: list[list[str]] = []
        self.in_flight = 0
        self.peak = 0
        self.fail_when = fail_when
        self.delay = delay

    async def __call__(self, *, model: str, input: list[str], **_kwargs: Any) -> Any:
        self.requests.append(list(input))
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            if self.fail_when is not None and self.fail_when in input:
                raise RuntimeError("provider rejected the request")
            data = [
                {"embedding": _vector_for(text), "index": index} for index, text in enumerate(input)
            ]
            return SimpleNamespace(data=list(reversed(data)), usage=None)
        finally:
            self.in_flight -= 1


async def _embed_many(provider: _Provider, texts: list[str], **kwargs: Any) -> Any:
    concurrency = kwargs.pop("concurrency", 8)
    with (
        patch.object(embedding_gateway, "aembedding", provider),
        patch.object(llm_spend, "meter_model_call"),
    ):
        return await embedding_gateway.embed_many(
            _settings(**kwargs), texts, concurrency=concurrency
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("count", "batch_size", "request_sizes"),
    [(1, 64, [1]), (64, 64, [64]), (65, 64, [64, 1]), (150, 64, [64, 64, 22]), (5, 2, [2, 2, 1])],
)
async def test_embed_many_sends_batches_and_keeps_input_order(
    count: int, batch_size: int, request_sizes: list[int]
):
    texts = [f"piece {index:03d}" + "x" * index for index in range(count)]
    provider = _Provider()

    result = await _embed_many(provider, texts, embedding_batch_size=batch_size)

    assert sorted(len(request) for request in provider.requests) == sorted(request_sizes)
    assert result == [_vector_for(text) for text in texts]


@pytest.mark.asyncio
@pytest.mark.parametrize(("concurrency", "batches"), [(1, 5), (3, 12), (8, 4), (0, 3), (-3, 3)])
async def test_embed_many_caps_requests_in_flight(concurrency: int, batches: int):
    provider = _Provider(delay=0.005)
    texts = [f"piece {index}" for index in range(batches)]

    result = await _embed_many(provider, texts, embedding_batch_size=1, concurrency=concurrency)

    assert len(provider.requests) == batches
    assert len(result) == batches
    # Bounded, and still a fan-out rather than one request at a time.
    assert provider.peak == min(max(1, concurrency), batches)


@pytest.mark.asyncio
async def test_embed_many_empty_input_makes_no_calls():
    provider = _Provider()

    assert await _embed_many(provider, []) == []
    assert provider.requests == []


@pytest.mark.asyncio
async def test_embed_many_cuts_each_input_to_the_char_cap():
    provider = _Provider()

    await _embed_many(provider, ["a" * 50, "b" * 5], embedding_input_max_chars=10)

    assert provider.requests == [["a" * 10, "b" * 5]]


@pytest.mark.asyncio
async def test_a_failed_batch_is_retried_one_text_at_a_time():
    """One rejected input voids its request; the rest of that batch is still embedded."""
    provider = _Provider(fail_when="bad")

    result = await _embed_many(provider, ["good", "bad", "fine"], embedding_batch_size=64)

    assert result == [_vector_for("good"), None, _vector_for("fine")]
    assert provider.requests[0] == ["good", "bad", "fine"]
    assert sorted(provider.requests[1:]) == [["bad"], ["fine"], ["good"]]


@pytest.mark.asyncio
async def test_embed_many_raises_what_escapes_embed_text():
    """An error ``embed_text`` does not turn into None fails the whole call, as each caller's
    own loop did: the attachment job retries, a chat-history message is skipped and logged."""

    async def embed(_settings: Settings, text: str) -> list[float]:
        if text == "boom":
            raise RuntimeError("embedding route missing")
        return _vector_for(text)

    with (
        patch(_EMBED_TEXT, embed),
        patch.object(embedding_gateway, "aembedding", AsyncMock(side_effect=RuntimeError("down"))),
        pytest.raises(RuntimeError, match="route missing"),
    ):
        await embedding_gateway.embed_many(_settings(), ["ok", "boom", "ok too"], concurrency=3)


@pytest.mark.asyncio
async def test_a_short_answer_counts_as_a_failed_request():
    """A provider that returns fewer vectors than inputs cannot be matched up: retry singly."""
    response = SimpleNamespace(data=[{"embedding": [1.0], "index": 0}], usage=None)
    with (
        patch.object(embedding_gateway, "aembedding", AsyncMock(return_value=response)),
        patch.object(llm_spend, "meter_model_call"),
    ):
        result = await embedding_gateway.embed_many(_settings(), ["a", "b"], concurrency=2)

    assert result == [[1.0], [1.0]]


@pytest.mark.asyncio
async def test_mock_mode_embeds_every_input_without_a_provider():
    provider = _Provider()

    with patch.object(embedding_gateway, "aembedding", provider):
        result = await embedding_gateway.embed_many(
            Settings(mock_llm_enabled=True, openrouter_api_key=""), ["a", "b", "c"], concurrency=2
        )

    assert provider.requests == []
    assert len(result) == 3 and all(vector and len(vector) == 1536 for vector in result)
