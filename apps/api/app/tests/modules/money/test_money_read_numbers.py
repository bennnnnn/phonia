"""Numbers read whole: a decimal-comma rate, a term in words with hundreds, time already spent.

A retrospective review of the money reader (2026-11-01) found three ways a believable wrong
number reached a worked answer: "3,5%" read as 5% (a €1,052 payment for €901), "one hundred
twenty months" read as 20 months, and "I've been paying my mortgage at 4% for five years"
read as a 5-year term. Each number is now read whole, or the reader gives it no value.
"""

from __future__ import annotations

import pytest

from app.modules.money.follow_up import follow_up_request
from app.modules.money.phrases import RATE, percent_value
from app.modules.money.purchase import purchase_request
from app.modules.money.read import read_money_request
from app.modules.money.solve import work


@pytest.mark.parametrize(
    ("text", "values", "payment"),
    [
        # A decimal comma is a decimal point.
        (
            "Sara takes out a mortgage of €180.000 at 3,5% for 25 years. "
            "What is her monthly payment?",
            {"rate": 3.5, "amount": 180000, "years": 25},
            901.12,
        ),
        ("€250.000 mortgage at 3,75% over 25 years", {"rate": 3.75, "years": 25}, 1285.33),
        ("car loan of $20,000 at 6,9% APR for 5 years", {"rate": 6.9, "months": 60}, 395.08),
        # A term in words, hundreds and all.
        ("car loan of $20,000 at 6% for one hundred twenty months", {"months": 120}, 222.04),
        ("Mortgage of $200,000 at 5% for three hundred sixty months", {"years": 30}, 1073.64),
        ("car loan of $20,000 at 6% for a hundred and eighty months", {"months": 180}, 168.77),
        ("car loan of $20,000 at 6% for one hundred months", {"months": 100}, None),
        # Look-alikes that were right and stay right.
        ("car loan of $20,000 at 6.9% for five years", {"rate": 6.9, "months": 60}, 395.08),
        ("car loan of $20,000 at 6% for 60 months", {"months": 60}, 386.66),
        ("$1,500 personal loan at 5% for 12 months", {"amount": 1500, "rate": 5}, None),
        ("mortgage of $300,000 at 6.5% for 30 years", {"years": 30}, 1896.2),
        ("I've had a 30-year mortgage of $250k at 4% for 5 years", {"years": 30}, None),
    ],
)
def test_a_number_is_read_whole(text: str, values: dict[str, float], payment: float | None) -> None:
    request = read_money_request(text)
    assert request is not None
    assert {name: request.values.get(name) for name in values} == values
    if payment is not None:
        worked = work(request, None)
        assert worked is not None
        paid = worked.outputs["payment"]
        assert paid is not None and round(paid, 2) == payment


@pytest.mark.parametrize(
    "text",
    [
        # Time already spent is no term: the term is left to the default, said as assumed.
        "I've been paying my $250k mortgage at 4% for five years, should I refinance?",
        "I've been paying my $250k mortgage at 4% for 5 years, should I refinance?",
        "We have paid our $300k mortgage at 6% for 10 years, is it worth refinancing?",
        # A decimal point or a dotted sum is no clause's end (PR review).
        "I've been paying my $250k mortgage at 4.5% for five years, should I refinance?",
        "I've been paying my $250.000 mortgage at 4% for five years, should I refinance?",
        "I've been paying my $1.5k car loan at 4% for 2 years, should I refinance?",
        "We've had our $300k mortgage at 6% for 10 years, refinance?",
        "I've been making payments on my $20k car loan at 7% for 2 years",
    ],
)
def test_time_already_spent_is_no_term(text: str) -> None:
    request = read_money_request(text)
    assert request is not None
    assert "years" not in request.values and "months" not in request.values


@pytest.mark.parametrize(
    "text",
    [
        # A spent verb in another clause leaves the asked loan's term alone (PR review).
        "I've saved $40k for a down payment and want a $300k mortgage at 6% for 15 years.",
        "I've saved $40k, want a $300k mortgage at 6% for 15 years.",
        # Looking, thinking or having an eye on a loan is no time spent paying it.
        "I've been thinking about a $300k mortgage at 5% for 15 years",
        "I've been looking at a $300k mortgage at 6% for 15 years, what's the payment?",
        "I've had my eye on a $300k mortgage at 6% for 15 years",
        # Money paid toward a new loan is no time spent paying one.
        "I've paid $5k toward a down payment on a $300k mortgage at 6% for 15 years, what's "
        "the payment?",
        # A quote or an offer for a loan is a new loan, never one held (coordinator review).
        "We have had a mortgage offer of $300k at 6% for 15 years",
    ],
)
def test_a_term_after_a_spent_clause_is_still_the_term(text: str) -> None:
    request = read_money_request(text)
    assert request is not None and request.values.get("years") == 15


def test_a_loan_quote_keeps_its_term() -> None:
    request = read_money_request(
        "I've had a car loan quote at 7% for 6 years on $20,000, what's the monthly payment?"
    )
    assert request is not None and request.values.get("months") == 72


@pytest.mark.parametrize(
    "text",
    [
        # A comma that may mark thousands is no rate the reader can certify.
        "mortgage of $200,000 at 3,125% for 30 years",
        # A count word before a term the reader did not take in whole.
        "car loan of $20,000 at 6% for two thousand and twenty months",
        # Two rates after a separator are two rates, not the first alone (coordinator review).
        "rates of 3%,4% on a $20,000 car loan for 5 years",
    ],
)
def test_a_number_the_reader_cannot_read_whole_gets_no_worked_numbers(text: str) -> None:
    request = read_money_request(text)
    assert request is None or work(request, None) is None


@pytest.mark.parametrize(
    ("text", "value"),
    [("3.5", 3.5), ("3,5", 3.5), ("3,75", 3.75), ("6,9", 6.9), ("12", 12.0), ("3,125", None)],
)
def test_percent_value(text: str, value: float | None) -> None:
    assert percent_value(text) == value


def test_a_decimal_comma_rate_in_a_follow_up_and_a_purchase_line() -> None:
    earlier = ["car loan 20000 at 7% for 5 years, what's the monthly payment"]
    follow_up = follow_up_request("and at 5,5%?", earlier)
    assert follow_up is not None and follow_up.values.get("rate") == 5.5
    purchase = purchase_request("20k with 6,5 percent", ("I am planing to buy a car",))
    assert purchase is not None and purchase.values.get("rate") == 6.5
    assert purchase_request("20k with 6,125 percent", ("I am planing to buy a car",)) is None


def test_a_percent_starts_at_no_digit_point_or_a_digits_comma() -> None:
    # "3,5%" is one rate, "1000%" no "000%", ".5%" no 5%, and "3%,4%" two rates.
    found = [match["pct"] for match in RATE.finditer("3,5% 1000% .5% 3%,4%")]
    assert found == ["3,5", "3", "4"]
