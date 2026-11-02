"""Whether a ranking question says what it is for."""

from __future__ import annotations

import re

# A ranking ask: "the best countries", "top universities", "which laptop should I buy".
_RANKING = re.compile(
    r"\b(?:best|top|ideal|greatest|recommended)\b|\b(?:which|what)\b[^.?!]{0,40}?\bshould\s+"
    r"(?:i|we)\s+(?:buy|get|choose|pick|use|learn|try|visit|move\s+to)\b",
    re.IGNORECASE,
)


# What it is for, after the ranking word: "for business", "to live in", "under $500",
# "in Paris". "For me", "in the world" or "ever" name no purpose: the user's own wants
# are still unknown, and the card may ask them.
_PURPOSE = re.compile(
    r"\b(?:for|to|under|below|within|in)\s+(?!(?:me|us|myself|ourselves|the\s+world|general"
    r"|my\s+(?:needs|situation|case|life))\b)[\w$€£]",
    re.IGNORECASE,
)


def names_its_purpose(text: str) -> bool:
    """A "best X" question that says what it is for, which has a good general answer.

    "What are the best countries for business" got a card asking what mattered most and
    what kind of business, after three suggestions: business was the answer to "best for
    what". "What is the best country?" and "the best laptop for me" still may ask.
    """
    ranking = _RANKING.search(text)
    return ranking is not None and _PURPOSE.search(text, ranking.end()) is not None
