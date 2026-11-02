"""Decide whether a turn needs live web search."""

from __future__ import annotations

import itertools
import re

from app.core.config import Settings
from app.modules.turn_reading.chart import chart_of_public_facts
from app.modules.turn_reading.coding import has_code_syntax
from app.modules.turn_reading.locale_cues import has_locale_cue
from app.modules.turn_reading.personal import is_personal_disclosure_turn
from app.modules.turn_reading.routing import (
    is_lightweight_chat_turn,
    is_short_confirmation,
    prior_looks_like_offer,
)
from app.modules.turn_reading.teaching import is_standing_preference
from app.modules.web_search.asks_nothing import asks_nothing_to_look_up
from app.modules.web_search.capability_ask import asks_whether_it_searches
from app.modules.web_search.chat_bound import answers_a_check, works_from_the_chat
from app.modules.web_search.command import asks_to_search, search_command
from app.modules.web_search.geo_intent import is_geo_query, is_short_letter_answer
from app.modules.web_search.live_asks import (
    asks_for_a_price,
    asks_for_entry_rules,
    asks_for_job_listings,
    asks_for_official_charges,
)
from app.modules.web_search.officeholder import asks_who_holds_office
from app.modules.web_search.patterns import (
    _CLARIFICATION,
    _EXPLICIT_SEARCH,
    _LATEST_NEWS,
    _NEW_PRODUCT,
    _NEWS,
    _ONGOING,
    _OWN_CALENDAR,
    _PERSONAL_PLANNING,
    _REMINDER_TURN,
    _SHORT_FOLLOWUP_WORDS,
    _SKIP,
    _SPORTS,
    _SPORTS_LOOKUP,
    _TEAM_POSSESSIVE_SCORE,
    _TEAM_SCORE,
    _WORLD_CUP,
    _YESTERDAY,
    asks_for_prior_subject,
    collapse_ws,
    has_recency,
    is_correspondence_request,
    is_word_problem,
)
from app.modules.web_search.place_answer import question_in_given_place
from app.modules.web_search.release_asks import asks_if_released
from app.modules.web_search.search_word import is_search_word
from app.modules.web_search.subject import (
    _prior_searchable_topic,
    resolve_search_subject,
    stands_as_query,
)
from app.modules.web_search.weather import WEATHER_NOT_A_FORECAST, is_weather_request
from app.services import time_context as time_context_service
from app.services.text_normalize import fold_token

# Questions about the user's own stored profile must be answered from memory,
# not by searching the public web. Keep this deliberately narrower than every
# first-person question: "find jobs for me" or "restaurants near me" may still
# need live results, while these clauses ask Recall to repeat a personal fact.
_PERSONAL_MEMORY_QUESTION = re.compile(
    r"(?:"
    r"\bwhere\s+(?:do|did)\s+i\s+(?:currently\s+)?work"
    r"(?:\s+(?:currently|now|right\s+now))?\b"
    r"|\bwho\s+do\s+i\s+(?:currently\s+)?work\s+for\b"
    r"|\b(?:what|which)\s+company\s+(?:do\s+i\s+work\s+(?:for|at)"
    r"|am\s+i\s+(?:currently\s+)?(?:working\s+(?:for|at)|employed\s+(?:by|at)))\b"
    r"|\bwhere\s+am\s+i\s+(?:currently\s+)?employed\b"
    r"|\bwhat(?:'s|\s+is|\s+was)\s+my\s+(?:current\s+)?"
    r"(?:job|role|title|employer|company|occupation|profession)\b"
    r"(?=\s*(?:[?.!,]|$|\band\b))"
    r"|\b(?:what|which)\s+(?:company|job|role|employer)\s+(?:am|was)\s+i\s+"
    r"(?:considering|targeting|pursuing|interested\s+in|moving\s+to|"
    r"planning\s+to\s+join|trying\s+to\s+join|hoping\s+to\s+join)\b"
    r"|\bwhat(?:'s|\s+is|\s+was)\s+my\s+"
    r"(?:current\s+|future\s+|career\s+|long[- ]term\s+)?"
    r"(?:goal|target|aspiration|plan)\b"
    r"(?=\s*(?:[?.!,]|$|\band\b))"
    r"|\b(?:do|can)\s+you\s+remember\s+(?:where|who|what)\s+i\b"
    r"|\bwhat\s+(?:do|did)\s+you\s+(?:remember|know)\s+about\s+my\s+"
    r"(?:job|work|career|role|employer|company|goals?|plans?)\b"
    r")",
    re.IGNORECASE,
)


_SEARCH_PLACES = frozenset({"google", "googling", "online", "web", "internet", "browse"})


def _offered_a_search(prior_assistant: str | None) -> bool:
    """The last reply offered to search: "I can search the web for that if you'd like"."""
    if not prior_looks_like_offer(prior_assistant):
        return False
    words = [fold_token(w) for w in collapse_ws(prior_assistant or "")[-400:].split()]
    pairs = itertools.pairwise(words)
    return any(is_search_word(w) or w in _SEARCH_PLACES for w in words) or any(
        first == "look" and then in {"it", "that", "into", "up"} for first, then in pairs
    )


def asks_only_whether_it_searches(
    text: str,
    *,
    prior_user_messages: list[str] | None = None,
    prior_assistant: str | None = None,
) -> bool:
    """ "Can you search the web?" with nothing in the chat to search: a question about Recall.

    Read against the line a search would use (``resolve_search_subject``), not any earlier
    one: after "who won the bears game yesterday" the same words ask for that search, but
    "Show me how u work" after it is what a search would send. An offer to search
    ("Should I check online?") asks for one too, when that line can stand as a query
    ("hi" cannot).
    """
    if not asks_whether_it_searches(text):
        return False
    cleaned = collapse_ws(text)
    line = resolve_search_subject(cleaned, prior_user_messages=prior_user_messages)
    if not prior_user_messages or line == cleaned:
        return True
    if _prior_searchable_topic([line]) is not None:
        return False
    return not (_offered_a_search(prior_assistant) and stands_as_query(line))


def web_search_skip(
    text: str,
    *,
    prior_user_messages: list[str] | None = None,
    prior_assistant: str | None = None,
) -> bool:
    """Hard no — never run web search or the classifier."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return True
    # "Can you search the web?" asks about Recall: the reply says yes, nothing is searched.
    if asks_only_whether_it_searches(
        cleaned, prior_user_messages=prior_user_messages, prior_assistant=prior_assistant
    ):
        return True
    # "search", "google it", "can't you look it up?": an explicit request is never chitchat.
    if asks_to_search(cleaned):
        return False
    # "Make a graph of USD to ETB this year" makes something, from facts it must find.
    if chart_of_public_facts(cleaned):
        return False
    if is_word_problem(cleaned) and not is_weather_request(cleaned):
        return True
    # "Great job today", "write a poem about today": a time word, nothing to find.
    if asks_nothing_to_look_up(cleaned):
        return True
    follow_up = bool(prior_user_messages) or prior_looks_like_offer(prior_assistant)
    if len(cleaned) < 4 and not (is_short_confirmation(cleaned) and follow_up):
        return True
    confirming = is_short_confirmation(cleaned) and follow_up
    # Only a yes to an offer may search; "no" / "got it" never do, question or not.
    if not confirming and is_lightweight_chat_turn(cleaned):
        return True
    # A yes to "Does that make sense?", "give me a practice problem", "summarize what we
    # covered": the chat answers it, and a search wrapped such replies in pages they had
    # nothing to do with ("Yes" searched the band Yes). A live ask beside one still searches.
    if (
        answers_a_check(cleaned, prior_assistant) or works_from_the_chat(cleaned)
    ) and not web_search_fast_yes(cleaned, prior_user_messages=prior_user_messages):
        return True
    if is_short_letter_answer(cleaned):
        return True
    # "When teaching me, use examples" sets how to answer; there is nothing to look up.
    if is_personal_disclosure_turn(cleaned) or is_standing_preference(cleaned):
        return True
    if _PERSONAL_MEMORY_QUESTION.search(cleaned):
        return True
    if time_context_service.is_local_now_question(cleaned):
        return True
    if time_context_service.is_location_question(cleaned):
        return True
    if _SKIP.search(cleaned):
        return True
    # "Under the weather today", "a poem about the weather": a figure of speech.
    if WEATHER_NOT_A_FORECAST.search(cleaned) and not is_weather_request(cleaned):
        return True
    if _REMINDER_TURN.search(cleaned):
        return True
    if _PERSONAL_PLANNING.search(cleaned):
        return True
    return bool(_OWN_CALENDAR.search(cleaned)) or has_locale_cue(cleaned, "calendar")


def web_search_fast_yes(
    text: str,
    *,
    prior_user_messages: list[str] | None = None,
) -> bool:
    """Obvious yes — skip the classifier."""
    cleaned = collapse_ws(text)
    if asks_for_prior_subject(cleaned):
        return bool(prior_user_messages)
    command = search_command(cleaned)
    if command is not None and command.subject:
        return True
    if _EXPLICIT_SEARCH.search(cleaned):
        return True
    if _NEWS.search(cleaned) or _LATEST_NEWS.search(cleaned):
        return True
    # Openings, prices and visa rules change: the classifier alone used to decide them.
    if asks_for_job_listings(cleaned) or asks_for_a_price(cleaned) or asks_for_entry_rules(cleaned):
        return True
    # What an institution charges in fees, levies and duties is read off its schedule.
    if asks_for_official_charges(cleaned):
        return True
    # A chart of facts the user did not give is drawn from a search, not from memory.
    if chart_of_public_facts(cleaned):
        return True
    # Conditions and products change after training; no model call can know them.
    if is_weather_request(cleaned) or _NEW_PRODUCT.search(cleaned):
        return True
    # "Is iPhone 19 out?" was told the iPhone 16 was current, two models late.
    if asks_if_released(cleaned):
        return True
    # So do officeholders: "who is the president of Ethiopia" was answered from memory.
    if asks_who_holds_office(cleaned):
        return True
    if _SPORTS_LOOKUP.search(cleaned):
        return True
    if _TEAM_SCORE.search(cleaned) or _TEAM_POSSESSIVE_SCORE.search(cleaned):
        return True
    if _YESTERDAY.search(cleaned) and _SPORTS.search(cleaned):
        return True
    if _WORLD_CUP.search(cleaned) and (_ONGOING.search(cleaned) or _SPORTS.search(cleaned)):
        return True
    subject = resolve_search_subject(cleaned, prior_user_messages=prior_user_messages)
    if _SPORTS_LOOKUP.search(subject):
        return True
    if _YESTERDAY.search(subject) and _SPORTS.search(subject):
        return True
    if _WORLD_CUP.search(subject) and (_ONGOING.search(cleaned) or _SPORTS.search(subject)):
        return True
    if is_geo_query(cleaned):
        return True
    return False


# "Current" in a circuit is amps, and "100 days from tomorrow" is counting:
# neither is news.
_CURRENT = re.compile(r"\bcurrent\b", re.IGNORECASE)
_CIRCUIT = re.compile(
    r"\bohms?\b|\u03a9|\bvolts?\b|\b\d+(?:\.\d+)?\s*k?v\b|resist|circuit|\bseries\b"
    r"|\bparallel\b|battery|\bamps?\b|ampere|capacitor|inductor|kirchhoff",
    re.IGNORECASE,
)
_DATE_ARITHMETIC = re.compile(
    r"\b\d+\s+(?:days?|weeks?|months?|years?)\s+(?:from|after|before|ago|since|until)\b"
    r"|\bwhat\s+day\s+(?:of\s+the\s+week\s+)?(?:will\s+it\s+be|was\s+it|is\s+it)\s+\d+",
    re.IGNORECASE,
)


_TELLS = re.compile(
    r"(?:ugh|omg|lol|haha|so|well|just|i|i'm|im|i've|my|we|we're|today\s+i)\b", re.IGNORECASE
)
# "The boiling point of my patience is low today", "the battery in my head is
# flat today": the sentence says how something of the user's is, however it
# opens. "The exchange rate in my country today" says nothing; it asks.
_ABOUT_THE_USER = re.compile(
    r"(?:the|a|an|this|that|these|those)\s+(?:[\w'-]+\s+){0,4}?(?:of|in|on|inside)\s+"
    r"(?:my|our)\s+(?:[\w'-]+\s+){1,2}?"
    r"(?:is|are|was|were|has|have|had|feels?|seems?|hit|went|got|keeps?)\b",
    re.IGNORECASE,
)


def _tells_about_the_user(text: str) -> bool:
    """A statement about something of the user's: its "today" is not news."""
    return "?" not in text and _ABOUT_THE_USER.match(text) is not None


def needs_web_search_heuristic(
    text: str,
    *,
    prior_user_messages: list[str] | None = None,
) -> bool:
    """Regex fallback for follow-ups and recency when the classifier is off or fails."""
    cleaned = collapse_ws(text)
    electric = _CURRENT.search(cleaned) and _CIRCUIT.search(cleaned)
    if electric or _DATE_ARITHMETIC.search(cleaned) or is_correspondence_request(cleaned):
        return False
    # "Traceback (most recent call last)" is not recency.
    if has_code_syntax(text):
        return False
    if _CLARIFICATION.search(cleaned) and prior_user_messages:
        return _prior_searchable_topic(prior_user_messages) is not None
    if prior_user_messages and len(cleaned.split()) <= _SHORT_FOLLOWUP_WORDS:
        if _prior_searchable_topic([prior_user_messages[-1]]) is not None:
            return True
    if has_recency(cleaned) and "?" in cleaned:
        return True
    # "ugh forgot my umbrella today and its pouring" tells; it asks nothing.
    tells = _TELLS.match(cleaned) or _tells_about_the_user(cleaned)
    if has_recency(cleaned) and len(cleaned.split()) >= 6 and not tells:
        return True
    return False


def needs_web_search(
    text: str,
    *,
    prior_user_messages: list[str] | None = None,
    prior_assistant: str | None = None,
) -> bool:
    """Sync gate: skip + fast-path + heuristic (tests and legacy callers)."""
    # "I'm in Indianapolis" after "I don't have your location yet": the earlier question there.
    prior = prior_user_messages[-1] if prior_user_messages else None
    if question_in_given_place(text, prior, prior_assistant) is not None:
        return True
    if web_search_skip(
        text, prior_user_messages=prior_user_messages, prior_assistant=prior_assistant
    ):
        return False
    if web_search_fast_yes(text, prior_user_messages=prior_user_messages):
        return True
    return needs_web_search_heuristic(text, prior_user_messages=prior_user_messages)


def should_web_search(
    text: str,
    settings: Settings,
    *,
    prior_user_messages: list[str] | None = None,
    prior_assistant: str | None = None,
) -> bool:
    """Whether a turn needs live results: search on, then skip, fast path and heuristic.

    An LLM classifier used to run for live cues and questions about the world; it was
    off in production (time to first token), so production read this heuristic.
    """
    if not settings.web_search_enabled:
        return False
    return needs_web_search(
        text, prior_user_messages=prior_user_messages, prior_assistant=prior_assistant
    )
