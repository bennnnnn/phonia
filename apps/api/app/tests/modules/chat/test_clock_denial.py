"""A reply swapped for the clock only when the user asked the clock and the reply denies it."""

from __future__ import annotations

import pytest

from app.modules.chat.clock_denial import model_denies_clock

_LIVE = "I don't have access to real-time information, so I can't tell you"
_DENIAL = f"{_LIVE} the time. You can check your device's clock."


@pytest.mark.parametrize(
    ("reply", "asked"),
    [
        (
            "I don't have access to the current clock, so I can't tell you the exact time "
            "right now.",
            "what time is it",
        ),
        (_DENIAL, "do you know what time it is"),
        (_DENIAL, "yo whats the time rn"),
        (_DENIAL, "what time is it bro"),
        (_DENIAL, "time?"),
        (_DENIAL, "what's today's date"),
        (_DENIAL, "what day is it"),
        (_DENIAL, "what time is it in my time zone"),
        (_DENIAL, "what time is it 😅"),
        (_DENIAL, "what's the date and time"),
        (_DENIAL, "tell me the time and date"),
        (_DENIAL, "what day and time is it"),
        (_DENIAL, "what time is it? i have a meeting at 4"),
        ("I don’t have access to a clock, sorry!", "do you know what time it is"),
        (
            "I can't tell you the current time at the moment, since I don't have access to "
            "real-time data.",
            "what time is it",
        ),
        (
            f"{_LIVE} what time it is right now. Would you like me to help you plan your "
            "schedule for the day?",
            "what time is it",
        ),
    ],
)
def test_a_clock_ask_denied_is_swapped(reply: str, asked: str) -> None:
    assert model_denies_clock(reply, asked)


@pytest.mark.parametrize(
    ("reply", "asked"),
    [
        # The live chat: a denial of the weather became the clock (2026-10-25).
        (f"{_LIVE} tomorrow's weather in Chicago.", "I told you, chicago"),
        ("I don't have access to real-time sports scores.", "did the bears win today"),
        (f"{_LIVE} the date of the next election.", "when is the next election"),
        (f"{_LIVE} the opening time of the store.", "when does target open"),
        (f"{_LIVE} the sunset time in Chicago.", "when is sunset"),
        (f"{_LIVE} the current wait time.", "how long is the wait at disney"),
        (
            "CVS usually closes at 10 PM. I don't have real-time data, so check the current "
            "time on your phone.",
            "is cvs still open",
        ),
        (
            "Daylight saving time ends on Sunday, November 1, 2026. I don't have real-time "
            "access, but set your clocks back one hour.",
            "when do the clocks go back",
        ),
        # Another place's clock.
        (f"{_LIVE} the current time in Tokyo.", "and in tokyo?"),
        (
            "I can't access real-time data, but Tokyo's local time is 14 hours ahead of "
            "Chicago, so it's about 5:22 AM there.",
            "whats the time over in tokyo",
        ),
        (
            "I can't tell you the current time there, but London is 5 hours ahead.",
            "what about london",
        ),
        ("I don't have access to a clock.", "what time is it in tokyo"),
        # A scheduled time, or another thing's date.
        ("I can't tell you the exact time right now.", "what time is my flight"),
        (_DENIAL, "what time is it playing at amc"),
        (_DENIAL, "what's the date of easter"),
        (_DENIAL, "what's the date and time in tokyo"),
        (_DENIAL, "whats the date and time of the eclipse"),
        (_DENIAL, "what time is it (in tokyo)"),
        # The clock and something else live: the reply is about both.
        (_DENIAL, "what time is it and whats the weather"),
        # No denial, a long reply, or no ask.
        ("It's 3:20 PM.", "what time is it"),
        ("I don't have access to the clock. " + "More words. " * 40, "what time is it"),
        (_DENIAL, ""),
    ],
)
def test_other_replies_are_left_alone(reply: str, asked: str) -> None:
    assert not model_denies_clock(reply, asked)
