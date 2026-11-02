"""One value per slot: a money request is worked only from what it says once, read whole.

The second review of the Ethiopian-book fix (2026-10-31) found the reader keeping the
first of two rates ("a 15-year at 5.5% or a 30-year at 6.25%"), reading "EUR 25.000" as
25.00 and a 0, a plan's name as a sum, a weekly deposit as a start, and an unread
compounding word as monthly. Each slot (sum, rate, term, money down, compounding) now
takes one value read whole, or the message gets no worked numbers and the model answers.
"""

from __future__ import annotations

import pytest

from app.modules.money.read import read_money_request


@pytest.mark.parametrize(
    "text",
    [
        # Two rates: a comparison, a refinance, a rate that moved.
        "Is it better to get a 15-year mortgage at 5.5% or a 30-year at 6.25% on $400,000?",
        "refinance: currently 7% on my $300k mortgage with 27 years left, new rate 6% for 30 years",
        "I have a 30-year mortgage with $250k left at 7%, should I refinance to a 15-year at 5.5%?",
        "Refinance my $200,000 mortgage from 6.8% to 5.9%, 25 years remaining",
        "Our mortgage rate went from 3% to 7% on 300k",
        "mortgage 300k, rate is 6% down from 7%",
        "car loan 25000 6.9% 60 months, is that better than the 8% apr my bank offered?",
        "I invest 15% of my $80,000 salary each year at 7% return for 30 years",
        # Two terms.
        "compare 15 vs 30 year mortgage on $350,000 at 6%",
        "compare a 15 year and a 30 year mortgage of 300k at 6%",
        "mortgage of $300,000 at 6%, 15 or 30 years?",
        "Should I take a 3 year or 5 year car loan for 25k at 7%?",
        "car loan 25k at 7%, 36 or 60 months?",
        "car loan 20000 at 6% for 2 years and 6 months",
        # Two sums for the money down.
        "a 400k house with 20% down or 50k down, mortgage at 6%",
        # A sum the reader cannot read whole is no sum of 5 or 0.
        "home loan of 5 lakh at 9% for 15 years",
        "a $1.2 billion loan at 5% for 10 years",
        "€1.250 million loan at 5%",
        # A deposit paid each week no product works.
        "I'm saving $200 a week at 4% for 3 years in a savings account",
        "savings account at 5%, I put in 50 every week for 2 years",
        # A compounding word not read into a frequency is never worked as monthly.
        "$5,000 in a savings account at 5%, interest is compounded and paid quarterly, for 4 years",
        "savings of 5000 birr at 6%, compounded at the end of each quarter, for 4 years",
        "savings of 5000 at 6%, compounding happens quarterly, for 4 years",
        "savings of 5000 at 6% compounded 4 times annually for 4 years",
        "savings of 1000 at 3% compounded for 5 years",
        # Interest said to be simple is no amortised or compounded sum.
        "What is the interest on a loan of $4,000 at 6% per year for 3 years, if interest is simple?",
        "Put $2,000 in a savings account at 5% per annum for 3 years with no compounding. How much interest?",
        "Almaz borrowed Birr 12,000 at 9% per annum for 2 years. Find the interest using I = PRT.",
    ],
)  # fmt: skip
def test_a_slot_with_two_values_or_one_unread_works_no_numbers(text: str) -> None:
    assert read_money_request(text) is None


@pytest.mark.parametrize(
    ("text", "name", "value"),
    [
        # Every grouping of digits, read whole.
        ("EUR 25.000 car loan at 5% for 4 years", "amount", 25000),
        ("ETB 250.000 house loan at 12% for 20 years", "amount", 250000),
        ("ETB 10.000,50 in a savings account at 7% for 3 years", "start", 10000.5),
        ("a 1.000.000 birr loan at 12% for 5 years", "amount", 1000000),
        ("€10.000 car loan at 5% for 4 years", "amount", 10000),
        ("₹5,00,000 home loan at 8.5% for 20 years", "amount", 500000),
        ("Birr 1.5 million car loan at 14% for 5 years", "amount", 1500000),
        # "N% down" is the share of the price put down, never the rate.
        ("20% down on a $400k home at 6.5%", "amount", 320000),
        ("20% down on a $400k home at 6.5%", "rate", 6.5),
        ("10% down on a 300,000 birr car at 18% for 4 years", "amount", 270000),
        ("10% down on a 300,000 birr car at 18% for 4 years", "rate", 18),
        ("20 percent down on a 400k house, mortgage at 6.5% for 30 years", "amount", 320000),
        # A plan's name is no sum.
        ("My 401k has $50k, investing at 7% for 20 years", "start", 50000),
        # A sum paid each month, said with no other money word.
        ("savings of 5000 at 6% compounded quarterly and 200 a month deposits for 4 years", "deposit", 200),
        # Only "ago", an age and time gone by leave a length of time out of the term.
        ("I'll save $200 a month at 5% for 20 years into retirement", "years", 20),
        ("lock in a 300k mortgage at 6% for 15 years since rates are falling", "years", 15),
        ("mortgage 300k at 6% for 15 years back to back with my wife", "years", 15),
        ("How much a month to pay off a $5,000 loan in two years at 10%?", "years", 2),
        # One rate said twice is one rate.
        ("car loan of 20000 at 6%; at 6% what is the payment over 5 years", "rate", 6),
    ],
)  # fmt: skip
def test_a_slot_said_once_is_read(text: str, name: str, value: float) -> None:
    request = read_money_request(text)
    assert request is not None and request.values[name] == value


def test_my_401k_investment_is_no_sum_of_401000() -> None:
    assert (
        read_money_request("my 401k investment grew 7% in five years, should I keep investing?")
        is None
    )
