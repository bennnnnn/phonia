from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.chat.recurring_pay import (
    format_recurring_pay_reply,
    maybe_recurring_pay_reply,
    parse_recurring_pay_request,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


def test_reported_biweekly_question_uses_local_today_and_shows_assumptions() -> None:
    text = (
        "if i make 3400 a every 2 weeks, how much money would i make untill dcember 11th from today"
    )
    estimate = parse_recurring_pay_request(text, "America/Los_Angeles", now=NOW)
    assert estimate is not None
    assert estimate.elapsed_days == 76
    assert estimate.interval_days == 14
    assert estimate.full_periods == 5
    assert estimate.remainder_days == 6

    reply = format_recurring_pay_reply(estimate)
    assert "Saturday, September 26, 2026" in reply
    assert "Friday, December 11, 2026" in reply
    assert "76 days = 5 × 14 days + 6 days" in reply
    assert "Oct 10 → Oct 24 → Nov 7 → Nov 21 → Dec 5" in reply
    assert "5 × $3,400 = $17,000" in reply
    assert "**Estimated total: $17,000** ✓" in reply
    assert "today is already a payday" in reply
    assert "6 × $3,400 = $20,400" in reply
    assert "76 ÷ 14 × $3,400 = $18,457.14" in reply
    assert "\\times" not in reply
    assert "{,}" not in reply
    assert "```answer" not in reply


def test_weekly_question_without_space_before_article_is_calculated() -> None:
    text = (
        "If i make 1500a week, how much would i make until December 11th? "
        "Please tell me the current date."
    )
    estimate = parse_recurring_pay_request(text, "America/Los_Angeles", now=NOW)
    assert estimate is not None
    assert estimate.amount == 1500
    assert estimate.interval_days == 7
    assert estimate.elapsed_days == 76
    assert estimate.full_periods == 10
    assert estimate.remainder_days == 6

    reply = format_recurring_pay_reply(estimate)
    assert "Saturday, September 26, 2026" in reply
    assert "Friday, December 11, 2026" in reply
    assert "76 days = 10 × 7 days + 6 days" in reply
    assert "10 × $1,500 = $15,000" in reply
    assert "**Estimated total: $15,000** ✓" in reply
    assert "11 × $1,500 = $16,500" in reply
    assert "76 ÷ 7 × $1,500 = $16,285.71" in reply


@pytest.mark.parametrize(
    "text",
    [
        "I get paid $3,400 biweekly. How much will I earn by December 11?",
        "$3,400 every two weeks — what is my total through 12/11/2026?",
        "My pay is USD 3400 per 14 days. What would I make between now and 2026-12-11?",
        "I earn 1700 every week. How much money will I make until 11 December 2026?",
        "I receive 3400 every other week. What is the total between today and Dec 11th?",
        "I earn $1,500 weekly. How much will I make through December 11th?",
        "I get paid 1500/week. What is my total until December 11?",
        "My pay is USD 200 daily. What will I make by Dec 11?",
        "I make 1500 once a week. How much would I earn until December 11?",
    ],
)
def test_equivalent_phrasings_are_owned_by_the_same_calculator(text: str) -> None:
    reply = maybe_recurring_pay_reply(text, "America/Los_Angeles", now=NOW)
    assert reply is not None
    assert "**1. Count the time**" in reply
    assert "**Estimated total:" in reply


@pytest.mark.parametrize(
    "text",
    [
        "How much money is 3400 US dollars in euros by December 11?",
        "I get paid every two weeks. How much by December 11?",
        "I make 3400 every 2 weeks. What is that annually?",
        "Schedule a meeting every 2 weeks until December 11.",
    ],
)
def test_declines_requests_without_amount_cadence_income_and_end_date(text: str) -> None:
    assert maybe_recurring_pay_reply(text, "America/Los_Angeles", now=NOW) is None


def test_explicit_past_date_gets_a_clear_correction() -> None:
    reply = maybe_recurring_pay_reply(
        "I earn $3400 every two weeks. How much by December 11, 2025?",
        "America/Los_Angeles",
        now=NOW,
    )
    assert reply is not None
    assert "is before today" in reply
