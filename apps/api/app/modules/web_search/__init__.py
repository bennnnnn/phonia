"""Live web search: whether a turn needs it, its queries, and the tool loop's search.

The package stays lazy: the SymPy pool's workers read a message with ``detection``
and must not load the search cache, which brings the ORM and the database with it.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.web_search.capability_ask import asks_whether_it_searches
    from app.modules.web_search.detection import (
        asks_only_whether_it_searches,
        needs_web_search,
        should_web_search,
        web_search_fast_yes,
        web_search_skip,
    )
    from app.modules.web_search.formatting import (
        AMBIGUOUS_NEARBY_HINT,
        GEO_ACTIVE_LOCATION_HINT,
        GEO_DISTANCE_HINT,
        LOCAL_PLACES_FORMAT_HINT,
        WEB_SEARCH_HINT,
        SearchSource,
        format_places_fence,
        format_search_block,
        format_search_empty_block,
        format_sources_fence,
        sources_payload,
        strip_duplicate_venue_list,
        strip_sources_from_text,
    )
    from app.modules.web_search.geo_intent import (
        format_location_not_set_answer,
        is_ambiguous_local_places_query,
        is_distance_query,
        is_geo_query,
        is_places_list_query,
        is_short_letter_answer,
        names_its_place,
    )
    from app.modules.web_search.homework import (
        asks_about_a_place,
    )
    from app.modules.web_search.query_builders import (
        build_search_queries,
    )
    from app.modules.web_search.recency import (
        wants_dated_results,
    )
    from app.modules.web_search.search_cache import (
        TurnTavilyBudget,
        run_cached_search,
    )
    from app.modules.web_search.subject import (
        resolve_search_subject,
    )
    from app.modules.web_search.tool import (
        WebSearchAdapter,
    )
    from app.modules.web_search.turn_query import (
        search_queries_for_turn,
    )

_EXPORTS = {
    "AMBIGUOUS_NEARBY_HINT": "formatting",
    "GEO_ACTIVE_LOCATION_HINT": "formatting",
    "GEO_DISTANCE_HINT": "formatting",
    "LOCAL_PLACES_FORMAT_HINT": "formatting",
    "SearchSource": "formatting",
    "TurnTavilyBudget": "search_cache",
    "WEB_SEARCH_HINT": "formatting",
    "WebSearchAdapter": "tool",
    "asks_about_a_place": "homework",
    "asks_only_whether_it_searches": "detection",
    "asks_whether_it_searches": "capability_ask",
    "build_search_queries": "query_builders",
    "format_location_not_set_answer": "geo_intent",
    "format_places_fence": "formatting",
    "format_search_block": "formatting",
    "format_search_empty_block": "formatting",
    "format_sources_fence": "formatting",
    "is_ambiguous_local_places_query": "geo_intent",
    "is_distance_query": "geo_intent",
    "is_geo_query": "geo_intent",
    "is_places_list_query": "geo_intent",
    "is_short_letter_answer": "geo_intent",
    "names_its_place": "geo_intent",
    "needs_web_search": "detection",
    "resolve_search_subject": "subject",
    "run_cached_search": "search_cache",
    "search_queries_for_turn": "turn_query",
    "should_web_search": "detection",
    "sources_payload": "formatting",
    "strip_duplicate_venue_list": "formatting",
    "strip_sources_from_text": "formatting",
    "web_search_fast_yes": "detection",
    "web_search_skip": "detection",
    "wants_dated_results": "recency",
}

__all__ = [
    "AMBIGUOUS_NEARBY_HINT",
    "GEO_ACTIVE_LOCATION_HINT",
    "GEO_DISTANCE_HINT",
    "LOCAL_PLACES_FORMAT_HINT",
    "WEB_SEARCH_HINT",
    "SearchSource",
    "TurnTavilyBudget",
    "WebSearchAdapter",
    "asks_about_a_place",
    "asks_only_whether_it_searches",
    "asks_whether_it_searches",
    "build_search_queries",
    "format_location_not_set_answer",
    "format_places_fence",
    "format_search_block",
    "format_search_empty_block",
    "format_sources_fence",
    "is_ambiguous_local_places_query",
    "is_distance_query",
    "is_geo_query",
    "is_places_list_query",
    "is_short_letter_answer",
    "names_its_place",
    "needs_web_search",
    "resolve_search_subject",
    "run_cached_search",
    "search_queries_for_turn",
    "should_web_search",
    "sources_payload",
    "strip_duplicate_venue_list",
    "strip_sources_from_text",
    "wants_dated_results",
    "web_search_fast_yes",
    "web_search_skip",
]

# Seams the chat turn uses to decide on a search and read prior turns.
_MODULE_EXPORTS = ("detection", "subject")


def __getattr__(name: str) -> Any:
    if name in _MODULE_EXPORTS:
        value = import_module(f"app.modules.web_search.{name}")
    else:
        module = _EXPORTS.get(name)
        if module is None:
            raise AttributeError(name)
        value = getattr(import_module(f"app.modules.web_search.{module}"), name)
    globals()[name] = value
    return value
