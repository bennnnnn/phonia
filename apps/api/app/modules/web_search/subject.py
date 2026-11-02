"""Resolve the searchable subject for follow-up turns."""

from __future__ import annotations

from app.modules.web_search.command import search_command
from app.modules.web_search.patterns import (
    _CLARIFICATION,
    _NEWS,
    _SHORT_FOLLOWUP_WORDS,
    _SPORTS,
    _WORLD_CUP,
    asks_for_prior_subject,
    collapse_ws,
    is_correspondence_request,
    looks_like_math_or_code,
)

_MIN_QUERY_WORDS = 3


def collect_prior_user_messages(
    prompt_messages: list[dict[str, str]],
    current: str,
) -> list[str]:
    user_msgs = [str(m.get("content") or "") for m in prompt_messages if m.get("role") == "user"]
    if user_msgs and user_msgs[-1].strip() == current.strip():
        user_msgs = user_msgs[:-1]
    return [msg for msg in user_msgs if msg.strip()]


def last_assistant_content(prompt_messages: list[dict[str, str]]) -> str | None:
    """Most recent assistant body in the prompt window, if any."""
    for msg in reversed(prompt_messages):
        if msg.get("role") == "assistant":
            text = str(msg.get("content") or "").strip()
            return text or None
    return None


def stands_as_query(message: str) -> bool:
    """A prior line that can stand as a query: not "Wrong", "ok", or another command."""
    cleaned = collapse_ws(message)
    return len(cleaned.split()) >= _MIN_QUERY_WORDS and not asks_for_prior_subject(cleaned)


def _prior_searchable_topic(prior_user_messages: list[str] | None) -> str | None:
    if not prior_user_messages:
        return None
    for msg in reversed(prior_user_messages):
        cleaned = collapse_ws(msg)
        if not cleaned or asks_for_prior_subject(cleaned):
            continue
        # A draft request ("write a text … at 2pm today") is not a search topic,
        # and neither is a sum or a code question ("scores = [78, 92]").
        if is_correspondence_request(cleaned) or looks_like_math_or_code(cleaned):
            continue
        if (
            _topic_needs_search(cleaned)
            or _SPORTS.search(cleaned)
            or _WORLD_CUP.search(cleaned)
            or _NEWS.search(cleaned)
        ):
            return cleaned
    return None


def resolve_search_subject(
    user_content: str,
    *,
    prior_user_messages: list[str] | None = None,
) -> str:
    cleaned = collapse_ws(user_content)
    command = search_command(cleaned)
    if command is not None and command.subject:
        return command.subject
    if asks_for_prior_subject(cleaned) and prior_user_messages:
        # Without the model's reading of the conversation, the last line that
        # can stand alone. "Wrong" or "no" before "do a search" is not a query.
        for msg in reversed(prior_user_messages):
            if stands_as_query(msg):
                return collapse_ws(msg)
        for msg in reversed(prior_user_messages):
            prior = collapse_ws(msg)
            if prior and not asks_for_prior_subject(prior):
                return prior
    if prior_user_messages and (
        len(cleaned.split()) <= _SHORT_FOLLOWUP_WORDS or _CLARIFICATION.search(cleaned)
    ):
        prior_topic = _prior_searchable_topic(prior_user_messages)
        if prior_topic:
            return prior_topic
    return cleaned


def _topic_needs_search(text: str) -> bool:
    from app.modules.web_search.detection import needs_web_search

    return needs_web_search(text, prior_user_messages=None)
