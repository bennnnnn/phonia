"""What the tool loop's search sends: the topic, the resolved reference, or the message."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.chat.tool_loop import forced_search
from app.modules.web_search import turn_query
from app.tests.tool_context import tool_context


def _awaited(mock: AsyncMock) -> Any:
    """The last await of *mock*; fails the test when it was never awaited."""
    assert mock.await_args is not None
    return mock.await_args


_NAME_CHAT = [
    {"role": "user", "content": "My name is bini"},
    {"role": "assistant", "content": "Nice to meet you, Bini!"},
    {"role": "user", "content": "What is its meaning"},
    {"role": "assistant", "content": "The name bini is a short form of binary."},
    {"role": "user", "content": "Wrong"},
    {"role": "assistant", "content": "Sorry about that."},
    {"role": "user", "content": "Do a seearch"},
]


@pytest.mark.asyncio
async def test_bare_request_searches_the_resolved_topic() -> None:
    resolve = AsyncMock(return_value="Bini name meaning")
    with patch.object(turn_query, "resolve_reference", resolve):
        queries = await turn_query.search_queries_for_turn(Settings(), "Do a seearch", _NAME_CHAT)
    assert queries == ["Bini name meaning"]
    kwargs = _awaited(resolve).kwargs
    assert kwargs["kind"] == "search"
    assert ("assistant", "The name bini is a short form of binary.") in kwargs["turns"]


@pytest.mark.asyncio
async def test_bare_request_falls_back_past_one_word_reactions() -> None:
    with patch.object(turn_query, "resolve_reference", AsyncMock(return_value=None)):
        queries = await turn_query.search_queries_for_turn(Settings(), "Do a seearch", _NAME_CHAT)
    # The last line that stands alone, not "Wrong" and not the request itself.
    assert queries == ["What is its meaning"]


@pytest.mark.asyncio
async def test_named_topic_is_searched_as_is() -> None:
    resolve = AsyncMock()
    with patch.object(turn_query, "resolve_reference", resolve):
        queries = await turn_query.search_queries_for_turn(
            Settings(), "search for the meaning of bini", _NAME_CHAT
        )
    assert queries == ["the meaning of bini"]
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_pronoun_follow_up_is_resolved() -> None:
    messages = [
        {"role": "user", "content": "Who lived the longest?"},
        {"role": "assistant", "content": "Jeanne Calment, 122 years."},
        {"role": "user", "content": "when did she die?"},
    ]
    resolve = AsyncMock(return_value="Jeanne Calment death date")
    with patch.object(turn_query, "resolve_reference", resolve):
        queries = await turn_query.search_queries_for_turn(
            Settings(), "when did she die?", messages
        )
    assert queries == ["Jeanne Calment death date"]


@pytest.mark.asyncio
async def test_standalone_question_is_its_own_query() -> None:
    resolve = AsyncMock()
    messages = [{"role": "user", "content": "who won the lakers game last night"}]
    with patch.object(turn_query, "resolve_reference", resolve):
        queries = await turn_query.search_queries_for_turn(
            Settings(), "who won the lakers game last night", messages
        )
    assert queries == ["who won the lakers game last night"]
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_loop_searches_the_topic_not_the_request() -> None:
    """The screenshot: "Do a seearch" used to reach Tavily as the words "Do a seearch"."""
    run_search = AsyncMock(return_value=([], ["Bini name meaning"]))
    ctx = tool_context()
    with (
        patch.object(turn_query, "resolve_reference", AsyncMock(return_value="Bini name meaning")),
        patch("app.modules.chat.tool_loop.forced_search.run_cached_search", run_search),
    ):
        _messages, hits = await forced_search._force_web_search_if_needed(
            settings=Settings(web_search_enabled=True),
            messages=list(_NAME_CHAT),
            search_hits=[],
            ctx=ctx,
            on_status=None,
            should_cancel=None,
            search_required=True,
        )
    assert hits == []
    assert _awaited(run_search).args[1] == ["Bini name meaning"]
    assert _awaited(run_search).kwargs["budget"] is ctx.tavily_budget


# "Find a coffee shop near me" searched those words: New York cafés came back and
# the reply gave them Nairobi addresses. "Weather here" found Milwaukee.
_NAIROBI = "Westlands, Nairobi, Kenya"


@pytest.mark.parametrize(
    "query, expected",
    [
        ("coffee shops near me", "coffee shops near Westlands, Nairobi, Kenya"),
        ("coffee nearby", "coffee near Westlands, Nairobi, Kenya"),
        ("weather in current location", "weather in Westlands, Nairobi, Kenya"),
        ("weather in my location today", "weather in Westlands, Nairobi, Kenya today"),
        ("current weather", "current weather Westlands, Nairobi, Kenya"),
        # The model already named the place: it is not added twice.
        ("best coffee shops Westlands Nairobi", "best coffee shops Westlands Nairobi"),
    ],
)
def test_anchor_to_location_names_the_place(query: str, expected: str) -> None:
    from app.modules.web_search.query_builders import anchor_to_location

    assert anchor_to_location(query, _NAIROBI) == expected
    assert anchor_to_location(query, None) == query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, location, expected",
    [
        (
            "find a coffee shop near me",
            _NAIROBI,
            "find a coffee shop near Westlands, Nairobi, Kenya",
        ),
        (
            "what's the weather like here",
            _NAIROBI,
            "what's the weather like here Westlands, Nairobi, Kenya",
        ),
        ("find a coffee shop near me", None, "find a coffee shop near me"),
        # Not a nearby ask: the saved place stays out of the search.
        ("who won the last world cup", _NAIROBI, "who won the last world cup"),
    ],
)
async def test_turn_search_names_the_place_for_a_nearby_ask(
    message: str, location: str | None, expected: str
) -> None:
    queries = await turn_query.search_queries_for_turn(
        Settings(), message, [{"role": "user", "content": message}], user_location=location
    )
    assert queries == [expected]


@pytest.mark.asyncio
async def test_forced_search_sends_the_turn_location() -> None:
    message = "find a coffee shop near me"
    ctx = tool_context(user_query=message, user_location=_NAIROBI)
    run_search = AsyncMock(return_value=([], [message]))
    with patch("app.modules.chat.tool_loop.forced_search.run_cached_search", run_search):
        await forced_search._force_web_search_if_needed(
            settings=Settings(web_search_enabled=True),
            messages=[{"role": "user", "content": message}],
            search_hits=[],
            ctx=ctx,
            on_status=None,
            should_cancel=None,
            search_required=True,
        )
    assert _awaited(run_search).args[1] == ["find a coffee shop near Westlands, Nairobi, Kenya"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_query, location, sent",
    [
        ("find a coffee shop near me", _NAIROBI, "coffee shops near Westlands, Nairobi, Kenya"),
        ("find a coffee shop near me", None, "coffee shops near me"),
        ("tell me about coffee", _NAIROBI, "coffee shops near me"),
    ],
)
async def test_model_written_search_names_the_place(
    user_query: str, location: str | None, sent: str
) -> None:
    from app.modules.web_search.tool import WebSearchAdapter

    ctx = tool_context(user_query=user_query, user_location=location)
    run_search = AsyncMock(return_value=([], [sent]))
    with patch("app.modules.web_search.tool.run_cached_search", run_search):
        await WebSearchAdapter(Settings()).invoke({"query": "coffee shops near me"}, ctx)
    assert _awaited(run_search).args[1] == [sent]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text, query",
    [
        # Its own words found a company called Thinking Pixel and the launch-day post.
        ("I'm thinking of getting the Pixel 11, is it out yet?", "is Pixel 11 out yet"),
        ("my wife wants the iPhone 18 Pro Max, has it been released?",
         "has iPhone 18 Pro Max been released"),
        ("do you know when the Galaxy S26 came out?", "when the Galaxy S26 came out"),
        ("can you tell me if GTA 6 is out yet?", "GTA 6 is out yet"),
        ("I keep hearing about GPT-6 — when does it come out?", "when does GPT-6 come out"),
        # A message that is only the ask is its own query, as before.
        ("Is iPhone 19 out?", "Is iPhone 19 out?"),
        # Another question keeps every question.
        ("which chip does the iPhone 18 Pro Max have and when was it released?",
         "which chip does the iPhone 18 Pro Max have and when was it released?"),
        ("is the iPhone 19 out? and how much will it cost?",
         "is the iPhone 19 out? and how much will it cost?"),
        # "Season 3" alone would lose whose season it is.
        ("I loved Severance season 2, when is season 3 coming out?",
         "I loved Severance season 2, when is season 3 coming out?"),
    ],
)  # fmt: skip
async def test_a_release_ask_in_chatter_searches_the_ask(text: str, query: str) -> None:
    assert await turn_query.search_queries_for_turn(Settings(), text, []) == [query]
