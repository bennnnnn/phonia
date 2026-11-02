"""A search for the newest X names this year; "I want to know if it will rain" is weather.

"What's the newest iPhone" answered iPhone 17 from 2018 to 2025 articles. "I want to
know if it will rain tomorrow" got "I don't have access to live weather data".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.web_search import is_geo_query, turn_query
from app.modules.web_search.patterns import is_weather_request
from app.modules.web_search.recency import anchor_recency_to_year, asks_for_newest
from app.modules.web_search.tool import WebSearchAdapter
from app.tests.tool_context import tool_context

_YEAR = datetime.now().year


@pytest.mark.parametrize(
    "text, newest",
    [
        ("what's the newest iphone", True),
        ("tell me about the new tesla model", True),
        ("what is the latest version of django", True),
        ("the most recent pixel phone", True),
        ("I'm new to python, where should I start?", False),
        ("happy new year!", False),
        ("a new way to learn", False),
        ("who won the last world cup", False),
    ],
)
def test_asks_for_newest_reads_recency_words(text: str, newest: bool) -> None:
    assert asks_for_newest(text) is newest


def test_anchor_recency_adds_the_year_once() -> None:
    assert anchor_recency_to_year("newest iphone", "what's the newest iphone", None) == (
        f"newest iphone {_YEAR}"
    )
    # The query already names a year, or the user did not ask for the newest.
    assert anchor_recency_to_year("iphone 2025", "the newest iphone", None) == "iphone 2025"
    assert anchor_recency_to_year("iphone review", "iphone review", None) == "iphone review"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, expected",
    [
        ("what's the newest iphone", f"what's the newest iphone {_YEAR}"),
        ("search for the latest tesla model", f"the latest tesla model {_YEAR}"),
        ("I'm new to python", "I'm new to python"),
    ],
)
async def test_turn_search_dates_a_newest_ask(message: str, expected: str) -> None:
    queries = await turn_query.search_queries_for_turn(
        Settings(), message, [{"role": "user", "content": message}]
    )
    assert queries == [expected]


@pytest.mark.asyncio
async def test_news_keeps_its_own_date_not_a_bare_year() -> None:
    message = "latest news on AI"
    queries = await turn_query.search_queries_for_turn(
        Settings(), message, [{"role": "user", "content": message}]
    )
    assert queries == [message]


@pytest.mark.asyncio
async def test_model_written_search_dates_a_newest_ask() -> None:
    ctx = tool_context(user_query="what's the newest iphone")
    run_search = AsyncMock(return_value=([], ["q"]))
    with patch("app.modules.web_search.tool.run_cached_search", run_search):
        await WebSearchAdapter(Settings()).invoke({"query": "newest iPhone model"}, ctx)
    sent: Any = run_search.await_args
    assert sent is not None and sent.args[1] == [f"newest iPhone model {_YEAR}"]


@pytest.mark.parametrize(
    "text",
    [
        "I want to know if it will rain tomorrow",
        "can you tell me if it will rain tomorrow",
        "do you know whether it's going to snow this weekend",
        "I wonder if it'll storm tonight",
        "will it rain tomorrow",
    ],
)
def test_an_indirect_rain_question_is_local_weather(text: str) -> None:
    assert is_weather_request(text)
    assert is_geo_query(text)


@pytest.mark.parametrize(
    "text",
    [
        "even if it rains we play",
        # Text pasted to proofread: only a message that opens by asking is a forecast ask.
        "fix this: they don't know if it will rain, so we bring coats",
        "I wonder whether it will matter if I skip breakfast",
        "I'm under the weather",
    ],
)
def test_a_rain_clause_is_not_a_forecast(text: str) -> None:
    assert not is_weather_request(text)
