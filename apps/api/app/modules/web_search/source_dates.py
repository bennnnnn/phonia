"""Dates in a search result, read against the user's today before the model reads them.

On 2026-10-24, "is the Pixel 11 out yet?" was answered "No, it isn't out yet" on 10 turns
in 12, from results that said "wide availability on August 20, 2026". The model compares
dates badly. Two things are now worked out here instead:

- Each dated day in a result says how long ago it was, or how far ahead: "August 20,
  2026 (2 months ago)".
- A page that calls a time still to come was written before it. Markets Insider said
  the phone "is expected to arrive sometime in the summer of 2026, most likely during an
  August launch event". Once that time has passed, the hit starts with a note saying so,
  and the model reads the page as the forecast it was. Only a time named after the
  looking-ahead words counts: "released August 20, 2026, and expected to get seven years
  of updates" is a page from after the release.

The phone's source cards keep the page's own words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from app.core.timezone import resolve_timezone
from app.services.calendar_dates import MONTHS, read_dates

# Words that look ahead: "expected to", "could arrive", "will launch", "slated for". "Was
# expected" reports an old forecast and is no forecast itself.
_AHEAD = re.compile(
    r"(?<!\bwas )(?<!\bwere )(?<!\bbeen )\b(?:"
    r"expected|anticipated|rumou?red|slated|set (?:to|for)|scheduled (?:to|for)|planned for"
    r"|upcoming|coming (?:soon|this|next|in|on|later)|likely (?:to|during|in|on)"
    r"|due (?:to|in|on|out)"
    r"|(?:could|should|will|may|might)(?: \w+ly)? (?:arrive|launch|debut|come|land|ship"
    r"|drop|release"
    r"|go on sale|be (?:released|available|announced|unveiled|launched|out))"
    r")\b",
    re.IGNORECASE,
)
# Sentences and clauses: "…later this year; iOS 26 came out in 2025" is two. The point
# after "Sept" or "No" ends no sentence.
_SENTENCE = re.compile(
    r"(?<!\bJan\.)(?<!\bFeb\.)(?<!\bMar\.)(?<!\bApr\.)(?<!\bJun\.)(?<!\bJul\.)"
    r"(?<!\bAug\.)(?<!\bSep\.)(?<!\bSept\.)(?<!\bOct\.)(?<!\bNov\.)(?<!\bDec\.)"
    r"(?<!\bNo\.)(?<=[.!?;])\s+|\n+"
)
# How far past the looking-ahead words a time still belongs to them.
_REACH = 90
# A month named alone, capitalized ("an August launch event"), with its year when one
# follows ("August 2026"). Lowercase "may" is a verb.
_MONTH = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November"
    r"|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\b\.?(?:,?\s+((?:19|20)\d\d)\b)?"
)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
# A year alone is a time ahead only after a word that places it: "slated for 2025".
_YEAR_AHEAD = re.compile(
    r"\b(?:in|by|for|until|of|early|late|mid|mid-|around)\s*((?:19|20)\d\d)\b", re.IGNORECASE
)
# A verb in the past: "sent", "was", "released".
_PAST_TENSE = re.compile(
    r"\b(?:\w{3,}ed|was|were|had|did|sent|said|came|went|began|became|took|held)\b",
    re.IGNORECASE,
)
_MONTH_NAMES = (
    "January February March April May June July August September October November December"
).split()


def local_today(timezone: str | None) -> date:
    return datetime.now(resolve_timezone(timezone)).date()


@dataclass(frozen=True)
class _Time:
    """A time a page names: a year, a month of it, or a day; the parts it names."""

    year: int
    month: int | None = None
    day: int | None = None

    def passed(self, today: date) -> bool:
        if self.month is None:
            return self.year < today.year
        if self.day is None:
            return (self.year, self.month) < (today.year, today.month)
        return (self.year, self.month, self.day) < (today.year, today.month, today.day)

    def written(self) -> str:
        if self.month is None:
            return str(self.year)
        month = _MONTH_NAMES[self.month - 1]
        return f"{month} {self.year}" if self.day is None else f"{month} {self.day}, {self.year}"


def _times_ahead(sentence: str) -> list[_Time]:
    """Each time the sentence names just after its looking-ahead words. One that tells of
    a dated past first reports an old forecast ("On July 7, 2026, Google sent out invites
    for the event, set for August 12") or says when it happened ("Released August 20,
    2026, and expected to get updates"): neither is the page looking ahead. "Preorders
    begin on Sept. 12, 2026, and the iPhones will be released on Sept. 18" still is."""
    times: list[_Time] = []
    for ahead in _AHEAD.finditer(sentence):
        before = sentence[: ahead.start()]
        if _PAST_TENSE.search(before) and _times_in(before, sentence):
            break
        times.extend(_times_in(sentence[ahead.end() : ahead.end() + _REACH], sentence))
    return times


def _times_in(tail: str, sentence: str) -> list[_Time]:
    """A date or a month without a year takes the sentence's year when it names only one;
    with none, it can't be placed ("on Sept. 18"). A year alone counts after a word that
    places it ("slated for 2025")."""
    years = {int(year) for year in _YEAR.findall(sentence)}
    sole_year = next(iter(years)) if len(years) == 1 else None
    times: list[_Time] = []
    covered: list[tuple[int, int]] = []
    for named in read_dates(tail):
        if named.month_word and named.month_word[:1].islower():
            continue
        year = named.year or sole_year
        if year is not None:
            times.append(_Time(year, named.month, named.day))
        covered.append((named.start, named.end))
    for match in _MONTH.finditer(tail):
        if any(start <= match.start() < end for start, end in covered):
            continue
        month = MONTHS.get(match.group(1).lower())
        year = int(match.group(2)) if match.group(2) else sole_year
        if month is not None and year is not None:
            times.append(_Time(year, month))
    if not times:
        times.extend(_Time(int(year)) for year in _YEAR_AHEAD.findall(tail))
    return times


def looked_ahead_to(snippet: str, today: date) -> str | None:
    """The latest past time the page calls still to come ("August 2026"), else None."""
    past = [
        time
        for sentence in _SENTENCE.split(snippet)
        for time in _times_ahead(sentence)
        if time.passed(today)
    ]
    return max(past, key=_latest).written() if past else None


def _latest(time: _Time) -> tuple[int, int, int]:
    # A year alone reaches to its end; a month to its last day.
    return (time.year, time.month or 13, time.day or 32)


def stale_note(snippet: str, today: date) -> str:
    """The note a hit's snippet starts with when it looks ahead to a time already past."""
    when = looked_ahead_to(snippet, today)
    if when is None:
        return ""
    return (
        f"[This page looks ahead to {when}, which has passed: what it calls coming may "
        "have happened since.] "
    )


def _ago(days: int) -> str:
    """How long ago a day was (or, negative, how far ahead): "2 months ago", "in 3 days"."""
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days == -1:
        return "tomorrow"
    span = abs(days)
    if span >= 365:
        unit, size = "year", 365
    elif span >= 60:
        unit, size = "month", 30
    elif span >= 14:
        unit, size = "week", 7
    else:
        unit, size = "day", 1
    count = span // size
    words = f"{count} {unit}{'s' if count != 1 else ''}"
    return f"{words} ago" if days > 0 else f"in {words}"


def mark_dates(text: str, today: date) -> str:
    """Each day the text names with its year, followed by how long ago it was. A day named
    twice in a row ("January 9, 2007 (2007-01-09)") is marked once."""
    marks: list[tuple[int, str]] = []
    last: tuple[date, int] | None = None
    for named in sorted(read_dates(text), key=lambda found: found.start):
        if named.year is None or (named.month_word and named.month_word[:1].islower()):
            continue
        try:
            day = date(named.year, named.month, named.day)
        except ValueError:
            continue
        if last is not None and last[0] == day and named.start - last[1] <= 3:
            continue
        marks.append((named.end, f" ({_ago((today - day).days)})"))
        last = (day, named.end)
    for end, mark in reversed(marks):
        text = text[:end] + mark + text[end:]
    return text


def published_day(published: str, timezone: str | None) -> date | None:
    """The user's own day a page was published, from ``WebSearchHit.published``."""
    try:
        moment = datetime.fromisoformat(published)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(resolve_timezone(timezone)).date()


def published_note(published: str, today: date, timezone: str | None) -> str:
    """The note a hit starts with when its page says when it was published.

    "The 2026 World Series continues on Saturday with Game 2" means the Saturday after
    the day it was written: with the weekday, the model can tell which one it was. The day
    is the user's: a recap posted at 03:30 GMT on the 25th is the 24th in Los Angeles.
    """
    day = published_day(published, timezone)
    if day is None:
        return ""
    month = _MONTH_NAMES[day.month - 1]
    ago = _ago((today - day).days)
    return f"[Published {day.strftime('%A')}, {month} {day.day}, {day.year} ({ago}).] "
