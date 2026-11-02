"""Web search — Tavily primary, DuckDuckGo fallback (server-side only).

``search_web`` returns the hits, an empty list when the search answered with
nothing, and raises ``WebSearchUnavailableError`` when it failed (Tavily errored
and DuckDuckGo found nothing, or DuckDuckGo alone errored): "tried and failed"
must not read as "nothing found".
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from app.core.blocking import has_room, run_blocking
from app.core.config import Settings
from app.gateways.http_client import get_pooled_client
from app.gateways.mock_llm import should_mock_search

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_SECONDS = 12.0
# The whole Tavily request, whatever its phases do.
_TAVILY_OVERALL_SECONDS = 15.0
# Bound the DuckDuckGo fallback — a stalled DDG socket must not hang TTFT. Its thread
# (up to three sequential calls) outlives the wait, so the fallback has two threads of
# its own per machine and is skipped, not queued, when both are taken.
_DDG_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class WebSearchHit:
    title: str
    url: str
    snippet: str
    # When the page was published, ISO-8601 in UTC ("2026-10-25T03:30:00+00:00", or a day
    # alone), when the provider says: Tavily's news search does; its general search and
    # DuckDuckGo do not.
    published: str = ""


class WebSearchUnavailableError(Exception):
    """Every search provider tried for a query errored or timed out."""


def is_configured(settings: Settings) -> bool:
    return bool(settings.web_search_enabled and settings.tavily_api_key.strip())


def mock_search_results(query: str, *, max_results: int) -> list[WebSearchHit]:
    return [
        WebSearchHit(
            title=f"Mock search: {query[:80]}",
            url="https://example.com/mock-search",
            snippet=(
                "Mock web search result (set TAVILY_API_KEY in apps/api/.env for live results). "
                "Use this to verify search injection in dev."
            ),
        )
    ][:max_results]


def _is_newsish_query(query: str) -> bool:
    return bool(
        re.search(
            r"\b(news|headlines|happening|world|today|breaking|events|"
            r"scores?|results?|match(?:es)?|soccer|football|fifa|world\s+cup|"
            r"nba|nfl|mlb|nhl|standings|fixture)\b",
            query,
            re.I,
        )
    )


def _ddg_item_to_hit(item: dict[str, object]) -> WebSearchHit | None:
    title = str(item.get("title") or "").strip()
    url = str(item.get("href") or item.get("link") or item.get("url") or "").strip()
    snippet = str(item.get("body") or item.get("content") or "").strip()
    if not title and not snippet:
        return None
    return WebSearchHit(
        title=title or url or "Untitled",
        url=url,
        snippet=snippet[:600],
    )


def _search_duckduckgo_sync(query: str, max_results: int) -> list[WebSearchHit]:
    """DuckDuckGo news then text. Raises when every call it made failed."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        logger.warning("ddgs package not installed")
        raise WebSearchUnavailableError("ddgs not installed") from exc

    hits: list[WebSearchHit] = []
    calls = {"made": 0, "failed": 0}

    def _fetch(items: object) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if len(hits) >= max_results:
                return
            if not isinstance(item, dict):
                continue
            hit = _ddg_item_to_hit(item)
            if hit is not None:
                hits.append(hit)

    def _try(search: Callable[[], Iterable[object]], label: str) -> None:
        calls["made"] += 1
        try:
            _fetch(list(search()))
        except Exception:
            calls["failed"] += 1
            logger.warning("DuckDuckGo %s failed", label)

    try:
        try:
            ddgs_cm = DDGS(timeout=int(_DDG_TIMEOUT_SECONDS))
        except TypeError:
            # Older ddgs builds reject timeout= — still bounded by wait_for below.
            ddgs_cm = DDGS()
        with ddgs_cm as ddgs:
            # Do not log the query anywhere below — it can contain private user
            # content (CodeQL py/clear-text-logging-sensitive-data).
            newsish = _is_newsish_query(query)
            if newsish:
                _try(lambda: ddgs.news(query, max_results=max_results), "news search")
            if not hits:
                _try(lambda: ddgs.text(query, max_results=max_results), "text search")
            if not hits and not newsish:
                _try(lambda: ddgs.news(query, max_results=max_results), "news fallback")
    except Exception as exc:
        logger.exception("DuckDuckGo search failed")
        raise WebSearchUnavailableError("DuckDuckGo failed") from exc
    if not hits and calls["made"] and calls["failed"] == calls["made"]:
        raise WebSearchUnavailableError("every DuckDuckGo call failed")
    return hits


async def _search_duckduckgo(query: str, max_results: int) -> list[WebSearchHit]:
    if not has_room("web_search"):
        # Both fallback threads are still on earlier searches: fail this one fast.
        raise WebSearchUnavailableError("DuckDuckGo fallback busy")
    try:
        return await asyncio.wait_for(
            run_blocking("web_search", _search_duckduckgo_sync, query, max_results),
            timeout=_DDG_TIMEOUT_SECONDS,
        )
    except WebSearchUnavailableError:
        raise
    except Exception as exc:
        # A timeout or provider error is a failed search, not an empty one. Do
        # not log the query — it can contain private user content (CodeQL
        # py/clear-text-logging-sensitive-data).
        logger.warning("DuckDuckGo fallback timed out/failed")
        raise WebSearchUnavailableError("DuckDuckGo timed out") from exc


def _published_at(raw: object) -> str:
    """Tavily's ``published_date`` ("Sat, 24 Oct 2026 10:00:00 GMT") as ISO-8601 in UTC.

    The moment, not its day: a game recap posted at 03:30 GMT on the 25th was written on
    the evening of the 24th in the Americas.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""
    try:
        moment = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return ""
    if moment.tzinfo is None:
        return moment.date().isoformat()
    return moment.astimezone(UTC).isoformat()


async def _search_tavily(
    settings: Settings, query: str, max_results: int, *, topic: str = "general"
) -> list[WebSearchHit]:
    payload: dict[str, object] = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
    }
    if topic != "general":
        payload["topic"] = topic

    try:
        client = get_pooled_client(DEFAULT_TIMEOUT_SECONDS)
        # httpx bounds each phase (connect, write, pool, every read) by itself, so a
        # trickling response could take several times that; this bounds the whole call.
        async with asyncio.timeout(_TAVILY_OVERALL_SECONDS):
            response = await client.post(TAVILY_SEARCH_URL, json=payload)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        # Do not log the query — it can contain private user content (CodeQL
        # py/clear-text-logging-sensitive-data).
        logger.exception("Tavily web search failed")
        raise WebSearchUnavailableError("Tavily failed") from exc

    hits: list[WebSearchHit] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        if not title and not snippet:
            continue
        hits.append(
            WebSearchHit(
                title=title or url or "Untitled",
                url=url,
                snippet=snippet[:600],
                published=_published_at(item.get("published_date")),
            )
        )
    return hits


async def search_web(
    settings: Settings,
    query: str,
    *,
    max_results: int | None = None,
    skip_tavily: bool = False,
    topic: str = "general",
) -> list[WebSearchHit]:
    """Hits for ``query``: Tavily, then DuckDuckGo when Tavily has none.

    ``topic="news"`` asks Tavily alone for news pages, each with the day it was
    published; with no Tavily it finds nothing, since the turn's own search runs beside it.
    Raises ``WebSearchUnavailableError`` when the search failed rather than found nothing.
    """
    cleaned = query.strip()
    if not cleaned:
        return []

    limit = max_results if max_results is not None else settings.web_search_max_results
    limit = max(1, min(limit, 10))

    if not settings.web_search_enabled:
        return []

    # Mock mode without a Tavily key (development without keys, and the tests) searches
    # nothing real: it ran DuckDuckGo first, so a test could reach the internet before
    # getting mock results. With a key, mock mode searches for real.
    if should_mock_search(settings):
        return [] if topic != "general" else mock_search_results(cleaned, max_results=limit)

    # Tavily is the search of record: when it errored, DuckDuckGo finding nothing
    # does not show there is nothing (it comes back empty when it throttles).
    primary_failed = False
    fallback_failed = False
    tavily_tried = not skip_tavily and bool(settings.tavily_api_key.strip())
    if topic != "general":
        return await _search_tavily(settings, cleaned, limit, topic=topic) if tavily_tried else []
    if tavily_tried:
        try:
            hits = await _search_tavily(settings, cleaned, limit)
        except WebSearchUnavailableError:
            primary_failed = True
        else:
            if hits:
                return hits

    if settings.web_search_fallback_enabled:
        try:
            hits = await _search_duckduckgo(cleaned, limit)
        except WebSearchUnavailableError:
            fallback_failed = True
        else:
            if hits:
                return hits

    if primary_failed or (fallback_failed and not tavily_tried):
        raise WebSearchUnavailableError("the search of record failed")
    return []
