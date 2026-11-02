"""Whether a message asks about the subject a reply's photo would show."""

from __future__ import annotations

import re

_ASKS_ABOUT = re.compile(
    r"^\s*(?:(?:hey|so|ok(?:ay)?|and)[,\s]+)?(?:please\s+)?"
    r"(?:what(?:['\u2019]s|\s+is|\s+are|\s+was|\s+were)\s+(?:an?\s+)?"
    r"|who(?:['\u2019]s|\s+is|\s+are|\s+was|\s+were)\s+"
    r"|(?:(?:can|could)\s+you\s+)?tell\s+me\s+(?:a\s+(?:little\s+)?bit\s+)?about\s+(?:the\s+)?)"
    r"(?P<subject>[^\W\d_][\w'\u2019 .-]*?)\s*[?.!]*\s*$",
    re.IGNORECASE,
)


# Not one thing to look at: the asker, a pronoun, a lookup with a "the … of" frame.
_NOT_A_THING = re.compile(
    r"^(?:it|this|that|these|those|he|she|they|you|me|i|we|him|her|them|his|their"
    r"|(?:your|my|our)sel(?:f|ves)|the\s+(?:time|date|weather|answer|difference|best|meaning))\b"
    # "a good name for my cat" asks for an answer, not about a thing.
    r"|\b(?:my|your|our|for|to|with|that|which|should|good|best|the\s+\w+\s+of)\b",
    re.IGNORECASE,
)


_MAX_SUBJECT_WORDS = 5


def asked_about_subject(text: str) -> str | None:
    """``capybara`` for "what is a capybara"; None when the turn names no one thing."""
    match = _ASKS_ABOUT.match(text or "")
    if match is None:
        return None
    subject = match.group("subject").strip(" .")
    if not subject or len(subject.split()) > _MAX_SUBJECT_WORDS or _NOT_A_THING.search(subject):
        return None
    return subject
