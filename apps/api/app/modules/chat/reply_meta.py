"""Sentences a reply says about the turn rather than to the user.

Live chat (2026-10-25): "1" and "Okay." were answered "Got it. It's currently Sunday,
October 25, 2026, 6:15 PM EDT." The prompt gives every reply the clock, and a short turn
read it back as filler. A sentence that is today's date and time and nothing else goes
when the user's message is not about a time, a day or a date. "It's Sunday, October 25,
2026, so the post office is closed" says something, and stays. A yes to an offer was
answered "Dev, you accepted my offer, so here is…": the lead-in about the yes goes.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.core.timezone import resolve_timezone
from app.services.md_fence_scan import line_fences
from app.services.text_normalize import straighten_apostrophes

_WEEKDAY = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH = rf"(?:{'|'.join(_MONTHS)})"
_CLOCK_TIME = r",?\s+(?:at\s+)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?(?:\s+[A-Z]{2,5})?"
# The clock as a whole sentence: "It's currently **Sunday, October 25, 2026, 6:15 PM EDT**.",
# "Yes, today is Monday, October 26, 2026, and it's 2:14 PM EDT."
_LEAD_IN = r"(?:(?:yes|yeah|yep|sure|right|well|okay|ok)[,!.]?\s+)?"
_TIME_OF_DAY = r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?(?:\s+(?-i:[A-Z]{2,5}))?"
_CLOCK_SENTENCE = re.compile(
    rf"(^|[.!?]\s+){_LEAD_IN}(?:it(?:['\u2019]s|\s+is)|today\s+is)\s+(?:currently\s+|now\s+)?"
    rf"[*_]*{_WEEKDAY},\s+"
    rf"(?P<month>{_MONTH})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{4}})(?:{_CLOCK_TIME})?"
    rf"(?:,?\s+and\s+(?:it(?:['\u2019]s|\s+is)\s+)?(?:at\s+)?{_TIME_OF_DAY})?"
    r"(?:[*_]*[.!](?=\s|$)|[*_]*\s*$)",
    re.IGNORECASE,
)
# The user's message is about time: the date may well be the answer.
_ABOUT_TIME = re.compile(
    rf"\b(?:time|date|day|days|today|tonight|tomorrow|yesterday|week|weekend|month|year|"
    rf"clock|calendar|now|when|due|deadline|until|{_WEEKDAY}|{_MONTH})\b",
    re.IGNORECASE,
)
# "Dev, you accepted my offer, so here is…", "You accepted my last offer again, so…".
_ACCEPTED_LEAD = re.compile(
    r"^(?:[A-Z][\w'-]*,\s+)?you(?:'ve|\s+have)?\s+accepted\s+my\s+(?:last\s+)?offer"
    r"(?:\s+again)?\s*[,.]\s*(?:so\s+)?",
    re.IGNORECASE,
)


def is_about_time(text: str | None) -> bool:
    """The message names a time, a day or a date: the clock may be what it needs."""
    return bool(text and _ABOUT_TIME.search(text))


def _is_today(found: re.Match[str], today: date | None) -> bool:
    if today is None:
        return True
    month = _MONTHS.index(found.group("month").lower()) + 1
    return (int(found.group("year")), month, int(found.group("day"))) == (
        today.year,
        today.month,
        today.day,
    )


def _without_clock(line: str, today: date | None) -> str:
    def drop(found: re.Match[str]) -> str:
        return found.group(1) if _is_today(found, today) else found.group(0)

    return re.sub(r"(?<=[.!?]) {2,}", " ", _CLOCK_SENTENCE.sub(drop, line)).strip()


def without_turn_meta(text: str, asked: str, today: date | None = None) -> str:
    """The reply without an unasked clock sentence or a lead-in about an accepted offer."""
    stripped = text.lstrip()
    lead = _ACCEPTED_LEAD.match(straighten_apostrophes(stripped))
    if lead is not None and lead.end() < len(stripped):
        rest = stripped[lead.end() :]
        # "here is…" opens the reply; "iPhone tips" keeps its case.
        text = rest[0].upper() + rest[1:] if rest[:2].islower() else rest
    if is_about_time(asked):
        return text
    lines: list[str] = []
    changed = False
    for line, fence in zip(text.split("\n"), line_fences(text), strict=True):
        if fence is not None or not _CLOCK_SENTENCE.search(line):
            lines.append(line)
            continue
        kept = _without_clock(line, today)
        changed = changed or kept != line.strip()
        if kept:
            lines.append(kept)
    if not changed:
        return text
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return body or text


def local_today(timezone: str | None) -> date:
    """Today on the user's clock: a date read back as filler is today's."""
    return datetime.now(resolve_timezone(timezone)).date()
