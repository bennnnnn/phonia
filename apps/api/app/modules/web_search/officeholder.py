"""Who holds an office is a live fact: the answer has to come from a search.

In a chat about Ethiopia, "What is the president?" got a made-up president from
memory, and "who is the president of ethiopia" never searched either: officeholders
change after training. Asking who holds an office (president, prime minister, CEO,
mayor, pope, ...) searches, for any place or company; no country list.

A follow-up that names no place ("What is the president?") searches for the
chat's subject, not the bare words.
"""

from __future__ import annotations

import re

_OFFICE = (
    r"(?:vice[- ]president|president|prime\s+minister|premier|chancellor|king|queen|monarch"
    r"|emperor|pope|ceo|chief\s+executive(?:\s+officer)?|chair(?:man|woman|person)?|governor"
    r"|mayor|head\s+of\s+(?:state|government)|secretary[- ]general|speaker|leader"
    r"|chief\s+justice|(?:foreign|finance|defen[cs]e|health)\s+minister|director[- ]general)"
)
# "Who is the president of Ethiopia", "who's the CEO of Tesla now", "What is the
# president?". Not "what is a president" (a definition), "who was the first
# president" (history), or "who is the president of my club" (nothing to look up).
_WHO_HOLDS = re.compile(
    r"^(?:(?:and|so|ok(?:ay)?|then)[ ,]+)?(?:who|what)(?:['\u2019]s|\s+is)\s+the\s+"
    rf"(?:current\s+|new\s+|present\s+|sitting\s+)?{_OFFICE}"
    r"(?P<place>\s+(?:of|in|at|for)\s+(?!(?:my|our|your|his|her|their|this|that)\b)\S.*?)?"
    r"(?:\s+(?:now|right\s+now|today|currently|these\s+days))?\s*[?.!]*$",
    re.IGNORECASE,
)


def asks_who_holds_office(text: str) -> bool:
    """True for "who is the president of Ethiopia" and "What is the president?"."""
    return _WHO_HOLDS.match(text.strip()) is not None


def office_without_place(text: str) -> bool:
    """True for "What is the president?": the place is the chat's subject."""
    match = _WHO_HOLDS.match(text.strip())
    return match is not None and not match.group("place")


def office_with_subject(text: str, prior_user_message: str) -> str:
    """``president`` and "tell me about the war in ethiopia": searched together."""
    office = re.search(_OFFICE, text, re.IGNORECASE)
    return f"{office.group(0) if office else text.strip()} {prior_user_message.strip()}"
