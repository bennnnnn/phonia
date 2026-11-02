"""A line that changes the chat's last money request's term or rate, and every line that
changes something else, which goes to the model.

Live (2026-10-25): "hmm what if i only do 3 years instead" after a used-car loan got no
card, and the model's own arithmetic was off by dollars. Four reviews of wider readers
(same day) each found a new shape they misread as a price, a down payment, a payment, a
kind or a term: "it's 40k miles", "what if I pay 400 instead?", "what about a 2019
model?", "what if my payment is 3%", "it's been 5 years", "what's 7%?". The server now
works a new term or rate only, asked for in a change frame ("what if", "what about",
"and", ... or "... instead") and read by a positive grammar (``change_line``).
"""

from __future__ import annotations

import pytest

from app.modules.money.change_line import read_change
from app.modules.money.follow_up import follow_up_request
from app.modules.money.read import read_money_request

USED = (
    "i'm thinking of buying a used car for 14000, i can put 3000 down. what would my monthly "
    "payment be over 5 years?"
)
CAR = "car loan 14000 with 3000 down at 7.16% for 5 years, what's the monthly payment"
CAR_PLAIN = "car loan 20000 at 7% for 5 years, what's the monthly payment"
USED_8 = "used car loan 8000 at 9% for 48 months"
MORTGAGE = "what is my mortgage for 300k dollars house if mr rate is 1 percent"
MORTGAGE_6 = "mortgage of 300k at 6% for 30 years"
MORTGAGE_SHARE = "what would my mortgage payment be on a 350k house with 20% down"
CARD = "I owe 5000 on my credit card at 22% apr and pay 200 a month, how long to pay off"
SAVINGS = "if I save 200 a month at 4.5% for 10 years how much will I have"
SAVINGS_1K = "if I save 1000 a month at 5% for 20 years how much will I have"
PERSONAL = "personal loan of 10000 at 12% for 36 months"
STUDENT = "student loan of 30000 at 5.5% for 10 years"
BIRR = "mortgage of 3 million birr at 15% for 20 years"
# The live car loan, told over two lines: 20k is the price of the car being bought.
BUYING = ["I am planing to buy a car", "20k with 6 percent"]
WORKOUT = "give me a 4 day workout plan with 4 sets of each exercise"
RECTANGLE = "a rectangle has a perimeter of 40 and a length of 12, what is the width?"


@pytest.mark.parametrize(
    ("earlier", "line", "values", "changed"),
    [
        # The live line: the used car over 36 months, its rate still today's average.
        ([USED], "hmm what if i only do 3 years instead", {"amount": 11000, "months": 36}, ("months",)),
        ([CAR], "hmm what if i only do 3 years instead", {"amount": 11000, "months": 36, "rate": 7.16}, ("months",)),
        ([CAR], "what if i do 3 years instead of 5", {"months": 36}, ("months",)),
        ([CAR], "make it 4 years", {"months": 48}, ("months",)),
        ([CAR], "or 4 years?", {"months": 48}, ("months",)),
        ([CAR], "4 years instead", {"months": 48}, ("months",)),
        ([CAR], "and over 4 years?", {"months": 48}, ("months",)),
        ([CAR], "what if I pay it off in 2 years", {"months": 24}, ("months",)),
        ([CAR_PLAIN], "what about 36mo", {"months": 36}, ("months",)),
        ([MORTGAGE], "what about 15 years?", {"amount": 300000, "rate": 1, "years": 15}, ("years",)),
        ([MORTGAGE_6], "what about 180 months", {"years": 15}, ("years",)),
        ([STUDENT], "what if it's 20 years", {"years": 20}, ("years",)),
        ([PERSONAL], "what about 60 months", {"months": 60}, ("months",)),
        ([SAVINGS], "what about 20 years?", {"deposit": 200, "years": 20}, ("years",)),
        ([SAVINGS], "what if I save for 20 years", {"years": 20}, ("years",)),
        # A rate by its words: "at 6%", "6% apr", "6% interest", "the rate is 6%", "a 6% rate".
        ([CAR], "and at 5%?", {"rate": 5}, ("rate",)),
        ([CAR], "what about a 6% rate", {"rate": 6}, ("rate",)),
        ([CAR], "what about 6% interest", {"rate": 6}, ("rate",)),
        ([STUDENT], "what if the rate was 6.8%", {"rate": 6.8}, ("rate",)),
        ([SAVINGS], "what about 8% apy", {"rate": 8}, ("rate",)),
        ([CAR], "what if the interest rate was 6%", {"rate": 6}, ("rate",)),
        ([MORTGAGE], "what if the rate was 6.5%?", {"rate": 6.5}, ("rate",)),
        ([CARD], "what if the apr was 18%", {"apr": 18}, ("apr",)),
        ([CARD], "what about 15% apr", {"apr": 15}, ("apr",)),
        # Both, in the loan's own words.
        ([MORTGAGE], "what about a 15 year mortgage at 5.5%?", {"rate": 5.5, "years": 15}, ("rate", "years")),
        ([PERSONAL], "what about 24 months at 10%", {"rate": 10, "months": 24}, ("rate", "months")),
        # Each change builds on the one before it.
        ([CAR, "what if i only do 3 years instead"], "and at 5%?", {"rate": 5, "months": 36}, ("rate",)),
        # A sum down comes off the price the request named (14000), never off the loan.
        ([CAR], "what if I put 5000 down?", {"amount": 9000, "months": 60}, ("amount",)),
        ([CAR, "what if i only do 3 years instead"], "and with 5000 down?", {"amount": 9000, "months": 36}, ("amount",)),
        (["400k house with 20% down at 6%"], "with 60k down", {"amount": 340000, "rate": 6}, ("amount",)),
        (["400k house with 20% down at 6%"], "60k down at 5.5%", {"amount": 340000, "rate": 5.5}, ("amount", "rate")),
        (BUYING, "Down payment 3k", {"amount": 17000, "rate": 6}, ("amount",)),
        (BUYING, "down payment of 3,000", {"amount": 17000}, ("amount",)),
        (BUYING, "the down payment is 3k", {"amount": 17000}, ("amount",)),
        (BUYING, "with 3k down", {"amount": 17000}, ("amount",)),
        (BUYING, "3k down", {"amount": 17000}, ("amount",)),
        (BUYING, "and 3k down?", {"amount": 17000}, ("amount",)),
        (BUYING, "I can put 3 grand down", {"amount": 17000}, ("amount",)),
        (BUYING, "I'm putting 3k down for 4 years", {"amount": 17000, "months": 48}, ("amount", "months")),
        (BUYING, "im putting 3k down", {"amount": 17000}, ("amount",)),
        (BUYING, "we want to put 3k down", {"amount": 17000}, ("amount",)),
    ],
)  # fmt: skip
def test_a_new_term_or_rate_is_the_last_request_changed(
    earlier: list[str], line: str, values: dict[str, float], changed: tuple[str, ...]
) -> None:
    request = follow_up_request(line, earlier)
    assert request is not None
    assert {name: request.values.get(name) for name in values} == values
    assert request.changed == changed


@pytest.mark.parametrize(
    ("earlier", "line"),
    [
        # Not a money chat, or one that moved on.
        ([WORKOUT], "what if i only do 3 sets instead"),
        (["what's a good name for a cat"], "3 years"),
        ([], "3 years"),
        ([RECTANGLE], "what if the perimeter was 48?"),
        ([CAR, "how do I make lasagna?"], "what if i only do 3 years instead"),
        (
            [CAR, "what if 3 years instead", "and 4 years?", "ok and 5000 down"],
            "what about 72 months",
        ),
        (["what are car loan rates right now"], "what about 72 months?"),
        # A length of time that is not the loan's, or one no slider of it reaches.
        ([CAR], "what if it was 3 years ago"),
        ([CAR], "what if I was 30 years old"),
        ([MORTGAGE_6], "what if I'm 30 years"),
        ([CAR], "what if I wait 2 years to buy"),
        ([CAR], "what if I keep the car for 10 years"),
        ([CAR], "what if I go from 60 to 36 months"),
        ([MORTGAGE], "what if I sell after 5 years?"),
        ([MORTGAGE_6], "what if rates are 5% in 2 years"),
        ([MORTGAGE_6], "what if rates are 5% for 2 years then go up"),
        ([MORTGAGE_6], "what if it's 5% for 2 years"),
        ([MORTGAGE_6], "what if the rate is 6% for 10 years"),
        ([MORTGAGE_6], "what if I take 6 months of maternity leave"),
        ([STUDENT], "what if I get 2 years of deferment"),
        ([CAR_PLAIN], "what if I get 3 months free"),
        ([CAR_PLAIN], "what if I get 0% for 12 months"),
        ([CAR_PLAIN], "what if I save for 2 years"),
        ([CARD], "what about 20 years"),
        # A percent that is not the loan's rate.
        ([CAR_PLAIN], "what if sales tax is 7%"),
        ([MORTGAGE_6], "what if property tax is 1.2%"),
        ([SAVINGS], "what if I get a 5% match from my employer"),
        ([CARD], "what if I get 2% back"),
        ([MORTGAGE_6], "what if I'm at 80% LTV"),
        ([CAR_PLAIN], "what if it's at 85% of msrp"),
        ([CAR], "what if the rate is 6% down from 7.16%"),
        ([MORTGAGE_6], "what if it's 20%"),
        ([CAR], "what if rates drop 1% next year?"),
        ([CAR], "lol 100%"),
        ([CAR], "is 7% a good rate?"),
        # Not asked as a change: no frame ("what if", "what about", "and", "... instead").
        ([CAR], "36 months?"),
        ([CAR], "same thing but 4 years"),
        ([CAR], "what would it be at 5%?"),
        ([CAR], "so at 5%?"),
        # A bare percent, or a question about one: no rate words.
        ([CAR], "7%"),
        ([CAR], "what if it's 5%"),
        ([SAVINGS], "what about 8%"),
        # The fourth review: a bare percent after a share put down, time gone by, a point in
        # time, an interest-only loan, a question about a percent.
        ([MORTGAGE_SHARE], "what about 15%?"),
        ([MORTGAGE_SHARE], "3.5%?"),
        ([MORTGAGE_6], "it's been 5 years"),
        ([CAR_PLAIN], "what if it's been 3 years"),
        ([MORTGAGE_6], "what about at 5 years?"),
        ([MORTGAGE_6], "and at 10 years?"),
        ([MORTGAGE_6], "what about 6% interest only"),
        ([MORTGAGE_6], "what about 6% interest-only?"),
        ([MORTGAGE_6], "is it 6%?"),
        ([MORTGAGE_6], "was it 6%?"),
        ([MORTGAGE_6], "what is 6%?"),
        ([MORTGAGE_6], "what's 7%?"),
        ([MORTGAGE_6], "what about 2 years from now"),
        ([CAR_PLAIN], "what about 3 years left"),
        ([MORTGAGE_6], "what if I did it for 10 years"),
        # A bare percent beside another change needs its rate words too.
        ([CAR_PLAIN], "what about 48 months instead of 60 and 5% instead of 7%"),
        # The third review: a card payment as a percent, "new" beside a rate or price.
        ([CARD], "what if my payment is 3%"),
        ([CARD], "what if the monthly payment was 4%"),
        ([CARD], "what if I only do 3%"),
        ([USED], "what if the new rate is 9%"),
        ([USED], "what if the new price is 12k"),
        # A price, an amount, a percent down, a payment, a deposit or a kind: the model's.
        ([CAR], "what if I put 20% down?"),
        ([CAR], "what if the car was $18,000?"),
        ([CAR], "what if I only borrow 8000?"),
        ([MORTGAGE_6], "what about 400k?"),
        ([CARD], "what if I pay 300 a month instead?"),
        ([CARD], "what if I owe 8000"),
        ([CARD], "what if I pay 1000 now"),
        ([SAVINGS], "what if I save 300 a month instead"),
        ([SAVINGS], "what if I start with 5000"),
        ([CAR], "what if it was a used car?"),
        ([USED], "what if it was new instead"),
        ([BIRR], "what if it was $400k"),
        # The third review's lines.
        ([USED_8], "what about a 2019 model?"),
        ([USED_8], "what if it's a 2015"),
        ([MORTGAGE_SHARE], "what if I put 20% down, so 80k"),
        ([USED], "what if I put 25% down, 3500"),
        ([MORTGAGE_SHARE], "what about 3.5 down?"),
        ([CAR_PLAIN], "10 down?"),
        ([SAVINGS_1K], "what if I make 3000 a month"),
        ([CARD], "what if I'm paid 3000 a month"),
        # The earlier reviews' lines.
        ([CAR_PLAIN], "what if I pay 400 instead?"),
        ([CAR_PLAIN], "what if the trade-in is worth 4000"),
        ([CAR_PLAIN], "what if it's 40k miles"),
        ([MORTGAGE_6], "what if the house is 1500 sq ft"),
        ([CAR_PLAIN], "what about 36m"),
        ([CAR_PLAIN], "and with 60k salary?"),
    ],
)
def test_a_line_that_changes_no_term_or_rate_is_none(earlier: list[str], line: str) -> None:
    assert follow_up_request(line, earlier) is None


@pytest.mark.parametrize(
    ("earlier", "line"),
    [
        (BUYING, "down payment assistance programs?"),
        (BUYING, "what's a good down payment?"),
        (BUYING, "I put 3k down on my old car last year"),
        # Not the user's own: the model asks whether to work it.
        ([CAR_PLAIN], "the dealer wants 3k down"),
        # A sum the user called a loan or a balance has no price to come off.
        ([CAR_PLAIN], "3k down"),
        ([MORTGAGE_6], "with 60k down"),
        (["I owe 15k on my car loan at 6%"], "what if I put 3k down"),
        (["refinance my 250k mortgage at 6%"], "with 10k down"),
        # Gone by, only talked about, a year, or a currency the loan does not have.
        (BUYING, "I put 3k down"),
        (BUYING, "we put 3k down"),
        (BUYING, "it was 3k down"),
        (BUYING, "it's 3k down"),
        (BUYING, "is it 3k down"),
        (BUYING, "my down payment was 3k"),
        (BUYING, "down payment 2026"),
        (["I am planing to buy a car", "$20k with 6 percent"], "€3k down"),
        # Told of a down payment made, not asked: only "what if I put" is one.
        (BUYING, "and I put 3k down"),
        (BUYING, "I put 3k down instead"),
        # A line read with two rates is not worked further.
        (
            [
                "car loan 25000 with 5000 down 6.9% apr 60 months, is that better than the 8% apr my bank offered?"
            ],
            "with 3k down",
        ),
        # No money down in the line: "a 400k home" may be an equity line or a refinance.
        (["I have a 400k home and owe 250k at 6%"], "with 50k down"),
        (["a 400k home equity loan at 8%"], "with 50k down"),
        (["a 400k home, refinancing at 6%"], "with 50k down"),
        (["20k car repairs at 9%"], "with 5k down"),
        (["20k car leasing at 6%"], "with 5k down"),
        (BUYING, "$0 down"),
        (BUYING, "no money down"),
        (BUYING, "3k down and 5k down"),
        (BUYING, "20k down"),
        ([], "down payment 3k"),
        # Only what a loan buys takes a down payment.
        ([SAVINGS], "3k down"),
        ([CARD], "3k down"),
        ([PERSONAL], "with 3k down"),
        ([STUDENT], "3k down"),
        ([BIRR], "$300k down"),
        # No rate in the line, so the first turn's own reading is not built on.
        ([MORTGAGE_SHARE], "with 60k down"),
    ],
)
def test_a_down_payment_that_fits_no_loan_is_none(earlier: list[str], line: str) -> None:
    assert follow_up_request(line, earlier) is None


def test_a_down_payment_in_a_currency_gives_the_loan_that_currency() -> None:
    request = follow_up_request("down payment $3k", BUYING)
    assert request is not None and request.currency == "USD"
    assert request.values["amount"] == 17000


def test_a_second_down_payment_replaces_the_first() -> None:
    earlier = [*BUYING, "Down payment 3k"]
    request = follow_up_request("with 5k down instead", earlier)
    assert request is not None
    assert (request.values["amount"], request.price, request.down) == (15000, 20000, 5000)


def test_an_earlier_line_is_read_in_its_own_turns_parts() -> None:
    """Review (2026-10-25): the whole of this line read as a loan of 9; its turn's money
    part was the car loan of 20000."""
    parts = ("set a reminder for 9 tomorrow", "what's the payment on a 20000 car loan at 6%")
    request = follow_up_request("what about 3 years", [parts])
    assert request is not None
    assert request.values == {"amount": 20000, "rate": 6, "months": 36}


def test_the_kind_stays_the_requests_own() -> None:
    request = follow_up_request("hmm what if i only do 3 years instead", [USED])
    assert request is not None and request.variant == "used"


def test_a_first_ask_is_no_follow_up() -> None:
    """The reader of a request alone stays as it was; the follow-up is the turn's to ask."""
    assert follow_up_request(CAR, []) is None
    first = read_money_request(CAR)
    assert first is not None and first.changed == ()


@pytest.mark.parametrize(
    ("line", "rate", "term"),
    [
        ("and at 6%?", 6, None),
        ("what about 6% apr", 6, None),
        ("what if it was 6% interest", 6, None),
        ("what if the rate is 6%", 6, None),
        ("6.5% apr instead", 6.5, None),
        ("what about over 4 years", None, (4, "years")),
        ("hmm what if i only do 3 years instead", None, (3, "years")),
        ("what about a 15 year mortgage at 5.5%", 5.5, (15, "year")),
        # A count in words, as a book writes it (2026-10-31).
        ("what if seven years instead", None, (7, "years")),
        ("what about twenty-five years", None, (25, "years")),
    ],
)
def test_the_grammar_reads_a_term_and_a_rate(
    line: str, rate: float | None, term: tuple[float, str] | None
) -> None:
    change = read_change(line)
    assert change is not None and (change.rate, change.term) == (rate, term)
