"""The reply's model call carries its tools, and the calls it streams come back whole."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gateways import litellm_gateway
from app.gateways.stream_signals import StreamAttempt
from app.gateways.stream_tool_calls import StreamedToolCalls
from app.tests.fakes import isolated_settings

_SETTINGS = isolated_settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
_TOOL = {"type": "function", "function": {"name": "web_search", "parameters": {"type": "object"}}}
_MESSAGES = [{"role": "user", "content": "who won the champions league"}]


def _delta(
    index: Any = 0,
    *,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments)
    )


def _chunk(
    *, content: str | None = None, calls: list[Any] | None = None, finish: str | None = None
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=None)


async def _chunks(*items: SimpleNamespace, pause_after_first: float = 0.0) -> AsyncIterator[Any]:
    for index, item in enumerate(items):
        yield item
        if index == 0 and pause_after_first:
            await asyncio.sleep(pause_after_first)


def test_stream_tool_calls_fold_pieces_by_index() -> None:
    calls = StreamedToolCalls()
    assert calls.fold([_delta(call_id="call_a", name="web_search", arguments='{"query": ')])
    assert calls.fold([_delta(arguments='"champions league winner"}')])
    assert calls.calls() == [
        {
            "id": "call_a",
            "type": "function",
            "function": {
                "name": "web_search",
                "arguments": '{"query": "champions league winner"}',
            },
        }
    ]


def test_stream_tool_calls_set_a_repeated_name_once() -> None:
    calls = StreamedToolCalls()
    calls.fold([_delta(call_id="c1", name="web_search", arguments='{"query":')])
    calls.fold([_delta(name="web_search", arguments=' "x"}')])
    assert calls.calls()[0]["function"] == {"name": "web_search", "arguments": '{"query": "x"}'}


def test_stream_tool_calls_read_a_new_id_at_a_used_index_as_another_call() -> None:
    calls = StreamedToolCalls()
    calls.fold([_delta(call_id="c1", name="web_search", arguments='{"query": "a"}')])
    calls.fold([_delta(call_id="c2", name="web_search", arguments='{"query": "b"}')])
    assert [call["id"] for call in calls.calls()] == ["c1", "c2"]


def test_stream_tool_calls_drop_a_nameless_call_and_give_an_id_to_one_without() -> None:
    calls = StreamedToolCalls()
    calls.fold(
        [
            {"index": 0, "function": {"name": "web_search"}},
            {"index": 1, "function": {"arguments": "{}"}},
        ]
    )
    (only,) = calls.calls()
    assert only["id"].startswith("call_")
    assert only["function"] == {"name": "web_search", "arguments": "{}"}


@pytest.mark.parametrize("deltas", [None, [], MagicMock()])
def test_stream_tool_calls_pass_over_a_chunk_without_calls(deltas: Any) -> None:
    calls = StreamedToolCalls()
    assert calls.fold(deltas) is False
    assert calls.calls() == []


@pytest.mark.asyncio
async def test_stream_a_reply_that_only_calls_a_tool_has_answered() -> None:
    sent: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> AsyncIterator[Any]:
        sent.append(kwargs)
        return _chunks(
            _chunk(calls=[_delta(call_id="call_1", name="web_search", arguments='{"query": ')]),
            _chunk(calls=[_delta(arguments='"ucl winner"}')], finish="tool_calls"),
        )

    calls: list[dict[str, Any]] = []
    meta: dict[str, str] = {}
    attempts: list[StreamAttempt] = []
    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="free-chat",
                messages=_MESSAGES,
                max_tokens=100,
                fallback_aliases=["smart-chat"],
                stream_meta=meta,
                attempts=attempts,
                tools=[_TOOL],
                tool_calls=calls,
            )
        ]
    assert tokens == []
    # A call answers: the fallback alias is never asked.
    assert len(sent) == 1
    assert sent[0]["tools"] == [_TOOL]
    assert sent[0]["tool_choice"] == "auto"
    assert calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "web_search", "arguments": '{"query": "ucl winner"}'},
        }
    ]
    assert meta == {"finish_reason": "tool_calls", "model_alias": "free-chat"}
    assert [attempt.failed for attempt in attempts] == [False]


@pytest.mark.asyncio
async def test_stream_without_tools_sends_none() -> None:
    sent: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> AsyncIterator[Any]:
        sent.append(kwargs)
        return _chunks(_chunk(content="Nairobi."))

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS, model_alias="free-chat", messages=_MESSAGES, max_tokens=100
            )
        ]
    assert "".join(tokens) == "Nairobi."
    assert "tools" not in sent[0]
    assert "tool_choice" not in sent[0]


@pytest.mark.asyncio
async def test_stream_without_tools_reads_no_stray_call() -> None:
    """A call no tool was offered for is not an answer: the next alias writes one."""
    replies = iter(
        [
            _chunks(_chunk(calls=[_delta(call_id="c", name="web_search", arguments="{}")])),
            _chunks(_chunk(content="Nairobi.")),
        ]
    )

    async def fake_acompletion(**_kwargs: Any) -> AsyncIterator[Any]:
        return next(replies)

    calls: list[dict[str, Any]] = []
    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="free-chat",
                messages=_MESSAGES,
                max_tokens=100,
                fallback_aliases=["smart-chat"],
                tool_calls=calls,
            )
        ]
    assert "".join(tokens) == "Nairobi."
    assert calls == []


@pytest.mark.asyncio
async def test_stream_gives_no_tools_to_a_model_that_takes_none() -> None:
    sent: list[dict[str, Any]] = []
    route = replace(litellm_gateway.resolve_route("free-chat"), supports_tools=False)

    async def fake_acompletion(**kwargs: Any) -> AsyncIterator[Any]:
        sent.append(kwargs)
        return _chunks(_chunk(content="Nairobi."))

    with (
        patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)),
        patch.object(litellm_gateway, "resolve_route", return_value=route),
    ):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="free-chat",
                messages=_MESSAGES,
                max_tokens=100,
                tools=[_TOOL],
                tool_calls=[],
            )
        ]
    assert "".join(tokens) == "Nairobi."
    assert "tools" not in sent[0]


@pytest.mark.asyncio
async def test_stream_counts_a_tool_call_as_the_first_content() -> None:
    """A thinking model's first-content deadline must not cut off a call it is making."""
    stream = _chunks(
        _chunk(calls=[_delta(call_id="call_1", name="web_search", arguments="{}")]),
        _chunk(finish="tool_calls"),
        pause_after_first=0.3,
    )
    calls: list[dict[str, Any]] = []
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=stream)):
        tokens = [
            token
            async for token in litellm_gateway._stream_chat_once(
                settings=_SETTINGS,
                model_alias="free-chat",
                messages=_MESSAGES,
                max_tokens=100,
                first_content_timeout_seconds=0.1,
                tools=[_TOOL],
                tool_calls=calls,
            )
        ]
    assert tokens == []
    assert [call["id"] for call in calls] == ["call_1"]
