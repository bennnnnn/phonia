"""The one reader of a day and a clock in the user's words.

"remind me tomorrow at 6pm to call mom", "remind me tmrw 8am buy injera",
"reminder: renew my passport, oct 20 at 10am", "set a reminder saturday 11am -
meet abel". In a new reminder, a clock without am/pm counts only beside a part
of the day ("tonight at 9", "9 in the morning"); otherwise the app asks when.

A bare hour is the evening when it is the whole reply to "when?" or ends a
change ("make it 7"): "6" and "6:30" are 6 PM and 6:30 PM, and "18" stays
18:00. "0" is no clock; midnight is said as midnight or 12am. An am/pm clock
has hours 1 to 12 everywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import NamedTuple

from app.services.calendar_dates import read_dates

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# The words a day is said as on its own, as ``date_for_day`` reads them.
DAY_NAMES = frozenset(("today", "tomorrow", *_WEEKDAYS))
_LEAD = r"\b(?:(?:on|for|by|this|coming)\s+){0,2}"
_DAY_RE = re.compile(
    _LEAD + r"(?P<next>next\s+)?(?P<day>today|tonight|tomorrow|" + "|".join(_WEEKDAYS) + r")\b",
    re.IGNORECASE,
)
# "fri 6pm", "sat 9am": a short day name counts only before a clock.
_SHORT_DAYS = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
_SHORT_DAY_RE = re.compile(
    _LEAD
    + r"(?P<next>next\s+)?(?P<day>"
    + "|".join(_SHORT_DAYS)
    + r")\b\.?(?=\s*(?:at\s+|@\s*)?\d)",
    re.IGNORECASE,
)
_REPEAT_RE = re.compile(
    r"\b(?:every\s*(?P<daily>day|night|morning|evening|afternoon)|(?P<daily2>daily|everyday|nightly)"
    r"|every\s+(?P<weekly>week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|(?P<weekly2>weekly)|every\s+(?P<weekdays>weekday)|(?P<weekdays2>weekdays)"
    r"|every\s+(?P<monthly>month)|(?P<monthly2>monthly))\b",
    re.IGNORECASE,
)
# The words before a date that go with it out of the reminder's text: "on", "by Dec 25".
_LEAD_BEFORE = re.compile(r"\b(?:(?:on|for|by|this|coming)\s+){1,2}\Z", re.IGNORECASE)
# "6pm", "7:30 a.m.": the am/pm clock, read at a place or found anywhere.
_AMPM = r"(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s*(?P<ap>[ap])\.?m\b\.?"
_AMPM_RE = re.compile(_AMPM, re.IGNORECASE)
_MERIDIEM_RE = re.compile(r"(?:\b(?:at|by)\s+|@\s*)?\b" + _AMPM, re.IGNORECASE)
_BARE_CLOCK_RE = re.compile(r"(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?")
_NAMED_RE = re.compile(r"(?:\b(?:at|by)\s+)?\b(?P<n>noon|midday|midnight)\b", re.IGNORECASE)
_PART_RE = re.compile(
    r"\b(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s+in\s+the\s+(?P<part>morning|afternoon|evening)\b",
    re.IGNORECASE,
)
# "at 9" or "at 9:30": a clock only beside a part of the day.
_BARE_RE = re.compile(
    r"(?:\b(?:at|by)\s+|@\s*)(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\b(?!\s*(?:%|[.,]\d))",
    re.IGNORECASE,
)
_EVENING = re.compile(r"\b(?:tonight|evening|night|afternoon)\b", re.IGNORECASE)
_MORNING = re.compile(r"\bmorning\b", re.IGNORECASE)
# "in 3 minutes", "in an hour and a half", "20 mins from now": a time from now.
_COUNT_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "ninety": 90,
}  # fmt: skip
_UNIT_MINUTES = {"min": 1, "hour": 60, "hr": 60, "day": 1440, "week": 10080, "wk": 10080}
_COUNT = r"(?P<n>\d{1,3}(?:\.\d{1,2})?|(?:a\s+)?couple(?:\s+of)?|" + "|".join(_COUNT_WORDS) + r")"
_UNIT = r"(?P<unit>min(?:ute)?s?|hours?|hrs?|days?|weeks?|wks?)\b"
_SPAN = (
    r"(?:(?P<half>half\s+an?\s+hour)|"
    + _COUNT
    + r"\s*"
    + _UNIT
    + r"(?P<and_half>\s+and\s+a\s+half)?)"
)
_AFTER_RE = re.compile(
    r"\b(?:in|after)\s+" + _SPAN + r"|\b" + _SPAN.replace("?P<", "?P<f_") + r"\s+from\s+now\b",
    re.IGNORECASE,
)
# A year at most, so a stray "in 900 weeks" is not a reminder.
_MAX_AFTER_MINUTES = 366 * 1440


@dataclass
class SpokenWhen:
    """``day`` is today, tomorrow, a weekday, "next <weekday>", or "MM-DD"."""

    day: str | None = None
    hour: int | None = None
    minute: int | None = None
    spans: list[tuple[int, int]] = field(default_factory=list)
    # "in 3 minutes": minutes from now, read only when no day or clock is named.
    after_minutes: int | None = None


def find_when(text: str) -> SpokenWhen:
    found = SpokenWhen()
    _find_day(text, found)
    _find_clock(text, found)
    if found.day is None and found.hour is None:
        _find_after(text, found)
    return found


def _find_after(text: str, found: SpokenWhen) -> None:
    match = _AFTER_RE.search(text)
    if match is None:
        return
    groups = {key.removeprefix("f_"): value for key, value in match.groupdict().items() if value}
    if "half" in groups:
        minutes = 30.0
    else:
        raw = groups["n"].lower()
        count = 2.0 if "couple" in raw else float(_COUNT_WORDS.get(raw, 0) or raw)
        unit = groups["unit"].lower()
        per = next(value for key, value in _UNIT_MINUTES.items() if unit.startswith(key))
        minutes = (count + (0.5 if "and_half" in groups else 0)) * per
    if 1 <= minutes <= _MAX_AFTER_MINUTES:
        found.after_minutes = round(minutes)
        found.spans.append(match.span())


def _find_day(text: str, found: SpokenWhen) -> None:
    # A named date or an ISO one ("Dec 25", "25th of December", "2026-12-25").
    dated = next(iter(read_dates(text)), None)
    day = _DAY_RE.search(text)
    if dated is not None:
        lead = _LEAD_BEFORE.search(text, 0, dated.start)
        start = dated.start if lead is None else lead.start()
        if day is None or start < day.start():
            found.day = f"{dated.month:02d}-{dated.day:02d}"
            found.spans.append((start, dated.end))
            return
    if day is None:
        day = _SHORT_DAY_RE.search(text)
        if day is None:
            return
        name = _SHORT_DAYS[day.group("day").lower()]
        if day.group("next"):
            name = f"next {name}"
        found.day = name
        found.spans.append(day.span())
        return
    name = day.group("day").lower()
    if name == "tonight":
        name = "today"
    elif day.group("next") and name in _WEEKDAYS:
        name = f"next {name}"
    found.day = name
    found.spans.append(day.span())


def _find_clock(text: str, found: SpokenWhen) -> None:
    match = _MERIDIEM_RE.search(text)
    if match is not None:
        hour = _ampm_hour(match)
        if hour is not None:
            _set_clock(found, hour, match, text)
            return
    match = _NAMED_RE.search(text)
    if match is not None:
        _set_clock(found, 0 if match.group("n").lower() == "midnight" else 12, match, text)
        return
    match = _PART_RE.search(text)
    if match is not None:
        hour = int(match.group("h"))
        if 1 <= hour <= 12:
            evening = match.group("part").lower() != "morning"
            _set_clock(found, hour % 12 + (12 if evening else 0), match, text)
            return
    match = _BARE_RE.search(text)
    if match is None:
        return
    hour = int(match.group("h"))
    if 13 <= hour <= 23:
        _set_clock(found, hour, match, text)
    elif 1 <= hour <= 12 and _EVENING.search(text):
        _set_clock(found, hour % 12 + 12, match, text)
    elif 1 <= hour <= 12 and _MORNING.search(text):
        _set_clock(found, hour % 12, match, text)


def _set_clock(found: SpokenWhen, hour: int, match: re.Match[str], text: str) -> None:
    minute = match.groupdict().get("m")
    found.hour = hour
    found.minute = int(minute) if minute else 0
    found.spans.append(match.span())


def _ampm_hour(match: re.Match[str]) -> int | None:
    """The 24-hour hour of an am/pm clock; hours outside 1 to 12 are no clock."""
    hour = int(match.group("h"))
    if not 1 <= hour <= 12:
        return None
    return hour % 12 + (12 if match.group("ap").lower() == "p" else 0)


class Clock(NamedTuple):
    """A clock read from the user's words: the 24-hour time, and where it was said."""

    hour: int
    minute: int
    start: int
    end: int


def read_clock(text: str, start: int = 0) -> Clock | None:
    """An am/pm clock at ``start``, after any spaces: "6pm", "7:30 a.m.", "12am"."""
    at = start
    while at < len(text) and text[at].isspace():
        at += 1
    match = _AMPM_RE.match(text, at)
    if match is None:
        return None
    hour = _ampm_hour(match)
    if hour is None:
        return None
    return Clock(hour, int(match.group("m") or 0), at, match.end())


def bare_hour_as_pm(text: str) -> tuple[int, int] | None:
    """A clock with no am/pm, all of ``text``: "6" and "6:30" are the evening.

    Hours 1 to 11 are after noon, the way a reminder is meant; 12 to 23 are as
    said. "0", "24" and "6:3" are no clock.
    """
    match = _BARE_CLOCK_RE.fullmatch(text.strip())
    if match is None:
        return None
    hour = int(match.group("h"))
    if not 1 <= hour <= 23:
        return None
    return (hour + 12 if hour < 12 else hour), int(match.group("m") or 0)


def parse_clock_only(user_text: str | None) -> tuple[int, int] | None:
    """A reply that is only a clock: "6", "6:30", "6pm", "at 7:30 a.m.". Other words are not."""
    raw = (user_text or "").strip()
    while raw and raw[-1] in ".!?":
        raw = raw[:-1].rstrip()
    if raw.lower().startswith("at "):
        raw = raw[3:].strip()
    clock = read_clock(raw)
    if clock is not None and not raw[clock.end :].strip(" ."):
        return clock.hour, clock.minute
    return bare_hour_as_pm(raw)


def find_clock(text: str) -> Clock | None:
    """The first am/pm clock in a change, else a bare hour that ends it.

    "make it 8:00 AM", "move gym to 7pm on friday", and "make it 7", which is 7 PM.
    An am/pm clock starts a word: "18:30pm" is not 8:30 PM.
    """
    for at, char in enumerate(text):
        if char.isdigit() and (at == 0 or not _in_a_word(text[at - 1])):
            clock = read_clock(text, at)
            if clock is not None:
                return clock
    body = text.rstrip(" .")
    start = len(body)
    while start > 0 and not body[start - 1].isspace():
        start -= 1
    bare = bare_hour_as_pm(body[start:])
    return None if bare is None else Clock(bare[0], bare[1], start, len(body))


def _in_a_word(char: str) -> bool:
    return char.isalnum() or char == "_"


def date_for_day(day_name: str, now: datetime) -> date | None:
    """today, tomorrow, a weekday, "next <weekday>", or "MM-DD" (this year, else next)."""
    if day_name == "today":
        return now.date()
    if day_name == "tomorrow":
        return now.date() + timedelta(days=1)
    if len(day_name) == 5 and day_name[2] == "-" and day_name.replace("-", "").isdigit():
        return _next_date(int(day_name[:2]), int(day_name[3:]), now.date())
    following = day_name.startswith("next ")
    try:
        weekday = _WEEKDAYS.index(day_name.removeprefix("next "))
    except ValueError:
        return None
    delta = (weekday - now.weekday()) % 7
    # "Next Wednesday" said on a Wednesday is a week away, not today.
    if following and delta == 0:
        delta = 7
    return now.date() + timedelta(days=delta)


def _next_date(month: int, day: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def due_on_day(day_name: str, hour: int, minute: int, now: datetime) -> datetime | None:
    """That clock on the named day, in the zone of ``now``, the user's local time."""
    day = date_for_day(day_name, now)
    if day is None:
        return None
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)


def find_repeat(text: str) -> tuple[str, tuple[int, int]] | None:
    """ "every night" → daily, "every monday" → weekly, with where it was said."""
    match = _REPEAT_RE.search(text)
    if match is None:
        return None
    groups = match.groupdict()
    for rule in ("daily", "weekly", "weekdays", "monthly"):
        if groups.get(rule) or groups.get(f"{rule}2"):
            return rule, match.span()
    return None


def without_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """The text with the day and the clock taken out."""
    kept: list[str] = []
    last = 0
    for start, end in sorted(spans):
        if start < last:
            continue
        kept.append(text[last:start])
        last = end
    kept.append(text[last:])
    return " ".join(" ".join(kept).split())
