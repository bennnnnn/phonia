"""A time from now ("in 3 minutes") is a stated time, due that long after the message."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.todos.reply_claims import without_when_questions
from app.modules.todos.spoken_add import (
    chat_add_needs_a_stated_time,
    parse_spoken_add,
    relative_due,
    user_named_a_clock,
)
from app.modules.todos.spoken_when import find_when

_NOW = datetime(2026, 10, 14, 6, 0, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("remind me to stretch in 3 minutes", 3),
        ("remind me in 2 hours to call mom", 120),
        ("remind me to drink water in 30 mins", 30),
        ("remind me in 5 min", 5),
        ("remind me in half an hour to check the oven", 30),
        ("remind me in an hour and a half to eat", 90),
        ("remind me in 1.5 hours", 90),
        ("remind me in a couple of hours", 120),
        ("remind me to call the bank 20 minutes from now", 20),
        ("remind me after 10 minutes to turn off the stove", 10),
        ("remind me in a week to renew the permit", 7 * 1440),
        ("remind me to pay rent in 3 days", 3 * 1440),
    ],
)
def test_find_when_reads_a_time_from_now(text: str, minutes: int) -> None:
    assert find_when(text).after_minutes == minutes


@pytest.mark.parametrize(
    "text",
    [
        "remind me tomorrow at 9am",  # a day and a clock win
        "remind me to stretch in the morning",
        "I live in 2 places",
        "remind me in 900 weeks",  # past a year is not a reminder
        "remind me in a few minutes",  # how many is not said
    ],
)
def test_find_when_leaves_other_words_alone(text: str) -> None:
    assert find_when(text).after_minutes is None


@pytest.mark.parametrize(
    "text",
    ["remind me to stretch in 3 minutes", "remind me in 2 hours to call mom"],
)
def test_a_time_from_now_is_a_stated_time(text: str) -> None:
    assert user_named_a_clock(text)
    assert not chat_add_needs_a_stated_time(text, _NOW)


@pytest.mark.parametrize(
    ("text", "title", "after"),
    [
        ("remind me to stretch in 3 minutes", "stretch", timedelta(minutes=3)),
        ("remind me in 2 hours to call mom", "call mom", timedelta(hours=2)),
        ("remind me to drink water in 30 mins", "drink water", timedelta(minutes=30)),
    ],
)
@pytest.mark.parametrize("zone", ["Africa/Nairobi", "America/Los_Angeles", "UTC"])
def test_relative_due_is_now_plus_the_time_on_any_clock(
    text: str, title: str, after: timedelta, zone: str
) -> None:
    add = parse_spoken_add(text)
    assert add is not None and add.title == title
    due = relative_due(text, user_timezone=zone, now=_NOW)
    assert due is not None and due.astimezone(UTC) == _NOW + after


def test_no_time_from_now_gives_no_relative_due() -> None:
    assert relative_due("remind me to call mom tomorrow at 6pm", user_timezone="UTC") is None


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        ("When should I remind you?", ""),
        ("Sure! When should I remind you to drink water?", ""),
        ("Stretching is good for you. What time works?", "Stretching is good for you."),
        ("I'll remind you to stretch.", "I'll remind you to stretch."),
        ("```python\nprint('when?')\n```", "```python\nprint('when?')\n```"),
    ],
)
def test_without_when_questions(reply: str, kept: str) -> None:
    assert without_when_questions(reply) == kept
