"""The calendar is read, not counted: named dates, the coming week, weekday checks."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.calendar_facts import calendar_lines, correct_weekday_dates, named_dates

_TODAY = date(2026, 10, 18)  # a Sunday


@pytest.mark.parametrize(
    "text, expected",
    [
        # "Christmas this year falls on a Monday" (a Friday) started this.
        ("what day of the week is christmas this year", date(2026, 12, 25)),
        ("christmas next year", date(2027, 12, 25)),
        ("what day was christmas last year", date(2025, 12, 25)),
        # No year: the next time the date comes round.
        ("is my birthday on March 3 a weekend?", date(2027, 3, 3)),
        ("is december 25th on a weekday", date(2026, 12, 25)),
        ("pay rent on oct 31", date(2026, 10, 31)),
        # Any order and form.
        ("what day was July 4, 1976", date(1976, 7, 4)),
        ("I was born on 5 May 1990", date(1990, 5, 5)),
        ("the 3rd of march 2027", date(2027, 3, 3)),
        ("what day is 2027-01-07", date(2027, 1, 7)),
        ("what day is valentines day", date(2027, 2, 14)),
        ("when is meskel this year", date(2026, 9, 27)),
        ("ethiopian new year 2026", date(2026, 9, 11)),
        # Enkutatash is September 12 in the year before a Gregorian leap year.
        ("enkutatash 2027", date(2027, 9, 12)),
        ("enkutatash 2023", date(2023, 9, 12)),
    ],
)
def test_named_dates_reads_the_date_the_message_means(text: str, expected: date) -> None:
    assert [when for _label, when in named_dates(text, _TODAY)] == [expected]


@pytest.mark.parametrize(
    "text",
    ["what is 2 + 2", "may i ask something", "march on, team", "a 5 may be wrong", "february"],
)
def test_named_dates_finds_no_date_in_ordinary_words(text: str) -> None:
    assert named_dates(text, _TODAY) == []


def test_named_dates_lists_each_date_once_in_order() -> None:
    found = named_dates("from Dec 24 to christmas and new year's day", _TODAY)
    assert [when for _label, when in found] == [
        date(2026, 12, 24),
        date(2026, 12, 25),
        date(2027, 1, 1),
    ]


def test_calendar_lines_gives_the_week_and_the_named_dates() -> None:
    lines = calendar_lines(datetime(2026, 10, 18, 14, 0), "what day is christmas")
    assert lines.startswith("The next seven days: Monday October 19, Tuesday October 20,")
    assert "christmas is Friday, December 25, 2026" in lines
    assert "Dates in this message" not in calendar_lines(datetime(2026, 10, 18), "hello")


@pytest.mark.parametrize(
    "text, fixed",
    [
        ("It is Monday, December 25, 2026.", "It is Friday, December 25, 2026."),
        (
            "Christmas falls on **Monday**, December 25, 2026.",
            "Christmas falls on **Friday**, December 25, 2026.",
        ),
        ("Today is Sunday, October 18, 2026.", "Today is Sunday, October 18, 2026."),
    ],
)
def test_correct_weekday_dates_fixes_only_a_wrong_weekday(text: str, fixed: str) -> None:
    assert correct_weekday_dates(text) == fixed
