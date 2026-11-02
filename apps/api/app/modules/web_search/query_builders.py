"""Build Tavily/DuckDuckGo queries from user text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search.geo_intent import is_geo_query
from app.modules.web_search.patterns import (
    _CLARIFICATION,
    _GENERIC_NEWS_QUERY,
    _NEWS,
    _ONGOING,
    _QUERY_PREFIX,
    _SPORTS,
    _TEAM_POSSESSIVE_SCORE,
    _TEAM_SCORE,
    _WORLD_CUP,
    asks_for_prior_subject,
    collapse_ws,
)
from app.modules.web_search.subject import resolve_search_subject
from app.services import time_context as time_context_service


def _yesterday_label(user_timezone: str | None) -> str:
    tz = time_context_service.resolve_timezone(user_timezone)
    yesterday = datetime.now(tz) - timedelta(days=1)
    return yesterday.strftime("%B %d %Y")


def _yesterday_iso(user_timezone: str | None) -> str:
    tz = time_context_service.resolve_timezone(user_timezone)
    yesterday = datetime.now(tz) - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def _today_label(user_timezone: str | None) -> str:
    tz = time_context_service.resolve_timezone(user_timezone)
    return datetime.now(tz).strftime("%B %d %Y")


def _today_iso(user_timezone: str | None) -> str:
    tz = time_context_service.resolve_timezone(user_timezone)
    return datetime.now(tz).strftime("%Y-%m-%d")


def anchor_news_query_to_today(query: str, user_timezone: str | None) -> str:
    """Make a current-news search name the actual local calendar date."""
    return f"{query.strip()} {_today_label(user_timezone)} {_today_iso(user_timezone)}".strip()


def is_current_news_request(text: str) -> bool:
    topical_update = re.search(
        r"\b(?:news|headlines?|stories|developments?|updates?|current events|happening)\b",
        text,
        re.IGNORECASE,
    )
    return bool(
        (_NEWS.search(text) or topical_update)
        and re.search(r"\b(?:today|current|latest|right now)\b", text, re.IGNORECASE)
    )


def is_news_today_request(text: str) -> bool:
    """Return whether the user explicitly constrained news to this day."""
    topical_update = re.search(
        r"\b(?:news|headlines?|stories|developments?|updates?|current events|happening)\b",
        text,
        re.IGNORECASE,
    )
    return bool(
        (_NEWS.search(text) or topical_update)
        and re.search(r"\b(?:today|right now)\b", text, re.IGNORECASE)
    )


def _today_date_markers(now: datetime) -> set[str]:
    """Padded and unpadded labels. `_today_label` emits `October 01 2026`."""
    raw = (
        now.strftime("%Y-%m-%d"),
        now.strftime("%B %d, %Y"),
        now.strftime("%B %d %Y"),
        now.strftime("%B %d"),
        now.strftime("%b %d, %Y"),
        now.strftime("%b %d"),
    )
    markers: set[str] = set()
    for item in raw:
        folded = item.casefold()
        markers.add(folded)
        markers.add(folded.replace(" 0", " "))
    return markers


def _blob_has_date_marker(blob: str, marker: str) -> bool:
    """`October 1` must not match `October 15`."""
    start = 0
    while True:
        at = blob.find(marker, start)
        if at < 0:
            return False
        end = at + len(marker)
        if end >= len(blob) or not blob[end].isdigit():
            return True
        start = at + 1


def filter_hits_to_today(hits: list[WebSearchHit], user_timezone: str | None) -> list[WebSearchHit]:
    """Keep only current-news hits that name today's local date or were published today."""
    from app.modules.web_search.source_dates import published_day

    tz = time_context_service.resolve_timezone(user_timezone)
    now = datetime.now(tz)
    markers = _today_date_markers(now)
    return [
        hit
        for hit in hits
        if published_day(hit.published, user_timezone) == now.date()
        or any(
            _blob_has_date_marker(f"{hit.title} {hit.snippet}".casefold(), marker)
            for marker in markers
        )
    ]


def _world_cup_queries(
    *, today: str, yesterday: str, yesterday_iso: str, today_iso: str
) -> list[str]:
    return [
        f"FIFA World Cup 2026 live scores results {today}",
        f"FIFA World Cup 2026 match results scores {yesterday}",
        f"World Cup 2026 group stage results {yesterday_iso}",
        f"World Cup 2026 scores {today_iso}",
    ]


_TEMPORAL_TEAM_WORDS = frozenset({"yesterday", "today", "tomorrow", "tonight", "week", "weekend"})
_TEAM_FILLER = frozenset({"show", "me", "the", "a", "an", "my", "our"})


def _normalize_team_label(raw: str) -> str:
    label = collapse_ws(raw).strip("?.!")
    # No ``\s+`` — input is whitespace-collapsed (CodeQL py/polynomial-redos).
    label = re.sub(r"(?: game| match| scores?| results?| fixture)s?$", "", label, flags=re.I)
    label = re.sub(r"(?:'s|s)$", "", label, flags=re.I)
    return label.strip()


def _is_plausible_team_label(label: str) -> bool:
    """Reject temporal phrases mis-parsed as teams (\"yesterdays game\")."""
    tokens = [t for t in label.lower().split() if t not in _TEAM_FILLER]
    if not tokens:
        return False
    if tokens[0] in _TEMPORAL_TEAM_WORDS:
        return False
    return True


def _extract_team_subject(cleaned: str) -> str | None:
    if not (_TEAM_SCORE.search(cleaned) or _TEAM_POSSESSIVE_SCORE.search(cleaned)):
        return None
    for pattern in (
        r"^(?P<team>.+?)\s+(?:game|match|scores?|results?|fixture)s?\s*[?.!]*$",
        r"^(?P<team>.+?)\s+(?:game|match)\s+score\s*[?.!]*$",
    ):
        match = re.match(pattern, cleaned, flags=re.I)
        if match:
            team = _normalize_team_label(match.group("team"))
            if team and len(team.split()) <= 6 and _is_plausible_team_label(team):
                return team
    fallback = _normalize_team_label(cleaned) or None
    if fallback and _is_plausible_team_label(fallback):
        return fallback
    return None


def _team_score_queries(team: str) -> list[str]:
    return [
        f"{team} national team football latest match score result",
        f"{team} football latest match score result",
        f"{team} World Cup 2026 qualified teams list",
    ]


def _is_team_specific_sports_query(cleaned: str) -> bool:
    if _WORLD_CUP.search(cleaned):
        return False
    return (
        _TEAM_SCORE.search(cleaned) is not None
        or _TEAM_POSSESSIVE_SCORE.search(cleaned) is not None
    )


def _geo_queries(cleaned: str) -> list[str]:
    query = _QUERY_PREFIX.sub("", cleaned.strip()).strip(" ?.!")
    primary = query or cleaned
    return [primary, f"{primary} official website address"]


def build_search_queries(
    text: str,
    *,
    user_timezone: str | None = None,
    prior_user_messages: list[str] | None = None,
) -> list[str]:
    subject = resolve_search_subject(text, prior_user_messages=prior_user_messages)
    query = _QUERY_PREFIX.sub("", subject.strip())
    cleaned = query.strip(" ?.!")
    current = collapse_ws(text)
    yesterday = _yesterday_label(user_timezone)
    yesterday_iso = _yesterday_iso(user_timezone)
    today = _today_label(user_timezone)
    today_iso = _today_iso(user_timezone)

    if _GENERIC_NEWS_QUERY.match(cleaned):
        return [anchor_news_query_to_today("top news today", user_timezone)]

    if _WORLD_CUP.search(current) or (
        _WORLD_CUP.search(subject) and (_ONGOING.search(current) or _CLARIFICATION.search(current))
    ):
        return _world_cup_queries(
            today=today,
            yesterday=yesterday,
            yesterday_iso=yesterday_iso,
            today_iso=today_iso,
        )

    # Generic "yesterday + sports" must NOT force World Cup — that stole team
    # queries like "did the Lakers win yesterday". WC only via _WORLD_CUP above.

    team = _extract_team_subject(cleaned)
    if team and _is_team_specific_sports_query(cleaned):
        return _team_score_queries(team)

    if _SPORTS.search(cleaned):
        return [
            f"{cleaned} scores results {yesterday}",
            f"{cleaned} latest match result",
        ]

    if asks_for_prior_subject(current) and prior_user_messages:
        return build_search_queries(
            subject,
            user_timezone=user_timezone,
            prior_user_messages=None,
        )

    if _CLARIFICATION.search(current) and prior_user_messages:
        return build_search_queries(
            subject,
            user_timezone=user_timezone,
            prior_user_messages=None,
        )

    if is_geo_query(subject) or is_geo_query(current):
        return _geo_queries(cleaned or current)

    fallback = cleaned or current
    if fallback and is_current_news_request(current):
        fallback = anchor_news_query_to_today(fallback, user_timezone)
    return [fallback] if fallback else []
