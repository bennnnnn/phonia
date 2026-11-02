"""Search honesty: a failed search reads as failed, results that miss are allowed to miss,
facts are attributed, and official sources come first (D11.6, D11.2, T5.10, T5.9)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.gateways import web_search_gateway as gw
from app.gateways.web_search_gateway import WebSearchHit, WebSearchUnavailableError
from app.modules.web_search import (
    WEB_SEARCH_HINT,
    TurnTavilyBudget,
    format_search_block,
    format_search_empty_block,
)
from app.modules.web_search.search_cache import _run_search, _search_with_cache
from app.modules.web_search.source_quality import rank_by_source, source_tier
from app.modules.web_search.tool import WebSearchAdapter
from app.tests.tool_context import tool_context

_LIVE = Settings(
    mock_llm_enabled=False, tavily_api_key="tvly-test", web_search_fallback_enabled=True
)


def _tavily_500() -> AsyncMock:
    request = httpx.Request("POST", gw.TAVILY_SEARCH_URL)
    response = httpx.Response(500, request=request)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_tavily_500_and_an_empty_fallback_is_a_failed_search() -> None:
    with (
        patch.object(gw, "get_pooled_client", return_value=_tavily_500()),
        patch.object(gw, "_search_duckduckgo", AsyncMock(return_value=[])),
        pytest.raises(WebSearchUnavailableError),
    ):
        await gw.search_web(_LIVE, "who won the match")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tavily_key, ddg, expected",
    [
        # Tavily answered with nothing, DuckDuckGo errored: nothing was found.
        ("tvly-test", WebSearchUnavailableError("down"), "empty"),
        # No Tavily, DuckDuckGo answered with nothing: nothing was found.
        ("", [], "empty"),
        # No Tavily, DuckDuckGo errored: the search failed.
        ("", WebSearchUnavailableError("down"), "failed"),
    ],
)
async def test_search_web_says_failed_only_when_the_search_of_record_failed(
    tavily_key: str, ddg: object, expected: str
) -> None:
    settings = Settings(
        mock_llm_enabled=False, tavily_api_key=tavily_key, web_search_fallback_enabled=True
    )
    ddg_mock = (
        AsyncMock(side_effect=ddg) if isinstance(ddg, Exception) else AsyncMock(return_value=ddg)
    )
    with (
        patch.object(gw, "_search_tavily", AsyncMock(return_value=[])),
        patch.object(gw, "_search_duckduckgo", ddg_mock),
    ):
        if expected == "failed":
            with pytest.raises(WebSearchUnavailableError):
                await gw.search_web(settings, "q")
        else:
            assert await gw.search_web(settings, "q") == []


def test_every_duckduckgo_call_failing_raises() -> None:
    ddgs = MagicMock()
    ddgs.__enter__.return_value.text.side_effect = RuntimeError("ratelimited")
    ddgs.__enter__.return_value.news.side_effect = RuntimeError("ratelimited")
    with (
        patch.dict("sys.modules", {"ddgs": SimpleNamespace(DDGS=lambda **_k: ddgs)}),
        pytest.raises(WebSearchUnavailableError),
    ):
        gw._search_duckduckgo_sync("plain query", 3)


@pytest.mark.asyncio
async def test_the_turn_ledger_records_a_failed_search(fake_redis) -> None:
    settings = Settings(mock_llm_enabled=False, tavily_api_key="")
    user: Any = SimpleNamespace(id=uuid4(), plan="free")
    budget = TurnTavilyBudget(settings=settings, user=user)
    failing = AsyncMock(side_effect=WebSearchUnavailableError("down"))
    with patch("app.modules.web_search.search_cache.web_search_gateway.search_web", failing):
        hits = await _search_with_cache(
            settings, "q", max_results=3, budget=budget, user=user, redis=fake_redis
        )
    assert hits == []
    assert budget.search_failed is True
    budget.record_search(failed=False)
    assert budget.search_failed is False


@pytest.mark.asyncio
async def test_the_tool_result_says_the_search_failed_not_no_results(fake_redis) -> None:
    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=False))
    ctx = tool_context(user=SimpleNamespace(id=uuid4(), plan="free"), redis=fake_redis)
    failing = AsyncMock(side_effect=WebSearchUnavailableError("down"))
    with patch("app.modules.web_search.search_cache.web_search_gateway.search_web", failing):
        result = await adapter.invoke({"query": "lisbon weather"}, ctx)
    assert result.content.startswith("Search failed")
    assert "No results" not in result.content

    empty = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=False))
    ctx = tool_context(user=SimpleNamespace(id=uuid4(), plan="free"), redis=fake_redis)
    with patch(
        "app.modules.web_search.search_cache.web_search_gateway.search_web",
        AsyncMock(return_value=[]),
    ):
        result = await empty.invoke({"query": "a very obscure thing"}, ctx)
    assert result.content.startswith("No results")


def test_the_empty_block_words_failure_apart_from_nothing_found() -> None:
    failed = format_search_empty_block(["lisbon weather"], failed=True)
    empty = format_search_empty_block(["lisbon weather"])
    assert "failed" in failed and "didn't work just now" in failed
    assert "no usable results" in empty and "failed" not in empty


@pytest.mark.asyncio
async def test_the_forced_search_says_failed_when_the_search_failed() -> None:
    from app.modules.chat.tool_loop import forced_search

    ctx = tool_context(user=SimpleNamespace(id=uuid4(), plan="free"))

    async def run(*_args: object, budget: TurnTavilyBudget, **_kwargs: object):
        budget.record_search(failed=True)
        return [], ["lisbon weather"]

    messages = [{"role": "user", "content": "search the web for lisbon weather"}]
    with (
        patch.object(forced_search, "run_cached_search", run),
        patch.object(
            forced_search, "search_queries_for_turn", AsyncMock(return_value=["lisbon weather"])
        ),
    ):
        out, hits = await forced_search._force_web_search_if_needed(
            settings=Settings(web_search_enabled=True),
            messages=messages,
            search_hits=[],
            ctx=ctx,
            on_status=None,
            should_cancel=None,
            search_required=True,
        )
    assert hits == []
    injected = "\n".join(str(m["content"]) for m in out if m["role"] == "system")
    assert "search service failed" in injected


def test_results_that_miss_may_say_so_and_facts_are_attributed() -> None:
    """D11.2 and T5.10: the model may say nothing it found covers it, never fill in.

    It says so in its own voice and names its sources: "according to the search results"
    read as a machine talking (2026-10-24).
    """
    block = format_search_block([WebSearchHit(title="T", url="https://a.example", snippet="s")])
    assert "couldn't find a source that covers it" in block
    assert "do not fill the gap from memory" in block
    assert "Do NOT say search failed or came up dry" not in block
    assert "you MUST answer from those results" not in WEB_SEARCH_HINT
    assert "According to" in WEB_SEARCH_HINT
    assert "link only pages from the results" in WEB_SEARCH_HINT  # safety phrase
    team = format_search_block(
        [WebSearchHit(title="T", url="https://a.example", snippet="s")], team="Kenya"
    )
    assert "Do NOT say search failed" not in team and "say so; do not guess" in team


@pytest.mark.parametrize(
    "url, tier",
    [
        ("https://www.cdc.gov/flu/index.html", 0),
        ("https://www.gov.uk/visas", 0),
        ("https://www.ox.ac.uk/admissions", 0),
        ("https://kenya.go.ke/", 0),
        ("https://en.wikipedia.org/wiki/Lisbon", 0),
        ("https://docs.python.org/3/", 0),
        ("https://developer.apple.com/swift/", 0),
        ("https://www.reuters.com/world/", 0),
        ("https://abc.go.com/shows", 1),
        ("https://docs.google.com/document/d/x", 1),
        ("https://www.example-blog.com/post", 1),
        ("not a url", 1),
        ("https://www.quora.com/What-is-x", 2),
        ("https://brainly.com/question/1", 2),
    ],
)
def test_source_tier(url: str, tier: int) -> None:
    assert source_tier(url) == tier


@pytest.mark.asyncio
async def test_official_sources_are_put_first_and_ties_keep_provider_order() -> None:
    """T5.9: a content farm and an official page; the official one leads the block."""
    farm = WebSearchHit(title="Farm", url="https://www.quora.com/flu", snippet="opinions")
    blog = WebSearchHit(title="Blog", url="https://blog.example.com/flu", snippet="a post")
    cdc = WebSearchHit(title="CDC", url="https://www.cdc.gov/flu", snippet="official")
    news = WebSearchHit(title="News", url="https://news.example.com/flu", snippet="report")

    async def search(*_args: object, **_kwargs: object) -> list[WebSearchHit]:
        return [farm, blog, cdc, news]

    with patch("app.modules.web_search.search_cache._search_with_cache", side_effect=search):
        merged, _tried = await _run_search(Settings(web_search_max_results=5), ["flu"])
    assert [hit.title for hit in merged] == ["CDC", "Blog", "News", "Farm"]
    block = format_search_block(merged)
    assert block.index("CDC") < block.index("Farm")
    assert rank_by_source([blog, news]) == [blog, news]
