"""A tool call a model writes as reply text is read as a call and never shown.

GLM 5.2 sent its search as text on 2026-10-24, and the bubble showed the markup with
sources and no answer.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.gateways import litellm_gateway
from app.gateways.stream_tool_calls import StreamedToolCalls
from app.gateways.text_tool_calls import TextToolCalls, read_text_call
from app.tests.fakes import isolated_settings

_SETTINGS = isolated_settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
_TOOL = {"type": "function", "function": {"name": "web_search", "parameters": {"type": "object"}}}
_MESSAGES = [{"role": "user", "content": "graph the population of Ethiopia"}]

# The two replies the app showed, as GLM wrote them (the second leaves out </arg_key>).
_ETHIOPIA = (
    "<tool_call>web_search<arg_key>query</arg_key><arg_value>Ethiopia population total "
    "2017 2018 2019 2020 World Bank</arg_value></tool_call>"
)
_ETB = (
    "<tool_call>web_search<arg_key>query<arg_value>USD to ETB monthly exchange rate "
    "January February 2026</arg_value></tool_call>"
)


def _stream(text: str, calls: StreamedToolCalls | None, size: int) -> str:
    reader = TextToolCalls(calls)
    shown = "".join(reader.feed(text[i : i + size]) for i in range(0, len(text), size))
    return shown + reader.flush()


@pytest.mark.parametrize(
    ("text", "query"),
    [
        (_ETHIOPIA, "Ethiopia population total 2017 2018 2019 2020 World Bank"),
        (_ETB, "USD to ETB monthly exchange rate January February 2026"),
        (
            '<tool_call>{"name": "web_search", "arguments": {"query": "ucl winner"}}</tool_call>',
            "ucl winner",
        ),
    ],
)
@pytest.mark.parametrize("size", [1, 3, 7, 1000])
def test_a_call_written_as_text_is_a_call_and_shows_nothing(
    text: str, query: str, size: int
) -> None:
    calls = StreamedToolCalls()
    assert _stream(text, calls, size) == ""
    [call] = calls.calls()
    assert call["function"]["name"] == "web_search"
    assert json.loads(call["function"]["arguments"]) == {"query": query}


def test_prose_around_a_call_still_shows() -> None:
    calls = StreamedToolCalls()
    shown = _stream(f"Let me check.{_ETHIOPIA} Back soon.", calls, 5)
    assert shown == "Let me check. Back soon."
    assert len(calls.calls()) == 1


def test_with_no_tools_offered_the_call_is_dropped() -> None:
    """The search already ran: the markup goes, and an empty reply passes to the next model."""
    assert _stream(_ETHIOPIA, None, 4) == ""


def test_a_call_left_open_at_the_end_is_still_a_call() -> None:
    calls = StreamedToolCalls()
    assert _stream(_ETHIOPIA.removesuffix("</tool_call>"), calls, 6) == ""
    assert calls.calls()[0]["function"]["name"] == "web_search"


@pytest.mark.parametrize(
    "text",
    [
        "Use the <toolbar> to save.",
        "The tag <tool is cut",
        "Ends with <tool_ca",
        "No tags at all, just 3 < 4.",
    ],
)
def test_text_that_only_looks_like_a_call_shows_as_written(text: str) -> None:
    calls = StreamedToolCalls()
    assert _stream(text, calls, 2) == text
    assert calls.calls() == []


def test_prose_that_names_the_tag_is_shown() -> None:
    """An unclosed tag in prose held the rest of the reply and dropped it at the end."""
    calls = StreamedToolCalls()
    text = "The `<tool_call>` tag opens a call. " + "More words follow. " * 30
    assert _stream(text, calls, 9) == text
    pair = "Write `<tool_call>` then `</tool_call>` around it."
    assert _stream(pair, calls, 4) == pair
    assert calls.calls() == []


def test_a_query_of_digits_stays_a_string() -> None:
    """The search tool's schema wants a string: a query of 2024 failed validation."""
    calls = StreamedToolCalls()
    text = "<tool_call>web_search<arg_key>query</arg_key><arg_value>2024</arg_value></tool_call>"
    assert _stream(text, calls, 5) == ""
    assert json.loads(calls.calls()[0]["function"]["arguments"]) == {"query": "2024"}


@pytest.mark.parametrize("body", ["", "  ", "{not json}", '{"name": 3}', "<arg_key>q</arg_key>"])
def test_a_body_that_names_no_tool_is_no_call(body: str) -> None:
    assert read_text_call(body) is None


def _chunk(content: str) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=None)


async def _chunks(*pieces: str) -> AsyncIterator[Any]:
    for piece in pieces:
        yield _chunk(piece)


@pytest.mark.asyncio
async def test_the_reply_stream_turns_the_text_call_into_a_search() -> None:
    pieces = [_ETHIOPIA[i : i + 9] for i in range(0, len(_ETHIOPIA), 9)]

    async def fake_acompletion(**_kwargs: Any) -> AsyncIterator[Any]:
        return _chunks(*pieces)

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
                tools=[_TOOL],
                tool_calls=calls,
            )
        ]
    assert tokens == []
    assert [call["function"]["name"] for call in calls] == ["web_search"]


@pytest.mark.asyncio
async def test_with_no_tools_a_reply_that_was_only_a_call_goes_to_the_next_model() -> None:
    replies = iter([_chunks(_ETHIOPIA), _chunks("Ethiopia had about 132 million people.")])

    async def fake_acompletion(**_kwargs: Any) -> AsyncIterator[Any]:
        return next(replies)

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="free-chat",
                messages=_MESSAGES,
                max_tokens=100,
                fallback_aliases=["smart-chat"],
            )
        ]
    assert "".join(tokens) == "Ethiopia had about 132 million people."
