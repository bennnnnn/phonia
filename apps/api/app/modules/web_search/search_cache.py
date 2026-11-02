"""Cached web search execution via Tavily (+ DuckDuckGo fallback).

Merged hits come back with official and reference sources first
(``source_quality``). Each query is recorded on the turn's budget as answered or
failed, so the turn can say "search failed right now" instead of "no results".

A search about now (``dated``) also asks for news pages, each with the moment it was
published. "Who won the World Series this year?" found the winners' lists and a table row
"2026 | Tampa Bay Rays | 0 | 1 | Milwaukee Brewers" (2026-10-25): no page said when it was
written, and three replies running said the Rays had won, that the series began "this
Friday" two days after it did, and that Game 1 was a week away. Up to three dated pages
join the general results, one after each, which keep their order and places. The news
search runs beside the general one and may take at most half a second longer.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import logging
from dataclasses import asdict, dataclass, field

from redis.asyncio import Redis

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.core.redis import get_redis_client
from app.gateways import web_search_gateway
from app.gateways.mcp.base import TavilyBudget
from app.gateways.web_search_gateway import WebSearchHit, WebSearchUnavailableError
from app.models.orm import User
from app.modules.web_search.model_match import drop_other_models
from app.modules.web_search.source_quality import is_error_page, rank_by_source
from app.services.quota import counters

logger = logging.getLogger(__name__)


@dataclass
class TurnTavilyBudget:
    """One Tavily reservation shared across every query in a single search turn.

    A turn fans out into several queries (e.g. sports/news build 3-4) that run
    concurrently. Reserving per query would let one turn spend 3-4 of the
    user's daily Tavily searches instead of one. This reserves at most once per
    turn, lazily (only when a query actually misses cache and is about to hit
    the network), and every concurrent query reuses that single decision. The
    lock makes the check-then-reserve atomic across the gathered coroutines so
    two cache-missing queries can't both reserve. A chat turn passes one budget
    to every search it runs (its ``ToolContext.tavily_budget``).

    It is also the turn's search ledger: each query that reached the providers
    is recorded as answered (hits or none) or failed, and ``search_failed`` says
    every one of them failed.
    """

    settings: Settings
    user: User | None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _decided: bool = False
    _skip_tavily: bool = False
    _answered: int = 0
    _failed: int = 0

    def record_search(self, *, failed: bool) -> None:
        if failed:
            self._failed += 1
        else:
            self._answered += 1

    @property
    def search_failed(self) -> bool:
        """The turn searched and every search errored: "tried and failed", not "nothing"."""
        return self._failed > 0 and self._answered == 0

    async def skip_tavily(self, redis: Redis) -> bool:
        """Whether this turn must skip Tavily (daily cap, no user, or Redis fail).

        Reserves at most once. DuckDuckGo stays uncapped (latency only) when
        this returns True. A missing user or a Redis error fail closed to DDG
        so we never run Tavily without a counted slot.
        """
        async with self._lock:
            if self._decided:
                return self._skip_tavily
            if self.user is None:
                self._skip_tavily = True
                self._decided = True
                logger.warning("Tavily cap: missing user; DuckDuckGo only")
                return True
            # Only spend the daily Tavily budget when Tavily can actually run.
            # With no key (or web search off) the turn falls back to free,
            # uncapped DuckDuckGo, so reserving here would burn a slot for a
            # search Tavily never performs.
            if not web_search_gateway.is_configured(self.settings):
                self._skip_tavily = False
                self._decided = True
                return False
            try:
                reserved = await counters.reserve("tavily_search", redis, self.user, self.settings)
                self._skip_tavily = not reserved
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Tavily reserve failed; falling back to DuckDuckGo user_id=%s",
                    self.user.id,
                    exc_info=True,
                )
                self._skip_tavily = True
            self._decided = True
            return self._skip_tavily


async def run_cached_search(
    settings: Settings,
    queries: list[str],
    *,
    user: User | None = None,
    redis: Redis | None = None,
    budget: TavilyBudget | None = None,
    dated: bool = False,
) -> tuple[list[WebSearchHit], list[str]]:
    """Public cached + quota-aware search (heuristic augment and MCP tool loop).

    Applies the per-user daily Tavily reservation and Redis result cache so
    model-initiated ``web_search`` calls cannot bypass the heuristic path's cap.
    *budget* is the turn's reservation when the turn may search more than once.
    *dated*: the ask is about now (``recency.wants_dated_results``); the first query
    also runs as a news search, on the same reservation.
    """
    return await _run_search(settings, queries, user=user, redis=redis, budget=budget, dated=dated)


async def _run_search(
    settings: Settings,
    queries: list[str],
    *,
    user: User | None = None,
    redis: Redis | None = None,
    budget: TavilyBudget | None = None,
    dated: bool = False,
) -> tuple[list[WebSearchHit], list[str]]:
    limit = max(1, min(settings.web_search_max_results, 10))
    if not queries:
        return [], []

    # Prefer the turn's budget (MCP may call web_search more than once).
    # Without one: one reservation for this call's fanned-out queries only.
    if budget is None:
        budget = TurnTavilyBudget(settings=settings, user=user)
    news_task = (
        asyncio.ensure_future(
            _search_with_cache(
                settings,
                queries[0],
                max_results=limit,
                budget=budget,
                user=user,
                redis=redis,
                topic=_NEWS,
            )
        )
        if dated
        else None
    )
    try:
        results = await gather_or_cancel(
            *(
                _search_with_cache(
                    settings, query, max_results=limit, budget=budget, user=user, redis=redis
                )
                for query in queries
            )
        )
        general = _merged(list(zip(queries, results, strict=True)), limit)
        if news_task is None:
            return general, list(queries)
        found = await _news_in_time(news_task)
    finally:
        if news_task is not None and not news_task.done():
            news_task.cancel()
    return _alternated(general, _merged([(queries[0], found)], _NEWS_EXTRA)), list(queries)


_NEWS = "news"
# The dated pages a search adds to the general ones, which keep their places.
_NEWS_EXTRA = 3
# How long the news search may run on once the turn's own search is back: it is an
# extra, and never what the reply waits for.
NEWS_GRACE_SECONDS = 0.5


async def _news_in_time(task: asyncio.Future[list[WebSearchHit]]) -> list[WebSearchHit]:
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=NEWS_GRACE_SECONDS)
    except TimeoutError:
        task.cancel()
        return []
    except Exception:
        logger.debug("Dated news search failed", exc_info=True)
        return []


def _merged(found: list[tuple[str, list[WebSearchHit]]], limit: int) -> list[WebSearchHit]:
    """Each query's hits in turn, up to ``limit``, without repeats or error pages."""
    seen_urls: set[str] = set()
    merged: list[WebSearchHit] = []
    for query, hits in found:
        # "Is iPhone 19 out?" also found "Apple to Release iPhone 6 Models Sept. 19".
        for hit in drop_other_models(hits, query):
            key = _key(hit)
            # An error page is no source, and takes no slot a real page could fill.
            if key in seen_urls or is_error_page(hit):
                continue
            seen_urls.add(key)
            merged.append(hit)
            if len(merged) >= limit:
                return rank_by_source(merged)
    return rank_by_source(merged)


def _alternated(general: list[WebSearchHit], news: list[WebSearchHit]) -> list[WebSearchHit]:
    """The general results in their order, each followed by a dated page in the news
    search's own order: the best general page stays first, and none is pushed out."""
    out: list[WebSearchHit] = []
    seen: set[str] = set()
    for pair in itertools.zip_longest(general, news):
        for hit in pair:
            if hit is None or _key(hit) in seen:
                continue
            seen.add(_key(hit))
            out.append(hit)
    return out


def _key(hit: WebSearchHit) -> str:
    return hit.url.strip().lower() or hit.title.strip().lower()


def _search_cache_key(
    query: str, max_results: int, *, user_id: str = "anon", topic: str = "general"
) -> str:
    digest = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:32]
    key = f"websearch:{user_id}:{max_results}:{digest}"
    return key if topic == "general" else f"{key}:{topic}"


async def _search_with_cache(
    settings: Settings,
    query: str,
    *,
    max_results: int,
    budget: TavilyBudget | None = None,
    user: User | None = None,
    redis: Redis | None = None,
    topic: str = "general",
) -> list[WebSearchHit]:
    cleaned = query.strip()
    if not cleaned:
        return []

    user_id = str(user.id) if user is not None else "anon"
    cache_key = _search_cache_key(cleaned, max_results, user_id=user_id, topic=topic)
    # The dated search goes beside the turn's own: whether the turn's search failed is
    # the general search's to say.
    ledger = budget if topic == "general" else None
    cache_redis = redis if redis is not None else get_redis_client()

    def _hits_from_payload(payload: object) -> list[WebSearchHit] | None:
        if not isinstance(payload, list):
            return None
        return [
            WebSearchHit(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("snippet") or ""),
                published=str(item.get("published") or ""),
            )
            for item in payload
            if isinstance(item, dict)
        ]

    async def _cached_hits() -> list[WebSearchHit] | None:
        """This query's cached hits (counted as a search), or None on a miss or error."""
        try:
            cached = await cache_redis.get(cache_key)
            if cached:
                hits = _hits_from_payload(json.loads(cached))
                if hits is not None:
                    _record(ledger, failed=False)
                    return hits
        except Exception:
            logger.debug("Web search cache read failed", exc_info=True)
        return None

    if (hits := await _cached_hits()) is not None:
        return hits

    lock_key = f"{cache_key}:lock"
    acquired = False
    try:
        acquired = bool(await cache_redis.set(lock_key, "1", ex=30, nx=True))
    except Exception:
        logger.debug("Web search lock acquire failed", exc_info=True)

    if not acquired:
        # Another request is fetching this query: wait up to 2s for its result.
        for _ in range(20):
            await asyncio.sleep(0.1)
            if (hits := await _cached_hits()) is not None:
                return hits

    try:
        # Reserve one Tavily slot for the whole turn (shared budget), only now
        # that this query has missed cache and is about to hit the network.
        skip_tavily = await budget.skip_tavily(cache_redis) if budget is not None else False

        try:
            hits = await web_search_gateway.search_web(
                settings,
                cleaned,
                max_results=max_results,
                skip_tavily=skip_tavily,
                **({} if topic == "general" else {"topic": topic}),
            )
        except WebSearchUnavailableError:
            _record(ledger, failed=True)
            return []
        _record(ledger, failed=False)
        if hits:
            try:
                await cache_redis.set(
                    cache_key,
                    json.dumps([asdict(hit) for hit in hits]),
                    ex=max(60, settings.web_search_cache_ttl),
                )
            except Exception:
                logger.debug("Web search cache write failed", exc_info=True)
        return hits
    finally:
        if acquired:
            try:
                await cache_redis.delete(lock_key)
            except Exception:
                logger.debug("Web search lock release failed", exc_info=True)


def _record(budget: TavilyBudget | None, *, failed: bool) -> None:
    if budget is not None:
        budget.record_search(failed=failed)
