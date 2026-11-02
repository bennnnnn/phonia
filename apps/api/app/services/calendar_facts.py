"""The calendar, read instead of counted: dates the user names, the coming week, weekday checks.

The model counts weekdays badly ("Christmas 2026 falls on a Monday"; it is a
Friday) and miscounts days ("what is Tuesday" on a Sunday got Wednesday the
21st). So the prompt states the facts and the reply is checked against them:

- every date the message names (``December 25``, ``3 March 2027``,
  ``2027-01-07``, a fixed-date holiday such as Christmas or Meskel) with its
  weekday, in the year the message means;
- the next seven days, for "Tuesday", "next Friday", "this weekend";
- a reply's "Weekday, Month D, YYYY" corrected before it is saved.

Holidays whose date moves (Easter, Ramadan) are not here: a search finds them.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.services.calendar_dates import YEAR_SUFFIX, read_dates

# Fixed-date days people ask about by name, as (month, day).
_HOLIDAYS = {
    "new year's day": (1, 1),
    "new years day": (1, 1),
    "new year's eve": (12, 31),
    "new years eve": (12, 31),
    "valentine's day": (2, 14),
    "valentines day": (2, 14),
    "international women's day": (3, 8),
    "earth day": (4, 22),
    "labour day": (5, 1),
    "labor day in ethiopia": (5, 1),
    "independence day": (7, 4),
    "fourth of july": (7, 4),
    "halloween": (10, 31),
    "christmas eve": (12, 24),
    "christmas": (12, 25),
    "boxing day": (12, 26),
    "ethiopian christmas": (1, 7),
    "genna": (1, 7),
    "timkat": (1, 19),
    "adwa victory day": (3, 2),
    "adwa day": (3, 2),
    "meskel": (9, 27),
    "ethiopian new year": (9, 11),
    "enkutatash": (9, 11),
}
_HOLIDAY_NAMES = "|".join(re.escape(name) for name in sorted(_HOLIDAYS, key=len, reverse=True))
_HOLIDAY = re.compile(rf"\b({_HOLIDAY_NAMES})\b{YEAR_SUFFIX}", re.IGNORECASE)
# "May" and "March" are words too: "a 5 may be wrong" names no date. Day first
# ("5 May"), they count only capitalised or with a year.
_WORD_MONTHS = frozenset({"may", "mar", "march"})
_YEAR_WORD = re.compile(r"\b(this|next|last)\s+year\b", re.IGNORECASE)
_LOOSE_YEAR = re.compile(r"\b(?:in|of)\s+((?:19|20)\d\d)\b")
_MAX_FACTS = 6


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _meant_year(text: str, today: date, month: int, day: int, stated: int | None) -> int:
    """The year a date means: stated, "this/next/last year", or its next occurrence."""
    if stated is not None:
        return stated
    loose = _LOOSE_YEAR.search(text)
    if loose:
        return int(loose.group(1))
    word = _YEAR_WORD.search(text)
    if word:
        return today.year + {"this": 0, "next": 1, "last": -1}[word.group(1).lower()]
    upcoming = _safe_date(today.year, month, day)
    return today.year if upcoming is None or upcoming >= today else today.year + 1


def _enkutatash_day(year: int) -> int:
    # Ethiopian New Year is September 12 in the Gregorian year before a leap year.
    following = year + 1
    return 12 if following % 4 == 0 and (following % 100 or following % 400 == 0) else 11


def named_dates(text: str, today: date) -> list[tuple[str, date]]:
    """Each date the text names, with the words that named it, first mention first."""
    found: list[tuple[int, str, date]] = []
    for named in read_dates(text):
        word = (named.month_word or "").rstrip(".")
        ambiguous = word.lower() in _WORD_MONTHS and word.islower()
        if named.form == "day_month" and ambiguous and named.year is None:
            continue
        year = _meant_year(text, today, named.month, named.day, named.year)
        when = _safe_date(year, named.month, named.day)
        if when is not None:
            found.append((named.start, named.text, when))
    for match in _HOLIDAY.finditer(text):
        name = match.group(1).lower()
        month, day = _HOLIDAYS[name]
        stated = match.group("year")
        year = _meant_year(text, today, month, day, int(stated) if stated else None)
        if name in {"ethiopian new year", "enkutatash"}:
            day = _enkutatash_day(year)
        when = _safe_date(year, month, day)
        if when is not None:
            found.append((match.start(), match.group(1), when))
    seen: set[date] = set()
    ordered: list[tuple[str, date]] = []
    for _start, label, when in sorted(found):
        if when not in seen:
            seen.add(when)
            ordered.append((label, when))
    return ordered[:_MAX_FACTS]


def _written(when: date) -> str:
    return f"{when.strftime('%A')}, {when.strftime('%B')} {when.day}, {when.year}"


def calendar_lines(now: datetime, message: str | None = None) -> str:
    """The coming week, then every date the message names, for the clock line."""
    days = (now + timedelta(days=offset) for offset in range(1, 8))
    week = ", ".join(f"{day.strftime('%A')} {day.strftime('%B')} {day.day}" for day in days)
    lines = f"The next seven days: {week}."
    named = named_dates(message or "", now.date())
    if named:
        facts = "; ".join(f"{label} is {_written(when)}" for label, when in named)
        lines += f" Dates in this message (computed, use them): {facts}."
    return lines


# "**Monday**, December 25, 2026" is checked too: bold may wrap the weekday.
_WEEKDAY_DATE = re.compile(
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?:\*\*)?,?\s+"
    r"(?:\*\*)?(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+"
    r"(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)


def correct_weekday_dates(text: str) -> str:
    """Replace a weekday that does not belong to the date written next to it."""

    def replace(match: re.Match[str]) -> str:
        weekday = match.group(1)
        month = match.group(2)
        day_raw = match.group(3)
        year_raw = match.group(4)
        try:
            when = datetime.strptime(f"{month} {int(day_raw)} {int(year_raw)}", "%B %d %Y")
        except ValueError:
            return match.group(0)
        actual = when.strftime("%A")
        if actual.lower() == weekday.lower():
            return match.group(0)
        return match.group(0).replace(weekday, actual, 1)

    return _WEEKDAY_DATE.sub(replace, text)
