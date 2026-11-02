"""One reader of dates the user names: every feature reads the same spellings.

The reminder reader, recurring pay and the calendar facts each had a month table:
"2027-1-7" was a date to one and not another, and "remind me on 2026-12-25" named no
day to reminders (code-health audit DUP-09).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.chat.recurring_pay import _parse_target_date
from app.modules.todos.spoken_when import find_when
from app.services.calendar_dates import read_dates
from app.services.calendar_facts import named_dates

_TODAY = date(2026, 10, 20)


@pytest.mark.parametrize(
    ("spelling", "month", "day"),
    [
        ("December 25", 12, 25),
        ("Dec 25th", 12, 25),
        ("25 December", 12, 25),
        ("the 25th of December", 12, 25),
        ("Sept 3", 9, 3),
        ("2026-12-25", 12, 25),
        ("2027-1-7", 1, 7),
    ],
)
def test_every_feature_reads_the_date(spelling: str, month: int, day: int) -> None:
    reminder = find_when(f"remind me on {spelling} to call mom")
    assert reminder.day == f"{month:02d}-{day:02d}"
    facts = named_dates(f"what day is {spelling}?", _TODAY)
    assert [(when.month, when.day) for _label, when in facts] == [(month, day)]
    paid = _parse_target_date(f"how much will I have by {spelling}", _TODAY)
    assert paid is not None and (paid.month, paid.day) == (month, day)


def test_a_slash_date_is_read_only_where_asked() -> None:
    assert [(d.month, d.day) for d in read_dates("by 12/25", slash=True)] == [(12, 25)]
    assert read_dates("by 12/25") == []


def test_the_reminder_cuts_the_lead_word_with_the_date() -> None:
    text = "remind me on 2026-12-25 to call mom"
    when = find_when(text)
    start, end = when.spans[0]
    assert text[start:end] == "on 2026-12-25"


def test_a_lowercase_may_day_first_is_a_verb_to_the_calendar_facts() -> None:
    assert named_dates("a 5 may be wrong", _TODAY) == []
