"""How long a message asks the reply to be."""

from __future__ import annotations

import re
from typing import Literal

from app.services.number_text import count_word_pattern
from app.services.text_normalize import collapse_ws, straighten_apostrophes

ReplyLength = Literal["brief", "balanced", "detailed", "mixed"]


_BREVITY_MARKERS = (
    "in one sentence",
    "one sentence",
    "in a word",
    "in one word",
    "in a single word",
    "briefly",
    "keep it short",
    "keep it brief",
    "shorter",
    "tldr",
    "tl;dr",
)


# "in 3 sentences", "under 100 words", "in two lines": a stated length is a cap too.
_LENGTH_CAP = re.compile(
    r"\b(?:in|within|using|with)\s+(?:only\s+|just\s+|exactly\s+)?"
    rf"(?:{count_word_pattern(high=10)}|a\s+few|\d{{1,3}})\s+"
    r"(?:short\s+)?(?:sentences?|words?|lines?|bullet(?:\s+point)?s?|paragraphs?)\b"
    r"|\b(?:under|less\s+than|fewer\s+than|no\s+more\s+than|at\s+most|max(?:imum)?)\s+"
    r"\d{1,4}\s+(?:words?|characters?|sentences?|lines?)\b"
    rf"|\b(?:{count_word_pattern(high=5)}|\d{{1,3}})[- ](?:sentence|word|line|paragraph)\s+"
    r"(?:summary|answer|reply|description|explanation|version|bio|pitch|intro|overview)\b",
    re.IGNORECASE,
)


# "In detail", "a deep dive into", "explain it thoroughly": the user asked for depth.
# "The details of the iPhone 16", "thoroughly clean the oven", "comprehensive insurance"
# and "a deep dive in scuba" are about something else. Input is ``collapse_ws``-ed, so
# a space is one space.
_DETAIL_REQUEST = re.compile(
    r"\bin (?:great |full |more |much more |greater |fine )?detail\b"
    r"|\bin[ -]depth\b"
    r"|\bdeep[ -]?dive (?:into|on|of)\b|\b(?:do|give me|want|need) a deep[ -]?dive\b"
    r"|^deep[ -]?dive\b"
    r"|\b(?:explain|describe|cover|go over|break down)(?: (?:it|this|that|them|everything))? "
    r"(?:thoroughly|fully|in full|exhaustively|comprehensively)\b"
    r"|\b(?:explain|describe|cover|go over|break down)\b[^.?!]{1,60} "
    r"(?:thoroughly|fully|exhaustively|comprehensively)[.!?]*$"
    r"|\b(?:thorough|comprehensive|exhaustive|detailed|long|full|complete) "
    r"(?:explanation|answer|breakdown|overview|guide|walkthrough|analysis|rundown|tutorial)\b"
    r"|\b(?:give|tell|show) me (?:a lot |much )?more details?\b|^more details?(?: please)?[.!?]*$"
    r"|\btell me everything (?:about|on)\b|\bgo deeper\b"
    r"|\belaborate (?:on|more)\b"
    r"|^(?:please |can you |could you )?elaborate(?: please| a bit| a little)?[.!?]*$"
    r"|\bdon't hold back\b|\bleave nothing out\b",
    re.IGNORECASE,
)


def is_brevity_request(text: str) -> bool:
    """True when the user capped length (one sentence / briefly)."""
    cleaned = text.strip().lower()
    if not cleaned:
        return False
    return any(marker in cleaned for marker in _BREVITY_MARKERS) or bool(
        _LENGTH_CAP.search(cleaned)
    )


def is_detail_request(text: str) -> bool:
    """True when the user asked for depth ("in detail", "deep dive", "explain thoroughly")."""
    cleaned = collapse_ws(straighten_apostrophes(text))
    return bool(cleaned) and _DETAIL_REQUEST.search(cleaned) is not None


def reply_length(text: str) -> ReplyLength:
    """The length this text asks for; "mixed" when it caps one part and wants detail in another."""
    brief = is_brevity_request(text)
    detailed = is_detail_request(text)
    if brief and detailed:
        return "mixed"
    if brief:
        return "brief"
    return "detailed" if detailed else "balanced"
