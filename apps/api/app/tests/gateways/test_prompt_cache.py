"""Prompt caching at the gateway: the stable system message is marked only for a model
that caches a marked prefix, and the provider's cached prompt tokens are counted."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from litellm.llms.openrouter.chat.transformation import OpenrouterConfig

from app.core.config import Settings
from app.gateways import litellm_gateway, stream_usage
from app.gateways.prompt_cache import EPHEMERAL, with_cache_breakpoint
from app.models import model_catalog

_PROMPT = [
    {"role": "system", "content": "Stable instructions"},
    {"role": "system", "content": "Current local time: 9:00 AM"},
    {"role": "user", "content": "hi"},
]


def test_only_a_model_that_needs_the_mark_gets_it() -> None:
    marked = with_cache_breakpoint(_PROMPT, model_catalog.get("free-chat"))
    assert marked[0] == {
        "role": "system",
        "content": [{"type": "text", "text": "Stable instructions", "cache_control": EPHEMERAL}],
    }
    # The turn's own context and the user turn go as they were, after the mark.
    assert marked[1:] == _PROMPT[1:]
    # A provider that reuses an identical prefix by itself gets the prompt untouched.
    for alias in ("qwen-3.7-flash", "smart-chat", "glm-5.2", "gpt-6-luna"):
        assert with_cache_breakpoint(_PROMPT, model_catalog.get(alias)) is _PROMPT


def test_the_prompt_itself_is_never_changed() -> None:
    prompt = [dict(message) for message in _PROMPT]
    with_cache_breakpoint(prompt, model_catalog.get("free-chat"))
    assert prompt == _PROMPT


@pytest.mark.parametrize(
    "messages",
    [
        # A lone system prompt holds the turn's own text: a mark would be a write per turn.
        [{"role": "system", "content": "everything"}, {"role": "user", "content": "hi"}],
        [{"role": "user", "content": "hi"}],
        [],
        # Already in parts (a caller's own format) or empty: left alone.
        [
            {"role": "system", "content": [{"type": "text", "text": "x"}]},
            {"role": "system", "content": "turn"},
        ],
        [{"role": "system", "content": ""}, {"role": "system", "content": "turn"}],
    ],
)
def test_no_mark_without_a_stable_message_before_the_turns(messages: list[dict[str, Any]]) -> None:
    assert with_cache_breakpoint(messages, model_catalog.get("free-chat")) is messages


def test_litellm_forwards_the_mark_to_openrouter_for_claude() -> None:
    route = model_catalog.get("free-chat")
    body = OpenrouterConfig().transform_request(
        model=route.model.removeprefix("openrouter/"),
        messages=with_cache_breakpoint(_PROMPT, route),  # type: ignore[arg-type]
        optional_params={},
        litellm_params={},
        headers={},
    )
    assert body["messages"][0]["content"][0]["cache_control"] == EPHEMERAL


class _OneChunk:
    def __init__(self, usage: Any = None) -> None:
        self.done = False
        self.usage = usage

    def __aiter__(self) -> _OneChunk:
        return self

    async def __anext__(self) -> Any:
        if self.done:
            raise StopAsyncIteration
        self.done = True
        delta = SimpleNamespace(content="Hello")
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=delta, finish_reason="stop")], usage=self.usage
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias, enabled, marked",
    [("free-chat", True, True), ("free-chat", False, False), ("qwen-3.7-flash", True, False)],
)
async def test_the_stream_sends_the_mark_for_its_route(
    alias: str, enabled: bool, marked: bool
) -> None:
    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        prompt_cache_breakpoints_enabled=enabled,
    )
    acompletion = AsyncMock(return_value=_OneChunk())
    with patch("app.gateways.litellm_gateway.acompletion", acompletion):
        tokens = [
            token
            async for token in litellm_gateway._stream_chat_once(
                settings=settings, model_alias=alias, messages=_PROMPT, max_tokens=10
            )
        ]
    assert "".join(tokens) == "Hello"
    assert acompletion.await_args is not None
    sent = acompletion.await_args.kwargs["messages"]
    assert isinstance(sent[0]["content"], list) is marked
    assert sent[1:] == _PROMPT[1:]


def _sse(usage: dict[str, Any]) -> bytes:
    """OpenRouter's stream for a two-chunk reply, then its usage chunk."""
    base = {"id": "gen-1", "object": "chat.completion.chunk", "created": 1, "model": "m"}
    chunks = [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hello"}}]},
        {
            **base,
            "choices": [{"index": 0, "delta": {"content": " there"}, "finish_reason": "stop"}],
        },
        {**base, "choices": [], "usage": usage},
    ]
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in [*chunks, "[DONE]"]).encode()


_TOKENS = {"prompt_tokens": 5000, "completion_tokens": 40, "total_tokens": 5040}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias, enabled, usage, marked, counts",
    [
        (
            "free-chat",
            True,
            {**_TOKENS, "prompt_tokens_details": {"cached_tokens": 4096, "cache_write_tokens": 0}},
            True,
            {"cached_input": 4096},
        ),
        (
            "free-chat",
            True,
            {**_TOKENS, "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 4096}},
            True,
            {"cache_write": 4096},
        ),
        ("free-chat", False, _TOKENS, False, {}),
        (
            "qwen-3.7-flash",
            True,
            {**_TOKENS, "prompt_tokens_details": {"cached_tokens": 4096}},
            False,
            {"cached_input": 4096},
        ),
    ],
)
async def test_through_litellm_the_request_carries_the_mark_and_the_reply_its_cache_counts(
    alias: str, enabled: bool, usage: dict[str, Any], marked: bool, counts: dict[str, int]
) -> None:
    """The real LiteLLM path to OpenRouter, with only the HTTP layer faked."""
    sent: list[httpx.Request] = []

    async def send(_client: Any, request: httpx.Request, *_args: Any, **_kwargs: Any) -> Any:
        sent.append(request)
        stream = {"content-type": "text/event-stream"}
        return httpx.Response(200, headers=stream, content=_sse(usage), request=request)

    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        prompt_cache_breakpoints_enabled=enabled,
    )
    totals: dict[str, int] = {}
    with patch.object(httpx.AsyncClient, "send", send):
        reply = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=settings, model_alias=alias, messages=_PROMPT, max_tokens=50, usage=totals
            )
        ]
    assert "".join(reply) == "Hello there"
    assert totals == {"input": 5000, "output": 40, **counts}
    (request,) = sent
    assert request.url.host == "openrouter.ai"
    body = json.loads(request.content)
    stable = {"type": "text", "text": "Stable instructions", "cache_control": EPHEMERAL}
    expected = [stable] if marked else "Stable instructions"
    assert body["messages"][0] == {"role": "system", "content": expected}
    assert body["messages"][1:] == _PROMPT[1:]


def _usage(**details: Any) -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=5000,
            completion_tokens=40,
            prompt_tokens_details=SimpleNamespace(**details) if details else None,
        )
    )


def test_cached_and_written_prompt_tokens_are_counted() -> None:
    usage: dict[str, int] = {}
    stream_usage.apply_usage(usage, _usage(cached_tokens=4096, cache_write_tokens=0))
    stream_usage.apply_usage(usage, _usage(cached_tokens=0, cache_write_tokens=4096))
    assert usage == {"input": 10_000, "output": 80, "cached_input": 4096, "cache_write": 4096}


def test_a_provider_without_cache_details_adds_no_cache_counts() -> None:
    usage: dict[str, int] = {}
    stream_usage.apply_usage(usage, _usage())
    # A mock's attribute is not a count.
    stream_usage.apply_usage(
        usage,
        SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=1, completion_tokens=1, prompt_tokens_details=MagicMock()
            )
        ),
    )
    assert usage == {"input": 5001, "output": 41}


def test_a_kept_attempt_carries_its_cache_counts() -> None:
    usage = {"input": 10, "output": 2}
    stream_usage.merge_attempt_usage(usage, {"input": 5000, "output": 40, "cached_input": 4096})
    assert usage == {"input": 5010, "output": 42, "cached_input": 4096}


@pytest.mark.asyncio
async def test_the_streamed_reply_reports_the_cache_hit() -> None:
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    chunk_usage = SimpleNamespace(
        prompt_tokens=5000,
        completion_tokens=40,
        prompt_tokens_details=SimpleNamespace(cached_tokens=4096, cache_write_tokens=None),
    )
    usage: dict[str, int] = {}
    with patch(
        "app.gateways.litellm_gateway.acompletion", AsyncMock(return_value=_OneChunk(chunk_usage))
    ):
        async for _ in litellm_gateway.stream_chat_completion(
            settings=settings,
            model_alias="free-chat",
            messages=_PROMPT,
            max_tokens=10,
            usage=usage,
        ):
            pass
    assert usage == {"input": 5000, "output": 40, "cached_input": 4096}


def test_the_turn_cost_line_shows_the_cache(caplog: pytest.LogCaptureFixture) -> None:
    from app.modules.chat.turn_settle import _log_turn_cost, _turn_charge

    ctx = SimpleNamespace(user_id=uuid4(), model="free-chat", prompt_messages=[])
    usage = {"input": 5000, "output": 40, "cached_input": 4096, "cache_write": 12}
    with caplog.at_level(logging.INFO, logger="app.modules.chat.turn_settle"):
        _log_turn_cost(ctx, _turn_charge(ctx, "Hello", usage))  # type: ignore[arg-type]
    assert "input_tokens=5000 output_tokens=40" in caplog.text
    assert "cached_input_tokens=4096 cache_write_tokens=12" in caplog.text
    assert "est_cost_usd=0.000520" in caplog.text
