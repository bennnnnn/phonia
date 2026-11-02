"""A search about now also reads news pages, each with the day it was published.

Live 2026-10-25: "who won the world series this year?" was answered "The Tampa Bay Rays
won" from a winners' table whose 2026 row read "Tampa Bay Rays | 0 | 1 | Milwaukee
Brewers", while the series was one game old. No page said when it was written.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit, _published_at, search_web
from app.modules.web_search import search_cache
from app.modules.web_search.formatting import format_search_block
from app.modules.web_search.recency import wants_dated_results
from app.modules.web_search.search_cache import _run_search, _search_cache_key
from app.modules.web_search.source_dates import published_note


@pytest.mark.parametrize(
    ("text", "dated"),
    [
        ("who won the world series this year?", True),
        ("wait is it over already? i thought it just started", True),
        ("so what's the score in the series right now?", True),
        ("is the world series over?", True),
        ("when is game 3?", True),
        ("did the dodgers win?", True),
        ("has the election been called?", True),
        ("is the iphone 18 out", True),
        ("is the new zelda out yet", True),
        ("latest iphone", True),
        ("World Series 2026", True),
        # History, places, and words that only look like now (review of the first draft).
        ("who won the 1998 world series", False),
        ("who won the first super bowl", False),
        ("i already know python, what language next?", False),
        ("explain the current account deficit", False),
        ("restaurants open right now near me", False),
        # Second review: words that only look like now, and live asks it missed.
        ("how are credit scores calculated", False),
        ("breaking bad cast", False),
        ("how to write a catchy headline", False),
        ("yesterday by the beatles chords", False),
        ("what are good new year's resolutions for this year", False),
        ("election results", True),
        ("who's in the world series", True),
        ("is the government still shut down", True),
        ("what is the capital of france?", False),
        ("how does photosynthesis work", False),
    ],
)
def test_wants_dated_results(text: str, dated: bool) -> None:
    with patch("app.modules.web_search.recency.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 25, tzinfo=UTC)
        assert wants_dated_results(text) is dated


@pytest.mark.parametrize(
    ("raw", "published"),
    [
        ("Sat, 24 Oct 2026 10:00:00 GMT", "2026-10-24T10:00:00+00:00"),
        ("2026-10-23T21:00:24Z", "2026-10-23T21:00:24+00:00"),
        ("2026-10-23", "2026-10-23"),
        ("", ""),
        ("yesterday", ""),
        (None, ""),
    ],
)
def test_published_at(raw: object, published: str) -> None:
    assert _published_at(raw) == published


def test_the_note_is_the_users_own_day() -> None:
    """A recap posted at 03:30 GMT on the 25th was written on the 24th in Los Angeles."""
    late = "2026-10-25T03:30:00+00:00"
    assert published_note(late, date(2026, 10, 24), "America/Los_Angeles") == (
        "[Published Saturday, October 24, 2026 (today).] "
    )
    assert published_note(late, date(2026, 10, 25), "Africa/Nairobi") == (
        "[Published Sunday, October 25, 2026 (today).] "
    )
    assert published_note("2026-10-24", date(2026, 10, 25), "UTC") == (
        "[Published Saturday, October 24, 2026 (yesterday).] "
    )
    assert published_note("", date(2026, 10, 25), "UTC") == ""


def _tavily(results: list[dict[str, str]]) -> AsyncMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"results": results}
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_a_news_search_asks_tavily_for_news_and_keeps_the_day() -> None:
    settings = Settings(tavily_api_key="test-key", web_search_fallback_enabled=False)
    client = _tavily(
        [
            {
                "title": "Rays score 4 runs in first inning of World Series Game 2",
                "url": "https://www.mlb.com/news/rays-game-2",
                "content": "Game 2 at American Family Field.",
                "published_date": "Sun, 25 Oct 2026 04:00:00 GMT",
            }
        ]
    )
    with patch("app.gateways.web_search_gateway.get_pooled_client", return_value=client):
        hits = await search_web(settings, "World Series 2026", topic="news")
    assert client.post.await_args.kwargs["json"]["topic"] == "news"
    assert hits[0].published == "2026-10-25T04:00:00+00:00"


@pytest.mark.asyncio
async def test_a_news_search_finds_nothing_without_tavily() -> None:
    """DuckDuckGo gives no dates; the turn's own search already ran it."""
    settings = Settings(mock_llm_enabled=True, tavily_api_key="", web_search_fallback_enabled=True)
    assert await search_web(settings, "World Series 2026", topic="news") == []
    assert await search_web(settings, "World Series 2026")


def test_the_news_search_has_its_own_cache_entry() -> None:
    general = _search_cache_key("world series", 5, user_id="u")
    assert _search_cache_key("world series", 5, user_id="u", topic="general") == general
    assert _search_cache_key("world series", 5, user_id="u", topic="news") == f"{general}:news"


def _hit(name: str, published: str = "") -> WebSearchHit:
    return WebSearchHit(
        title=name, url=f"https://example.com/{name}", snippet=name, published=published
    )


@pytest.mark.asyncio
async def test_a_dated_search_adds_news_after_each_general_result(fake_redis):
    """The best general page stays first, and none is pushed out (review of the draft)."""
    settings = Settings(web_search_max_results=5)
    news = [_hit("game-1", "2026-10-24"), _hit("game-2", "2026-10-25"), _hit("shared"), _hit("n4")]
    general = [_hit("winners-list"), _hit("shared"), _hit("history")]

    async def search(_settings, query, *, max_results, skip_tavily=False, topic="general"):
        return news if topic == "news" else general

    with patch("app.modules.web_search.search_cache.web_search_gateway.search_web", search):
        merged, tried = await _run_search(
            settings, ["world series 2026"], redis=fake_redis, dated=True
        )
        plain, _ = await _run_search(settings, ["world series 2026"], redis=fake_redis)

    assert tried == ["world series 2026"]
    assert [hit.title for hit in merged] == [
        "winners-list",
        "game-1",
        "shared",
        "game-2",
        "history",
    ]
    assert [hit.title for hit in plain] == ["winners-list", "shared", "history"]
    # The news pages keep their moments through the cache.
    again, _ = await _run_search(settings, ["world series 2026"], redis=fake_redis, dated=True)
    assert [hit.published for hit in again if hit.published] == ["2026-10-24", "2026-10-25"]


@pytest.mark.asyncio
async def test_a_slow_news_search_never_holds_up_the_general_one(fake_redis):
    import asyncio

    settings = Settings(web_search_max_results=5)

    async def search(_settings, query, *, max_results, skip_tavily=False, topic="general"):
        if topic == "news":
            await asyncio.sleep(30)
        return [_hit("winners-list")]

    with (
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", search),
        patch.object(search_cache, "NEWS_GRACE_SECONDS", 0.05),
    ):
        merged, _ = await asyncio.wait_for(
            _run_search(settings, ["world series 2026"], redis=fake_redis, dated=True), 2
        )
    assert [hit.title for hit in merged] == ["winners-list"]


def test_a_news_page_published_today_is_today_s() -> None:
    from app.modules.web_search.query_builders import filter_hits_to_today

    with patch("app.modules.web_search.query_builders.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 25, 12, tzinfo=UTC)
        kept = filter_hits_to_today(
            [_hit("fresh", "2026-10-25T09:00:00+00:00"), _hit("old", "2026-10-20T09:00:00+00:00")],
            "UTC",
        )
    assert [hit.title for hit in kept] == ["fresh"]


def test_the_search_block_says_when_each_page_was_published() -> None:
    hits = [
        _hit("game-2", "2026-10-25"),
        WebSearchHit(title="winners", url="https://example.com/w", snippet="2025 Dodgers"),
    ]
    with patch("app.modules.web_search.formatting.local_today", return_value=date(2026, 10, 25)):
        block = format_search_block(hits, user_timezone="America/New_York")
    assert (
        "1. game-2 (https://example.com/game-2) — [Published Sunday, October 25, 2026 (today).]"
        in block
    )
    assert "2. winners (https://example.com/w) — 2025 Dodgers" in block
