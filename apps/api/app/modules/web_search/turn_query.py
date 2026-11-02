"""The query a turn's live search sends, when the tool loop searches before the model.

Most messages are their own query. A request that names its topic ("search
for the meaning of bini") sends the topic. A message that points back ("do a
search", "look it up", "when did she die?") sends what the conversation was
about; sending the literal words searched for "do a search".
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.modules.web_search.command import search_command
from app.modules.web_search.geo_intent import is_geo_query
from app.modules.web_search.officeholder import office_with_subject, office_without_place
from app.modules.web_search.patterns import (
    _CLARIFICATION,
    _SHORT_FOLLOWUP_WORDS,
    asks_for_prior_subject,
    collapse_ws,
)
from app.modules.web_search.place_answer import question_in_given_place
from app.modules.web_search.query_builders import (
    anchor_news_query_to_today,
    anchor_to_location,
    build_search_queries,
    is_current_news_request,
)
from app.modules.web_search.recency import anchor_recency_to_year
from app.modules.web_search.release_asks import release_search_query
from app.modules.web_search.subject import collect_prior_user_messages
from app.services.conversation_reference import resolve_reference, turns_from_prompt
from app.services.text_normalize import fold_token

# Words that stand for someone or something named earlier in the chat.
_REFERENCE_WORDS = frozenset(
    {
        "it",
        "its",
        "that",
        "this",
        "those",
        "these",
        "she",
        "he",
        "her",
        "him",
        "his",
        "they",
        "them",
        "their",
        "there",
    }
)


def _last_assistant_text(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        if message.get("role") == "assistant" and isinstance(message.get("content"), str):
            return str(message["content"])
    return None


def points_back(text: str, prior_user_messages: list[str] | None) -> bool:
    """True when *text* needs the conversation to say what to search."""
    if not prior_user_messages:
        return False
    cleaned = collapse_ws(text)
    if asks_for_prior_subject(cleaned) or _CLARIFICATION.search(cleaned):
        return True
    # "What is the president?" after a chat about Ethiopia: of the chat's subject.
    if office_without_place(cleaned):
        return True
    words = [fold_token(w) for w in cleaned.split()]
    return len(words) <= _SHORT_FOLLOWUP_WORDS and any(w in _REFERENCE_WORDS for w in words)


async def search_queries_for_turn(
    settings: Settings,
    user_text: str,
    messages: list[dict[str, Any]],
    *,
    user_timezone: str | None = None,
    user_location: str | None = None,
) -> list[str]:
    """Queries for this turn's search, best first; never empty for a non-empty message."""
    cleaned = collapse_ws(user_text)
    if not cleaned:
        return []
    command = search_command(cleaned)
    if command is not None and command.subject:
        subject = command.subject
        if is_current_news_request(subject):
            subject = anchor_news_query_to_today(subject, user_timezone)
        else:
            subject = anchor_recency_to_year(subject, cleaned, user_timezone)
        return [subject]
    priors = collect_prior_user_messages(messages, user_text)
    # A place named after "I don't have your location yet" asks the earlier question there.
    asked_there = question_in_given_place(
        cleaned, priors[-1] if priors else None, _last_assistant_text(messages)
    )
    if asked_there is not None:
        return [asked_there]
    if points_back(cleaned, priors):
        resolved = await resolve_reference(
            settings,
            kind="search",
            request=cleaned,
            turns=turns_from_prompt(messages),
        )
        if resolved:
            return [resolved]
        if office_without_place(cleaned):
            return [office_with_subject(cleaned, priors[-1])]
        queries = build_search_queries(
            cleaned,
            user_timezone=user_timezone,
            prior_user_messages=priors,
        )
        if queries:
            return queries
    # "I'm thinking of getting the Pixel 11, is it out yet?" found a company called Thinking
    # Pixel; the ask alone, "is Pixel 11 out yet", found the phone's release.
    release = release_search_query(cleaned)
    if release is not None:
        return [release]
    # "Coffee near me" searched those words and found New York cafés.
    if user_location and is_geo_query(cleaned):
        return [anchor_to_location(cleaned, user_location)]
    if is_current_news_request(cleaned):
        return [cleaned]
    return [anchor_recency_to_year(cleaned, cleaned, user_timezone)]
