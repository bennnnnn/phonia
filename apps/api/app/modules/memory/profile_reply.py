"""Answer a direct profile question from stored facts, without asking again."""

from __future__ import annotations

import re
from collections.abc import Sequence

_SECOND_LANGUAGE = re.compile(r"second language is ([^.]+)", re.IGNORECASE)
_FIRST_LANGUAGE = re.compile(r"(?:first|native) language is ([^.]+)", re.IGNORECASE)
_GRADE = re.compile(r"is in (\d+(?:st|nd|rd|th) grade)", re.IGNORECASE)
_SCHOOL = re.compile(
    r"(attended|studies at|attends|goes to) ([^.]+)",
    re.IGNORECASE,
)
_FROM = re.compile(r"is from ([^.]+)", re.IGNORECASE)
# "User lives in Addis Ababa", "Bini is based in Nairobi"; never "User's sister lives in".
_LIVES_IN = re.compile(
    r"^(?:the )?[a-z][\w-]*(?: (?:currently|now))? (?:lives|is living|is based|resides) in "
    r"([^.;]+)",
    re.IGNORECASE,
)
_LIVE_ASK = re.compile(r"\bwhere do i live\b", re.IGNORECASE)
_LANGUAGE_ASK = re.compile(r"\b(?:language|langauge)s?\b", re.IGNORECASE)
_EDUCATION_ASK = re.compile(
    r"\b(?:education|school|university|college|degree|grade)s?\b",
    re.IGNORECASE,
)
_SECOND = re.compile(r"\bsecond\b", re.IGNORECASE)
_FIRST = re.compile(r"\b(?:first|native)\b", re.IGNORECASE)


def reply_for_profile_question(
    question: str, facts: Sequence[str], *, location: str | None = None
) -> str:
    """One sentence from the saved facts, or a clear miss. Never a question back.

    ``location`` is the place set on the account, used when no saved fact says
    where the user lives.
    """
    if _LIVE_ASK.search(question):
        return _home_reply(facts, location)
    if _LANGUAGE_ASK.search(question):
        return _language_reply(question, facts)
    if _EDUCATION_ASK.search(question):
        return _education_reply(facts)
    if re.search(r"\bwhere am i from\b", question, re.IGNORECASE):
        origin = _first(_FROM, facts)
        if origin:
            return f"You're from {origin}."
        return "I don't have where you're from saved."
    return "I don't have that saved."


def _home_reply(facts: Sequence[str], location: str | None) -> str:
    home = _first(_LIVES_IN, facts)
    if home:
        return f"You live in {home}."
    if location:
        return f"I don't have where you live saved, but your location is set to {location}."
    return "I don't have where you live saved."


def _language_reply(question: str, facts: Sequence[str]) -> str:
    second = _first(_SECOND_LANGUAGE, facts)
    first = _first(_FIRST_LANGUAGE, facts)
    if _SECOND.search(question) and second:
        return f"Your second language is {second}."
    if _FIRST.search(question) and first:
        return f"Your first language is {first}."
    parts: list[str] = []
    if first:
        parts.append(f"Your first language is {first}")
    if second:
        parts.append(f"your second language is {second}")
    if parts:
        return " and ".join(parts) + "."
    return "I don't have a language saved for you."


def _education_reply(facts: Sequence[str]) -> str:
    grade = _first(_GRADE, facts)
    if grade:
        return f"You're in {grade}."
    school = _school(facts)
    if school:
        return school
    return "I don't have your education level saved."


def _school(facts: Sequence[str]) -> str | None:
    for text in facts:
        match = _SCHOOL.search(text)
        if match is None:
            continue
        verb, name = match.group(1).lower(), match.group(2).strip()
        if verb == "attended":
            return f"You attended {name}."
        return f"You study at {name}."
    return None


def _first(pattern: re.Pattern[str], facts: Sequence[str]) -> str | None:
    for text in facts:
        match = pattern.search(text)
        if match is not None:
            return match.group(1).strip()
    return None
