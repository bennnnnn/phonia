"""Sentences in a reply that say Recall cannot keep reminders.

Live (2026-10-25): asked "what do you remember about me so far?", a reply listed the
reminder card offered earlier and went on "I can't set reminders from here, though, so
you'll want to set that one in your own reminder app." Recall sets them: a card the user
taps. ``without_denials`` drops those sentences and keeps the rest of the reply.

A denial says the assistant cannot set or add reminders at all, or sends the user to their
own reminder app for one. A limit is no denial: "I can't add reminders to Apple Reminders
directly", "I can't set reminders that repeat every other Tuesday", anything about the
phone or another app, and "I can't remind you enough how much sleep matters". A denial
followed by "but you can…" keeps what comes after the "but".
"""

from __future__ import annotations

import re

from app.modules.todos.reply_claims import split_sentences
from app.services.md_fence_scan import line_fences
from app.services.text_normalize import straighten_apostrophes

_CANNOT = (
    r"\bi\s*(?:can't|cannot|can not|am not able to|'m not able to|am unable to|'m unable to"
    r"|don't have (?:the ability|a way) to|do not have (?:the ability|a way) to|have no way to)"
    r"\s+(?:actually\s+|directly\s+|really\s+|personally\s+)?"
)
# What may follow "reminders" in a denial of them all: an end, or words that place nothing.
_END = r"(?=\s*(?:[.,;!:)]|$))"
_ALL_OF_THEM = (
    rf"(?:\s+(?:from here|here|for you|in (?:this|the) (?:chat|app)|right now|myself|though"
    rf"|anymore|on my own))*{_END}"
)
_DENIAL = re.compile(
    "|".join(
        (
            rf"{_CANNOT}(?:set|create|make|add|schedule|save|keep|manage)\s+(?:up\s+)?"
            r"(?:any\s+|a\s+|the\s+|real\s+|actual\s+)?(?:reminders?|to-?dos?(?:\s+lists?)?)"
            + _ALL_OF_THEM,
            # "I can't remind you tomorrow", not "I can't remind you every day how much …".
            rf"{_CANNOT}remind you(?:\s+(?:from here|here|later|tomorrow|today|tonight"
            rf"|at \d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)?))*{_END}",
            r"\byou(?:'ll| will)?\s*(?:want|need|have)\s+to\s+(?:set|add|put|create|save)\s+"
            r"(?:that|it|this|them|that one|this one)\s+(?:up\s+)?(?:yourself\s+)?in\s+"
            r"(?:your|a)\s+(?:own|separate|regular)\s+(?:reminders?|to-?do|task)\s+(?:app|list)\b",
        )
    ),
    re.IGNORECASE,
)
# A sentence about the phone or another app states a real limit: Recall keeps its own list.
_ELSEWHERE = re.compile(
    r"\b(?:apple|ios|iphone|ipad|android|google|outlook|alexa|siri|samsung|calendar|clock"
    r"|alarm|phone|device|watch)\b",
    re.IGNORECASE,
)
_BUT = re.compile(r",?\s+but\s+", re.IGNORECASE)
# A list item's marker, kept on what is left of the line.
_MARKER = re.compile(r"\s*(?:[-*+>]\s+|\d+[.)]\s+)?")


def is_denial(sentence: str) -> bool:
    plain = straighten_apostrophes(sentence)
    return bool(_DENIAL.search(plain)) and not _ELSEWHERE.search(plain)


def _without_denial(sentence: str) -> str:
    """The sentence's part after "but" when it has one, or nothing."""
    plain = straighten_apostrophes(sentence)
    found = _DENIAL.search(plain)
    rest = _BUT.search(plain, found.end()) if found is not None else None
    if rest is None:
        return ""
    kept = sentence[rest.end() :].strip()
    return kept[:1].upper() + kept[1:]


def without_denials(text: str) -> str:
    """The reply without sentences saying reminders cannot be set here. Code stays."""
    if not _DENIAL.search(straighten_apostrophes(text)):
        return text
    kept: list[str] = []
    for line, fence in zip(text.split("\n"), line_fences(text), strict=True):
        if fence is not None or not line.strip():
            kept.append(line)
            continue
        # The marker pattern matches the empty string too, so it always matches.
        start = marker.end() if (marker := _MARKER.match(line)) else 0
        prefix, body = line[:start], line[start:]
        sentences = split_sentences(body)
        left = [
            part
            for sentence in sentences
            if (part := _without_denial(sentence) if is_denial(sentence) else sentence)
        ]
        if left == sentences:
            kept.append(line)
        elif left:
            kept.append(prefix + " ".join(left))
        # A line that was only the denial goes, and so does its list marker.
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return body or text
