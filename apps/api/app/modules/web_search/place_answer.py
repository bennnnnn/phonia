# ruff: noqa: RUF001 - the typographic apostrophe iOS types (U+2019) is matched
"""A place the user names right after Recall said it doesn't know where they are.

"Is it gonna rain tonight?" got the location reply, and "I'm in Indianapolis" answers
it. The turn is the earlier question asked in that place: it searches "is it gonna rain
tonight in Indianapolis". The place alone searched nothing, and the model offered to
look it up, then said it couldn't check live weather.
"""

from __future__ import annotations

import re

# The location reply's opening (``geo_intent.format_location_not_set_answer``).
LOCATION_ASK_OPENING = "I don't have your location yet"

# "I'm in", "we're near", "I live in", "currently in" before the place.
_LEAD = re.compile(
    r"^(?:(?:i['’]?m|i\s+am|we['’]?re|we\s+are|i\s+live|we\s+live|i['’]?m\s+"
    r"currently|currently|i['’]?m\s+staying)\s+)?(?:(?:in|at|near|around)\s+)?",
    re.IGNORECASE,
)
_TRAIL = re.compile(r"(?:\s+(?:right\s+now|now|rn|currently|today|tonight|atm))?[\s.!,]*$", re.I)
_PLACE = re.compile(r"[^\W\d_][\w .,'’-]*", re.UNICODE)
_MAX_PLACE_WORDS = 5
# Words a short reply holds that no place name does: "yes please", "turn it on", "ok".
_NOT_A_PLACE = frozenset(
    {
        "yes", "yeah", "yep", "no", "nope", "ok", "okay", "sure", "please", "thanks",
        "thank", "you", "nvm", "never", "mind", "cool", "fine", "good", "great", "it",
        "that", "this", "turn", "on", "off", "settings", "location", "how", "what", "why",
        "where", "when", "who", "not", "do", "does", "did", "is", "are", "was", "be", "i",
        "me", "my", "we", "us", "our", "can", "can't", "cant", "don't", "dont", "will",
        "would", "should", "here", "there", "home", "anywhere", "somewhere",
    }
)  # fmt: skip
# "Coffee near me" asked in Indianapolis is "coffee in Indianapolis".
_NEAR_USER = re.compile(
    r"\b(?:near\s+me|nearby|near\s+here|around\s+here|close\s+to\s+me|around\s+me)\b",
    re.IGNORECASE,
)


def given_place(text: str) -> str | None:
    """The place ``text`` names as where the user is ("I'm in Indianapolis"), else None."""
    cleaned = " ".join(text.split())
    if not cleaned or "?" in cleaned:
        return None
    place = _TRAIL.sub("", _LEAD.sub("", cleaned, count=1)).strip(" ,")
    if not place or _PLACE.fullmatch(place) is None:
        return None
    words = [word.strip(".,").casefold().replace("’", "'") for word in place.split()]
    if len(words) > _MAX_PLACE_WORDS or any(word in _NOT_A_PLACE for word in words):
        return None
    return place


def question_in_given_place(
    text: str, prior_user: str | None, prior_assistant: str | None
) -> str | None:
    """The earlier question asked in the place ``text`` names, when Recall had just said
    it didn't know where the user is; None otherwise."""
    if not prior_user or not (prior_assistant or "").lstrip().startswith(LOCATION_ASK_OPENING):
        return None
    place = given_place(text)
    if place is None:
        return None
    question = " ".join(prior_user.split()).rstrip(" ?.!")
    if _NEAR_USER.search(question):
        return _NEAR_USER.sub(f"in {place}", question, count=1)
    return f"{question} in {place}"
