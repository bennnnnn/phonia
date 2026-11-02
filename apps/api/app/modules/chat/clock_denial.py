"""A short reply that says it cannot see the clock, when the user asked the clock.

The finalize pass swaps such a reply for the clock the app always has
(``finalize_text.fix_clock``). The user's message decides, not the reply's wording: it
must ask the local clock in so many words ("what time is it", "whats the time rn", "do
you know what time it is", "today's date") and name nothing else live. Read from the
reply, "I don't have access to real-time information, so I can't tell you tomorrow's
weather in Chicago" became "Sunday, October 25, 2026, 3:22:15 PM EDT" (live chat,
2026-10-25), and two review rounds still found replies about store hours, the time in
Tokyo or daylight saving swapped, and true clock denials missed.
"""

from __future__ import annotations

import re

from app.services.text_normalize import collapse_ws, straighten_apostrophes
from app.services.time_context import is_remote_time_question, is_scheduled_event_time_question

# Linear substrings, one per way a model says it has no clock or no live data.
_DENIALS = (
    "don't have access to the current clock",
    "do not have access to the current clock",
    "don't have access to real-time",
    "do not have access to real-time",
    "don't have real-time",
    "do not have real-time",
    "unable to access real-time",
    "can't access real-time",
    "cannot access real-time",
    "can't access the current",
    "cannot access the current",
    "don't have access to a clock",
    "don't have access to the clock",
    "no access to real-time",
    "no access to a clock",
    "no access to the clock",
    "can't tell you the exact time",
    "cannot tell you the exact time",
    "can't tell the current time",
    "cannot tell the current time",
    "can't tell you the current time",
    "cannot tell you the current time",
    "unable to check the time",
    "can't check the time",
    "cannot check the time",
    "check a device nearby",
)
_MAX_LEN = 400
# The local clock asked, and the clause ends there (fillers aside): "what time is it? i have
# a meeting at 4" asks it; "what time is it playing at amc", "what's the date of easter"
# and "whats the time over in tokyo" do not.
# The clock or the date, or both: "the date and time" is exactly what the swap shows.
_NOUN = r"(?:time|date|day)(?:\s+(?:and|&)\s+(?:the\s+)?(?:time|date))?"
_ASKS_CLOCK = re.compile(
    r"\b(?:what\s+time\s+(?:is\s+it|it\s+is)"
    r"|(?:what'?s|what\s+is|know|tell\s+me|got|give\s+me)\s+(?:the\s+)?(?:current\s+)?"
    rf"(?:today'?s\s+)?{_NOUN}"
    r"|what\s+(?:day|date|time)(?:\s+and\s+(?:time|date))?\s+(?:is\s+it|it\s+is|is\s+today)"
    rf"|today'?s\s+{_NOUN}"
    rf"|(?:current|exact|local)\s+{_NOUN})"
    r"(?=(?:\s+(?:rn|now|right\s+now|currently|today|exactly|again|here|please|pls|bro|lol)\b){0,3}"
    # The clause ends: punctuation or an emoji ("what time is it 😅"), or "in my time zone".
    r"\s*(?:$|[^\w\s(]|in\s+(?:my|our|here)\b))",
    re.IGNORECASE,
)
_BARE_TIME = re.compile(r"(?:the\s+)?time\s*\??", re.IGNORECASE)
# Another live thing the message asks about beside the clock.
_OTHER_LIVE = re.compile(
    r"\b(?:weather|forecast|temperature|rain|snow|scores?|games?|match|news|prices?|"
    r"stocks?|markets?|traffic|flights?|events?|schedules?|standings)\b",
    re.IGNORECASE,
)
# "What time is it in my time zone" asks the local clock in other words.
_IN_MY_PLACE = re.compile(r"\bin\s+(?:my|our|here)\b", re.IGNORECASE)


def _asks_the_clock(asked: str) -> bool:
    if _BARE_TIME.fullmatch(asked.strip()) is not None:
        return True
    return _ASKS_CLOCK.search(asked) is not None and _OTHER_LIVE.search(asked) is None


def _asks_another_clock(asked: str) -> bool:
    """Another place's clock, or a scheduled time ("what time is my flight")."""
    if is_remote_time_question(asked) and not _IN_MY_PLACE.search(asked):
        return True
    # "What time is it? I have a meeting at 4" still asks the clock.
    return is_scheduled_event_time_question(asked) and "what time is it" not in asked.lower()


def model_denies_clock(reply: str, asked: str) -> bool:
    """True when a short ``reply`` claims it cannot read the clock the user ``asked`` for."""
    cleaned = straighten_apostrophes(collapse_ws(reply))
    if not cleaned or len(cleaned) > _MAX_LEN:
        return False
    if not any(mark in cleaned.lower() for mark in _DENIALS):
        return False
    asked = straighten_apostrophes(collapse_ws(asked))
    return _asks_the_clock(asked) and not _asks_another_clock(asked)
