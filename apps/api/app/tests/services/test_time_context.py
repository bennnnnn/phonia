from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.services import time_context
from app.services.time_context import (
    correct_weekday_dates,
    describe_due_at,
    effective_timezone,
    format_date_answer,
    format_digital_clock,
    format_location_answer,
    format_now_awareness,
    format_time_answer,
    format_time_context,
    format_year_answer,
    is_current_date_question,
    is_local_now_question,
    is_location_question,
    is_shown_clock_question,
    is_time_denial,
    is_time_question,
    is_year_question,
    maybe_local_now_reply,
    normalize_due_at,
)


def test_normalize_due_at_naive_uses_user_timezone():
    due = datetime(2026, 6, 28, 17, 0, 0)
    utc = normalize_due_at(due, "America/New_York")
    assert utc is not None
    assert utc.tzinfo == UTC


def test_describe_due_at_overdue():
    tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    past = (now - timedelta(days=2)).astimezone(UTC)
    label = describe_due_at(past, "UTC")
    assert label.startswith("overdue")


def test_describe_due_at_skips_checked():
    due = datetime.now(UTC) + timedelta(days=1)
    assert describe_due_at(due, "UTC", checked=True) == ""


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what time is it", True),
        ("What time is it?", True),
        ("what time", True),
        ("What time?", True),
        ("what time now", True),
        ("what's the time", True),
        ("current time", True),
        ("tell me the time", True),
        ("again", False),
        ("Again!", False),
        ("one more time", False),
        ("tell me again", False),
        ("refresh", False),
        ("update", False),
        ("update it", False),
        ("is it", False),
        ("what time is it in dc", False),
        ("what time is it in Tokyo", False),
        ("what time is the meeting", False),
        ("what time is my flight", False),
        ("schedule a reminder for 5pm", False),
    ],
)
def test_is_time_question(text, expected):
    assert is_time_question(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what year is it", True),
        ("What year is it?", True),
        ("what year is it now", True),
        ("what year", False),
        ("current year", True),
        ("what's the current year", True),
        ("What’s the year", True),  # curly apostrophe
        ("what year are we in", True),
        ("tell me the year", True),
        ("what year did WWII end", False),
        ("what year was I born", False),
        ("what year is it in Japan", False),
        ("what time is it", False),
        ("U sure?", False),
    ],
)
def test_is_year_question(text, expected):
    assert is_year_question(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what's the date", True),
        ("what is the date", True),
        ("what's today's date", True),
        ("what date is it", True),
        ("current date", True),
        ("Please tell me the current date.", True),
        ("Could you tell me current date?", True),
        ("what day is it", True),
        ("what day is it today", True),
        ("what day", False),
        ("what's today", False),
        ("what is today", False),
        ("what date is Christmas", False),
        ("what day is Christmas", False),
        ("what time is it", False),
    ],
)
def test_is_current_date_question(text, expected):
    assert is_current_date_question(text) is expected


def test_is_local_now_question_covers_time_year_and_date():
    assert is_local_now_question("what time is it") is True
    assert is_local_now_question("what year is it") is True
    assert is_local_now_question("what's the date") is True
    assert is_local_now_question("Please tell me the current date.") is True
    assert is_local_now_question("Could you tell me the current time?") is True
    assert is_local_now_question("what year did WWII end") is False


def test_format_year_answer_uses_timezone_year():
    now = datetime.now(ZoneInfo("UTC"))
    assert format_year_answer("UTC") == f"It's {now.year}."


def test_format_date_answer_uses_local_calendar_day():
    now = datetime.now(ZoneInfo("UTC"))
    assert format_date_answer("UTC") == f"{now.strftime('%A, %B')} {now.day}, {now.year}."


def test_relative_day_answer_uses_the_real_weekday():
    reply = maybe_local_now_reply("3 days after", "America/New_York")
    assert reply is not None
    when = datetime.now(ZoneInfo("America/New_York")) + timedelta(days=3)
    assert when.strftime("%A") in reply
    assert when.strftime("%B") in reply
    assert str(when.day) in reply
    ago = maybe_local_now_reply("And 3 days ago", "America/New_York")
    assert ago is not None
    earlier = datetime.now(ZoneInfo("America/New_York")) - timedelta(days=3)
    assert earlier.strftime("%A") in ago
    assert maybe_local_now_reply("remind me in 3 days", "UTC") is None


def test_correct_weekday_dates_fixes_a_mismatched_name():
    fixed = correct_weekday_dates("Adding three days gives **Monday, October 14, 2026**.")
    assert "Wednesday, October 14, 2026" in fixed
    assert "Monday" not in fixed
    kept = correct_weekday_dates("Today is Sunday, October 11, 2026.")
    assert kept == "Today is Sunday, October 11, 2026."


def test_correct_weekday_dates_reads_through_bold():
    # "Christmas this year falls on a Monday": 2026's is a Friday.
    fixed = correct_weekday_dates("Christmas falls on **Monday**, December 25, 2026.")
    assert fixed == "Christmas falls on **Friday**, December 25, 2026."


def test_format_now_awareness_asks_for_the_full_date_with_a_weekday():
    text = format_now_awareness("Africa/Nairobi", "en")
    assert "When you name the weekday of a date, write the full date with it" in text


def test_format_now_awareness_lists_the_coming_week():
    # "What is Tuesday" on Sunday, October 18 got "Wednesday, October 21".
    with patch.object(time_context, "datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 18, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        text = format_now_awareness("America/New_York", "en")
    assert "The next seven days: Monday October 19, Tuesday October 20," in text
    assert text.endswith("Sunday October 25.")


def test_format_now_awareness_includes_year_month_and_time():
    now = datetime.now(ZoneInfo("America/New_York"))
    text = format_now_awareness("America/New_York", "en")
    assert str(now.year) in text
    assert now.strftime("%B") in text
    assert "Never say you lack a clock" in text
    assert maybe_local_now_reply("what time is it", "UTC") == "```clock\n```"
    now = datetime.now(ZoneInfo("UTC"))
    assert maybe_local_now_reply("what year is it", "UTC") == f"It's {now.year}."
    assert maybe_local_now_reply("what's the date", "UTC") == (
        f"{now.strftime('%A, %B')} {now.day}, {now.year}."
    )
    denial = "Didn't u just says u don't know the time"
    assert is_time_denial(denial) is True
    assert maybe_local_now_reply(denial, "UTC") == (
        "No. I didn't say that. The clock above is the current time."
    )
    assert maybe_local_now_reply("you said you don't know the time", "UTC") == (
        "No. I didn't say that. The clock above is the current time."
    )
    assert is_time_denial("I don't have time") is False
    assert maybe_local_now_reply("I don't know the time of the meeting", "UTC") is None
    shown = maybe_local_now_reply("What time is above", "America/New_York")
    assert shown is not None
    assert "```clock" not in shown
    # The month the reply was written in: a fixed "October" failed every run from November 1.
    assert datetime.now(ZoneInfo("America/New_York")).strftime("%B") in shown
    assert is_shown_clock_question("What time is above") is True
    assert maybe_local_now_reply("what year did WWII end", "UTC") is None
    assert maybe_local_now_reply("what year", "UTC") is None
    assert maybe_local_now_reply("what day", "UTC") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what time is my flight", True),
        ("When is the meeting?", True),
        ("what time does my train leave", True),
        ("what time is it", False),
        ("tell me about flight delays", False),
        ("schedule a reminder for 5pm", False),
    ],
)
def test_is_scheduled_event_time_question(text, expected):
    from app.services.time_context import is_scheduled_event_time_question

    assert is_scheduled_event_time_question(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what time is it in dc", True),
        ("What time is it in Tokyo?", True),
        ("what's the time in London", True),
        ("time in Paris", True),
        ("what time is it", False),
        ("what time", False),
    ],
)
def test_is_remote_time_question(text, expected):
    from app.services.time_context import is_remote_time_question

    assert is_remote_time_question(text) is expected


def test_format_digital_clock_24h():
    when = datetime(2026, 6, 28, 14, 32, 5, tzinfo=ZoneInfo("UTC"))
    assert format_digital_clock(when, "de") == "14:32:05"


def test_format_digital_clock_12h():
    when = datetime(2026, 6, 28, 14, 32, 5, tzinfo=ZoneInfo("UTC"))
    assert format_digital_clock(when, "en") == "02:32:05 PM"


def test_format_time_answer_uses_clock_fence():
    answer = format_time_answer("America/Los_Angeles", "en")
    assert answer == "```clock\n```"


@pytest.mark.parametrize("text", ["what’s the time?", "What’s the time", "ok what’s the time now?"])
def test_curly_apostrophe_time_ask_gets_the_clock_fence(text: str) -> None:
    # iOS smart punctuation types U+2019. The phone's clock card reads this reply, not the ask.
    assert is_time_question(text) is True
    assert maybe_local_now_reply(text, "UTC") == format_time_answer("UTC") == "```clock\n```"


def test_is_location_question():
    assert is_location_question("location")
    assert is_location_question("Where am I?")
    assert is_location_question("Where am I right now")
    assert is_location_question("where am i right nwo")
    assert is_location_question("where am I currently")
    assert is_location_question("Where is my location?")
    assert is_location_question("Where's my location")
    assert is_location_question("What's my location")
    assert is_location_question("what's my current location")
    assert is_location_question("Where am iI")
    assert is_location_question("where am ii")
    assert not is_location_question("weather in Paris")
    assert not is_location_question("Where is the meeting")
    assert not is_location_question("where am I going tomorrow")


def test_location_ask_folded_entries_can_match():
    # A message is folded (letters only, doubles collapsed) before the lookup, so an
    # entry written unfolded ("whatsmycurrentlocation") could never match (ES-42).
    for entry in time_context._LOCATION_ASK_FOLDED:
        assert time_context._fold_location_ask(entry) == entry, entry


def test_format_location_answer_with_city():
    answer = format_location_answer("Los Angeles, CA, United States", "America/Los_Angeles")
    assert "Los Angeles" in answer


def test_format_location_answer_without_city():
    answer = format_location_answer(None, "UTC")
    assert "don't have your location" in answer.lower()


def test_effective_timezone_prefers_client():
    assert effective_timezone("UTC", "America/New_York") == "America/New_York"


def test_effective_timezone_falls_back_to_profile():
    assert effective_timezone("Europe/London", None) == "Europe/London"


def test_effective_timezone_invalid_client_uses_profile():
    assert effective_timezone("America/Chicago", "Not/A/Zone") == "America/Chicago"


def test_evening_is_not_rewritten_as_morning() -> None:
    context = format_time_context("UTC")
    assert "4 in the evening is 16:00" in context
    assert "never 04:00" in context


def test_effective_timezone_invalid_profile_falls_back_to_utc():
    assert effective_timezone("Not/A/Zone", None) == "UTC"
    assert effective_timezone("Not/A/Zone", "Also/Bogus") == "UTC"
