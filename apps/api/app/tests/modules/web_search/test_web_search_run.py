from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit, search_web


@pytest.mark.asyncio
async def test_search_web_uses_mock_without_api_key():
    settings = Settings(mock_llm_enabled=True, tavily_api_key="", web_search_fallback_enabled=False)
    hits = await search_web(settings, "test query")
    assert len(hits) == 1
    assert "Mock search" in hits[0].title


@pytest.mark.asyncio
async def test_search_web_with_a_key_searches_for_real_in_mock_mode():
    """Mock mode fakes search only without a key, like the chat model (should_mock_llm)."""
    settings = Settings(
        mock_llm_enabled=True, tavily_api_key="test-key", web_search_fallback_enabled=False
    )
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "results": [
            {
                "title": "Freddie Mac PMMS",
                "url": "https://www.freddiemac.com/pmms",
                "content": "6.27%",
            }
        ]
    }
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    with patch("app.gateways.web_search_gateway.get_pooled_client", return_value=client):
        hits = await search_web(settings, "mortgage rates this week")
    client.post.assert_awaited_once()
    assert hits == [
        WebSearchHit(
            title="Freddie Mac PMMS", url="https://www.freddiemac.com/pmms", snippet="6.27%"
        )
    ]


@pytest.mark.asyncio
async def test_run_search_parallelizes_queries():
    """The queries run together: no search finishes until all three have started."""
    import asyncio

    from app.modules.web_search.search_cache import _run_search

    settings = Settings(web_search_max_results=10, mock_llm_enabled=True)
    all_started = asyncio.Barrier(3)

    async def mock_search(_settings, query, *, max_results, budget=None, user=None, redis=None):
        # Run one at a time, the first search waits here alone and times out.
        await asyncio.wait_for(all_started.wait(), timeout=1)
        return [
            WebSearchHit(
                title=f"{query} hit",
                url=f"https://example.com/{query}",
                snippet="snippet",
            )
        ]

    with patch("app.modules.web_search.search_cache._search_with_cache", side_effect=mock_search):
        merged, tried = await _run_search(settings, ["q1", "q2", "q3"])

    assert tried == ["q1", "q2", "q3"]
    assert len(merged) == 3


@pytest.mark.asyncio
async def test_run_search_reserves_tavily_once_per_turn(fake_redis):
    """A multi-query turn must spend at most ONE daily Tavily search, not one
    per fanned-out query — the whole point of the shared per-turn budget."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.modules.web_search.search_cache import _run_search

    settings = Settings(web_search_max_results=10, mock_llm_enabled=True, tavily_api_key="test-key")
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"

    reserve_calls = 0

    async def counting_reserve(counter, _redis, _user, _settings):
        assert counter == "tavily_search"
        nonlocal reserve_calls
        reserve_calls += 1
        return True

    async def fake_search(_settings, query, *, max_results=10, skip_tavily=False):
        return [WebSearchHit(title=query, url=f"https://ex/{query}", snippet="s")]

    with (
        patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.web_search.search_cache.counters.reserve",
            counting_reserve,
        ),
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", fake_search),
    ):
        merged, _tried = await _run_search(
            settings,
            ["q1", "q2", "q3", "q4"],
            user=user,
            redis=fake_redis,
        )

    assert reserve_calls == 1
    assert len(merged) == 4


@pytest.mark.asyncio
async def test_run_cached_search_shares_the_turn_tavily_budget(fake_redis):
    """Two MCP-style run_cached_search calls given one turn budget spend one Tavily slot."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.modules.web_search.search_cache import TurnTavilyBudget, run_cached_search

    settings = Settings(web_search_max_results=10, mock_llm_enabled=True, tavily_api_key="test-key")
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"

    reserve_calls = 0

    async def counting_reserve(counter, _redis, _user, _settings):
        assert counter == "tavily_search"
        nonlocal reserve_calls
        reserve_calls += 1
        return True

    async def fake_search(_settings, query, *, max_results=10, skip_tavily=False):
        return [WebSearchHit(title=query, url=f"https://ex/{query}", snippet="s")]

    with (
        patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.web_search.search_cache.counters.reserve",
            counting_reserve,
        ),
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", fake_search),
    ):
        budget = TurnTavilyBudget(settings=settings, user=user)
        await run_cached_search(settings, ["q1"], user=user, redis=fake_redis, budget=budget)
        await run_cached_search(settings, ["q2"], user=user, redis=fake_redis, budget=budget)
        assert reserve_calls == 1
        # Without a turn budget each call reserves for itself.
        await run_cached_search(settings, ["q3"], user=user, redis=fake_redis)
        await run_cached_search(settings, ["q4"], user=user, redis=fake_redis)

    assert reserve_calls == 3


@pytest.mark.asyncio
async def test_run_search_skips_tavily_reservation_when_unconfigured(fake_redis):
    """No Tavily key → the turn uses free DuckDuckGo, so it must not spend a
    daily Tavily search reserving a call Tavily never performs."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.modules.web_search.search_cache import _run_search

    settings = Settings(web_search_max_results=10, mock_llm_enabled=True, tavily_api_key="")
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"

    reserve_calls = 0

    async def counting_reserve(counter, _redis, _user, _settings):
        assert counter == "tavily_search"
        nonlocal reserve_calls
        reserve_calls += 1
        return True

    async def fake_search(_settings, query, *, max_results=10, skip_tavily=False):
        return [WebSearchHit(title=query, url=f"https://ex/{query}", snippet="s")]

    with (
        patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.web_search.search_cache.counters.reserve",
            counting_reserve,
        ),
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", fake_search),
    ):
        merged, _tried = await _run_search(settings, ["q1", "q2"], user=user, redis=fake_redis)

    assert reserve_calls == 0
    assert len(merged) == 2


@pytest.mark.asyncio
async def test_skip_tavily_when_user_missing(fake_redis):
    """No user on the budget must not run uncapped Tavily."""
    from app.modules.web_search.search_cache import TurnTavilyBudget

    settings = Settings(tavily_api_key="test-key")
    budget = TurnTavilyBudget(settings=settings, user=None)
    reserve = AsyncMock(side_effect=AssertionError("must not reserve without a user"))
    with patch(
        "app.modules.web_search.search_cache.counters.reserve",
        reserve,
    ):
        assert await budget.skip_tavily(fake_redis) is True
        assert await budget.skip_tavily(fake_redis) is True
    reserve.assert_not_called()


@pytest.mark.parametrize("used_today, skip", [(0, False), (1, True)])
@pytest.mark.asyncio
async def test_skip_tavily_follows_the_daily_cap(fake_redis, quota_clock, used_today, skip):
    """Tavily runs while a slot is left today (reserve returns its day), then DuckDuckGo."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.modules.billing.entitlements import setting_name
    from app.modules.web_search.search_cache import TurnTavilyBudget

    settings = Settings(
        tavily_api_key="test-key", **{setting_name("daily_web_searches", "free"): 1}
    )
    user = MagicMock(id=uuid4(), plan="free")
    key = f"tavily:{user.id}:2026-10-16"
    if used_today:
        await fake_redis.set(key, used_today, ex=60)
    budget = TurnTavilyBudget(settings=settings, user=user)
    assert await budget.skip_tavily(fake_redis) is skip
    # A reserved search stays spent; one past the cap is given back at once.
    assert await fake_redis.get(key) == "1"


@pytest.mark.asyncio
async def test_skip_tavily_on_redis_reserve_error(fake_redis):
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.exceptions import RedisUnavailableError
    from app.modules.web_search.search_cache import TurnTavilyBudget

    settings = Settings(tavily_api_key="test-key")
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"
    budget = TurnTavilyBudget(settings=settings, user=user)
    with patch(
        "app.modules.web_search.search_cache.counters.reserve",
        AsyncMock(side_effect=RedisUnavailableError()),
    ):
        assert await budget.skip_tavily(fake_redis) is True
        assert await budget.skip_tavily(fake_redis) is True


@pytest.mark.asyncio
async def test_search_cache_is_per_user(fake_redis):
    from unittest.mock import MagicMock
    from uuid import uuid4

    from app.modules.web_search.search_cache import TurnTavilyBudget, _search_with_cache

    settings = Settings(web_search_cache_ttl=300, mock_llm_enabled=True, tavily_api_key="")
    u1 = MagicMock()
    u1.id = uuid4()
    u1.plan = "free"
    u2 = MagicMock()
    u2.id = uuid4()
    u2.plan = "free"
    hit = WebSearchHit(title="Hit", url="https://example.com", snippet="snippet")
    search_mock = AsyncMock(return_value=[hit])
    with (
        patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis),
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", search_mock),
    ):
        await _search_with_cache(
            settings,
            "same query",
            max_results=3,
            budget=TurnTavilyBudget(settings=settings, user=u1),
            user=u1,
            redis=fake_redis,
        )
        await _search_with_cache(
            settings,
            "same query",
            max_results=3,
            budget=TurnTavilyBudget(settings=settings, user=u2),
            user=u2,
            redis=fake_redis,
        )
    assert search_mock.call_count == 2


@pytest.mark.asyncio
async def test_run_search_dedupes_across_queries_and_respects_limit():
    from app.modules.web_search.search_cache import _run_search

    settings = Settings(web_search_max_results=2, mock_llm_enabled=True)

    async def mock_search(_settings, query, *, max_results, budget=None, user=None, redis=None):
        if query == "q1":
            return [
                WebSearchHit(title="A", url="https://dup", snippet="1"),
                WebSearchHit(title="B", url="https://b", snippet="2"),
            ]
        return [WebSearchHit(title="A dup", url="https://dup", snippet="3")]

    with patch("app.modules.web_search.search_cache._search_with_cache", side_effect=mock_search):
        merged, tried = await _run_search(settings, ["q1", "q2"])

    assert tried == ["q1", "q2"]
    assert len(merged) == 2
    assert merged[0].url == "https://dup"
    assert merged[1].url == "https://b"


@pytest.mark.asyncio
async def test_search_web_falls_back_to_duckduckgo():
    settings = Settings(mock_llm_enabled=False, tavily_api_key="", web_search_fallback_enabled=True)
    ddg_hit = WebSearchHit(title="DDG", url="https://news.example", snippet="story")
    with patch(
        "app.gateways.web_search_gateway._search_duckduckgo",
        AsyncMock(return_value=[ddg_hit]),
    ):
        hits = await search_web(settings, "top news today")
    assert hits[0].title == "DDG"


@pytest.mark.asyncio
async def test_search_web_returns_empty_when_all_providers_fail():
    settings = Settings(mock_llm_enabled=False, tavily_api_key="", web_search_fallback_enabled=True)
    with patch(
        "app.gateways.web_search_gateway._search_duckduckgo",
        AsyncMock(return_value=[]),
    ):
        hits = await search_web(settings, "test query")
    assert hits == []


@pytest.mark.asyncio
async def test_search_duckduckgo_timeout_is_a_failed_search():
    """Stalled DDG must not hang the turn, and a timeout is a failure, not "no results"."""
    import asyncio

    from app.gateways import web_search_gateway as gw

    async def never_finishes(*_args: object, **_kwargs: object) -> list[WebSearchHit]:
        await asyncio.sleep(3600)
        return []

    with (
        patch.object(gw, "_DDG_TIMEOUT_SECONDS", 0.05),
        patch.object(gw, "run_blocking", side_effect=never_finishes),
        pytest.raises(gw.WebSearchUnavailableError),
    ):
        await gw._search_duckduckgo("slow query", max_results=3)


@pytest.mark.asyncio
async def test_a_busy_duckduckgo_fallback_fails_fast_instead_of_queueing():
    """Its threads outlive their waits; with both taken, a search is refused at once."""
    from app.gateways import web_search_gateway as gw

    with (
        patch.object(gw, "has_room", return_value=False),
        patch.object(gw, "run_blocking") as run,
        pytest.raises(gw.WebSearchUnavailableError, match="busy"),
    ):
        await gw._search_duckduckgo("query", max_results=3)
    run.assert_not_called()


@pytest.mark.asyncio
async def test_search_with_cache_reuses_redis(fake_redis):
    from app.modules.web_search.search_cache import _search_with_cache

    settings = Settings(web_search_cache_ttl=300, mock_llm_enabled=True)
    with patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis):
        first = await _search_with_cache(settings, "cached query", max_results=3)
        second = await _search_with_cache(settings, "cached query", max_results=3)
    assert len(first) >= 1
    assert second == first


@pytest.mark.asyncio
async def test_search_with_cache_honors_injected_redis():
    from app.modules.web_search.search_cache import _search_with_cache

    injected = AsyncMock()
    injected.get = AsyncMock(return_value=None)
    injected.set = AsyncMock(return_value=True)
    injected.delete = AsyncMock(return_value=1)

    settings = Settings(web_search_cache_ttl=300, mock_llm_enabled=True)
    hit = WebSearchHit(title="Hit", url="https://example.com", snippet="snippet")
    with (
        patch(
            "app.modules.web_search.search_cache.get_redis_client",
            side_effect=AssertionError("should use injected redis"),
        ),
        patch(
            "app.modules.web_search.search_cache.web_search_gateway.search_web",
            AsyncMock(return_value=[hit]),
        ),
    ):
        results = await _search_with_cache(
            settings,
            "injected query",
            max_results=3,
            redis=injected,
        )

    assert results == [hit]
    injected.get.assert_awaited()
    injected.set.assert_awaited()
    injected.delete.assert_awaited()


def test_search_cache_key_includes_max_results():
    from app.modules.web_search.search_cache import _search_cache_key

    assert _search_cache_key("Foo", 3) != _search_cache_key("Foo", 5)
    assert _search_cache_key("Foo", 3) == _search_cache_key("foo", 3)


def test_search_cache_key_includes_user_id():
    from app.modules.web_search.search_cache import _search_cache_key

    assert _search_cache_key("Foo", 3, user_id="a") != _search_cache_key("Foo", 3, user_id="b")
    assert _search_cache_key("Foo", 3) == _search_cache_key("Foo", 3, user_id="anon")


@pytest.mark.asyncio
async def test_search_with_cache_separate_entries_per_max_results(fake_redis):
    from app.modules.web_search.search_cache import _search_with_cache

    settings = Settings(web_search_cache_ttl=300, mock_llm_enabled=True)
    hit = WebSearchHit(title="Hit", url="https://example.com", snippet="snippet")
    search_mock = AsyncMock(return_value=[hit])
    with (
        patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis),
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", search_mock),
    ):
        await _search_with_cache(settings, "same query", max_results=1)
        await _search_with_cache(settings, "same query", max_results=5)

    assert search_mock.call_count == 2
    assert search_mock.call_args_list[0].kwargs["max_results"] == 1
    assert search_mock.call_args_list[1].kwargs["max_results"] == 5


@pytest.mark.asyncio
async def test_search_with_cache_single_flight_on_miss(fake_redis):
    import asyncio

    from app.modules.web_search.search_cache import _search_with_cache

    settings = Settings(web_search_cache_ttl=300, mock_llm_enabled=True)
    call_count = 0

    async def slow_search(_settings, _query, *, max_results=5, skip_tavily=False):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.25)
        return [
            WebSearchHit(title="Hit", url="https://example.com", snippet="snippet"),
        ]

    with (
        patch("app.modules.web_search.search_cache.get_redis_client", return_value=fake_redis),
        patch("app.modules.web_search.search_cache.web_search_gateway.search_web", slow_search),
    ):
        results = await asyncio.gather(
            *[_search_with_cache(settings, "same query", max_results=3) for _ in range(3)]
        )

    assert call_count == 1
    assert all(result == results[0] for result in results)
