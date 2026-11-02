"""Dates the user names: month names, ISO dates and (where a caller asks) slash dates.

The reminder reader, recurring pay and the calendar facts each kept a month table and
a date grammar of their own: "2027-1-7" was a date to recurring pay and not to the
calendar facts, "12/25" only to recurring pay, and "remind me on 2026-12-25" named no
day to the reminder reader (code-health audit DUP-09). This reads the dates; each
caller keeps its own decisions (which year is meant, whether a past date counts, a
lowercase "may" that may be a verb).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MONTHS: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    # A phone keyboard's slip, from a production question.
    "dcember": 12,
}  # fmt: skip
MONTH_NAME = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|dcember)"
)
_DAY = r"(?P<day>[0-3]?\d)(?:st|nd|rd|th)?"
# A year after a date or a holiday's name: "December 25, 2026", "Christmas 2027".
YEAR_SUFFIX = r"(?:,?\s+(?P<year>(?:19|20)\d\d)\b)?"
_MONTH_FIRST = re.compile(rf"\b(?P<month>{MONTH_NAME})\.?\s+{_DAY}\b{YEAR_SUFFIX}", re.IGNORECASE)
_DAY_FIRST = re.compile(
    rf"\b{_DAY}\s+(?:of\s+)?(?P<month>{MONTH_NAME})\b\.?{YEAR_SUFFIX}", re.IGNORECASE
)
# One width rule: a four-digit year, then a month and a day of one or two digits.
_ISO = re.compile(r"\b((?:19|20)\d\d)-(\d{1,2})-(\d{1,2})\b")
# Month first, as written in the US; a two-digit year is this century's.
_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?\b")

Form = Literal["month_day", "day_month", "iso", "slash"]


@dataclass(frozen=True)
class NamedDate:
    """A date as the text names it. The day and month are in range; whether the date
    exists (30 February) and which year is meant are the caller's to decide."""

    month: int
    day: int
    year: int | None
    start: int
    end: int
    text: str
    form: Form
    # The month as written ("may", "Sept"), for a named date.
    month_word: str | None = None


def month_number(word: str) -> int | None:
    """``Sept`` → 9; None for a word that is no month."""
    return MONTHS.get(word.lower().rstrip("."))


def read_dates(text: str, *, slash: bool = False) -> list[NamedDate]:
    """Every date the text names, first mention first; slash dates only when asked for."""
    found: list[NamedDate] = []
    for form, pattern in (("month_day", _MONTH_FIRST), ("day_month", _DAY_FIRST)):
        for match in pattern.finditer(text):
            month = month_number(match.group("month"))
            day = int(match.group("day"))
            year = match.group("year")
            if month is not None and 1 <= day <= 31:
                found.append(
                    NamedDate(
                        month=month,
                        day=day,
                        year=int(year) if year else None,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(0).strip(),
                        # One of this module's date-pattern names; the model validates it.
                        form=form,  # type: ignore[arg-type]
                        month_word=match.group("month"),
                    )
                )
    for match in _ISO.finditer(text):
        year, month, day = (int(part) for part in match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            found.append(
                NamedDate(month, day, year, match.start(), match.end(), match.group(0), "iso")
            )
    if slash:
        for match in _SLASH.finditer(text):
            month, day = int(match.group(1)), int(match.group(2))
            raw_year = match.group(3)
            year = None if raw_year is None else int(raw_year) + (2000 if len(raw_year) == 2 else 0)
            if 1 <= month <= 12 and 1 <= day <= 31:
                found.append(
                    NamedDate(month, day, year, match.start(), match.end(), match.group(0), "slash")
                )
    return sorted(found, key=lambda named: named.start)
