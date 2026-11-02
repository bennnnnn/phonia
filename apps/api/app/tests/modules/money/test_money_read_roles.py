"""What each number in a money request is: the term, the compounding, the loan.

From the Ethiopian grade 11 and 12 books (2026-10-31) and the review of their fix: a term in
words, "compounded quarterly", a price with a deposit; and the look-alikes that must not
change (an age or time gone by is no term, two prices compared name no loan, an exchange
rate or a note is no sum, a sum owed is the loan as it stands).
"""

from __future__ import annotations

import pytest

from app.modules.money.read import read_money_request

_ALULA = (
    "Ato Alula deposited Birr 3,000 in a saving account that pays 6% interest rate per year, "
    "compounded quarterly. What is the amount of interest obtained at the end of seven years? "
    "(No deposit or withdrawal is made in these seven years)"
)
_MOGES = (
    "Moges wants to buy a house that costs Birr 250,000. He has saved Birr 50,000 which he "
    "will use as a deposit, and will finance the rest of the cost by taking out a loan. The "
    "loan is to be paid back in equal monthly instalments, amortized over 30 years, at an "
    "annual interest rate of 7%. What will his monthly payment be?"
)


@pytest.mark.parametrize(
    ("text", "term"),
    [
        (_ALULA, {"years": 7}),
        ("car loan 20000 at 6% for five years", {"months": 60}),
        ("mortgage of 300k at 6% over twenty-five years", {"years": 25}),
        ("borrow 10000 at 8% for two and a half years", {"years": 2.5}),
        ("personal loan of 5000 at 12% for eighteen months", {"months": 18}),
        ("car loan 20000 at 6% for 5 years", {"months": 60}),
        ("a car loan of 20000 at 6% that will last 5 years", {"months": 60}),
        # An age, time gone by or a gap is no term, in digits or words (review, 2026-10-31).
        ("Ten years ago I took out a $200k mortgage at 4% for 30 years", {"years": 30}),
        ("I'm thirty years old and want to invest $500 a month at 7% for 35 years", {"years": 35}),
        ("I took a $15,000 loan at 7% two years ago for five years", {"years": 5}),
        ("I've been paying for three years on my 30 year mortgage of $300k at 6%", {"years": 30}),
        ("I made twelve months of payments on a $300k mortgage at 6%, 30 years", {"years": 30}),
        ("Our kids are five years apart; I borrow 20k at 6% for 3 years", {"years": 3}),
        ("I am 30 years old, mortgage of 300k at 6% over 15 years", {"years": 15}),
        ("savings of 1000 at 3% for 10 years, I've saved for the past 2 years", {"years": 10}),
    ],
)  # fmt: skip
def test_the_term_is_the_length_of_time_said_as_one(text: str, term: dict[str, float]) -> None:
    request = read_money_request(text)
    assert request is not None
    assert {name: request.values[name] for name in term} == term


@pytest.mark.parametrize(
    "text",
    [
        "My son is five years old; save $100 a month at 5% for his college",
        "a $200k mortgage at 4%, it's been 5 years",
        "a 5-year-old car, car loan of 12000 at 9%",
        "I am 30 years old, mortgage of 300k at 6%",
    ],
)
def test_a_length_of_time_that_is_no_term_leaves_the_default(text: str) -> None:
    request = read_money_request(text)
    assert request is not None
    assert not {"years", "months"} & set(request.values)


@pytest.mark.parametrize(
    ("text", "per_year"),
    [
        (_ALULA, 4),
        ("I have $5000 in savings at 4% compounded semi-annually for 10 years", 2),
        ("save 200 a month at 5% with quarterly compounding for 10 years", 4),
        ("savings account with 1000 at 3% compounded daily for 5 years", 365),
        ("savings of 1000 at 3% compounded monthly for 5 years", 12),
        ("deposit 100 every month, compounded quarterly at 5% for 3 years", 4),
        ("invest 1000 at 7% compounded twice a year for 20 years", 2),
        # Spaces, hyphens and word order (review, 2026-10-31).
        ("savings of 1000 at 3% with semi annual compounding for 5 years", 2),
        ("savings of 1000 at 3% with half yearly compounding for 5 years", 2),
        ("savings of 1000 at 3% compounded semi annually for 5 years", 2),
        ("savings of 1000 at 3% compounded semiannually for 5 years", 2),
        ("savings of 1000 at 3% compounded per annum for 5 years", 1),
        ("savings of 1000 at 3% compounded per quarter for 5 years", 4),
        ("savings of 1000 at 3% compounded on a quarterly basis for 5 years", 4),
        ("savings of 1000 at 3% quarterly compounded for 5 years", 4),
        ("save 100 monthly compounded quarterly at 5% for 3 years", 4),
    ],
)
def test_the_compounding_said_is_the_requests(text: str, per_year: int) -> None:
    request = read_money_request(text)
    assert request is not None and request.settings == {"per_year": per_year}


@pytest.mark.parametrize(
    "text",
    [
        # None said is the usual monthly, which the block names as assumed.
        "if I save 200 a month at 4.5% for 10 years how much will I have",
        # A loan compounded monthly is what loans are; a card is charged by the month.
        "car loan 30000 at 6% compounded monthly for 5 years",
        "my credit card balance is 5000 at 22% APR, it compounds daily, I pay 200 a month",
    ],
)
def test_a_compounding_the_product_already_works_sets_nothing(text: str) -> None:
    request = read_money_request(text)
    assert request is not None and request.settings == {}


@pytest.mark.parametrize(
    "text",
    [
        # A frequency no count a year writes is never worked as monthly.
        "savings of 1000 at 3% compounded continuously for 5 years",
        "savings of 1000 at 3% compounded every 2 months for 5 years",
        "save 1000 at 3% compounded bi-monthly for 5 years",
        "save 1000 at 3% compounded bi monthly for 5 years",
        "savings of 1000 at 3% compounded fortnightly for 5 years",
        "savings of 1000 at 3% with continuous compounding for 5 years",
        "savings of 1000 at 3% compounded on a regular basis for 5 years",
        # Two frequencies compared: no one of them is the request's.
        "savings of 1000: is 5% compounded quarterly better than 4.9% compounded monthly?",
        # A loan is amortized monthly only when it compounds monthly.
        "car loan 30000 at 6% compounded quarterly for 5 years",
    ],
)
def test_a_compounding_the_product_cannot_work_is_left(text: str) -> None:
    assert read_money_request(text) is None


@pytest.mark.parametrize(
    ("text", "amount", "price", "down"),
    [
        (_MOGES, 200000, 250000, 50000),
        ("The car costs $30,000. She pays $5,000 and borrows the rest at 6% for 5 years", 25000, 30000, 5000),
        ("a house priced at 400k; we put in 80k and finance the remainder at 6.5% over 30 years", 320000, 400000, 80000),
        ("a 250k house, 50k of it as a deposit, mortgage at 7% for 30 years", 200000, 250000, 50000),
        # A sum said to be borrowed or owed is the loan as it stands (review, 2026-10-31).
        ("I have a 400k home and owe 250k at 6%", 250000, None, None),
        ("borrow 20k to buy a 30k car at 6%", 20000, None, None),
        ("borrow 20k and pay the rest in cash for a 30k car at 6%", 20000, None, None),
        ("I put down 10k and still owe 20k on my car loan at 6%", 20000, None, None),
        ("I owe $20,000 on my car loan at 7%. I put $5,000 down when I bought it", 20000, None, None),
        ("I borrowed $20,000 for a car at 7% after putting $5,000 down", 20000, None, None),
        # A deposit with a landlord is no money down; the loan named is the loan.
        ("I paid the landlord $2,000 as a deposit and now want a $15,000 car loan at 8%", 15000, None, None),
        # An income is never the loan.
        ("I make 80k a year, what's the payment on a 300k mortgage at 6%?", 300000, None, None),
        ("Mortgage payment on a $400k house at 6.5%, my salary is $90,000", 400000, None, None),
        ("my salary is 60k, buying a 25k car at 7% over 5 years, what's the payment", 25000, None, None),
        # The same sum again in another currency is no second sum.
        ("I want a EUR 20,000 car, that's about USD 21,600, car loan at 6%", 20000, None, None),
        # As before: one sum, or money down said outright.
        ("car loan 25000 with 5000 down 6.9% apr 60 months", 20000, 25000, 5000),
        ("mortgage on a 400k house, 50k down 6.5% for 30 years", 350000, 400000, 50000),
        ("personal loan of 20000 at 10% with a 500 upfront fee", 20000, None, None),
    ],
)  # fmt: skip
def test_the_loan_is_the_sum_borrowed(
    text: str, amount: float, price: float | None, down: float | None
) -> None:
    request = read_money_request(text)
    assert request is not None
    assert (request.values["amount"], request.price, request.down) == (amount, price, down)


@pytest.mark.parametrize(
    "text",
    [
        # A price and another sum, and nothing says which is borrowed: no loan is assumed.
        "The house costs 250,000 and I have 50,000 saved, mortgage at 7% for 30 years",
        "a car worth 30,000, I have 8,000, car loan at 6% for 5 years, monthly payment?",
        # Two prices compared are no price less a deposit (review, 2026-10-31).
        "What's the difference in payment between a $300,000 house and a $350,000 house on a mortgage at 6%?",
        "What's the difference between a $30,000 car vs a $40,000 car, financing at 6%?",
        "$30,000 car vs a $40,000 car, financing at 6%, which payment is lower?",
        # "The rest" with no sum said to be paid toward the price.
        "a $300,000 house or a $350,000 house, and I'd borrow the rest at 6%",
    ],
)  # fmt: skip
def test_a_loan_the_message_never_names_is_not_assumed(text: str) -> None:
    request = read_money_request(text)
    assert request is None or "amount" not in request.values


@pytest.mark.parametrize(
    ("text", "name", "value"),
    [
        ("car loan of Birr 300000 at 12% for 5 years", "amount", 300000),
        # An exchange rate or a note is no sum (review, 2026-10-31).
        ("Exchange rate is USD 1 = ETB 57. Savings account at 7% with ETB 10,000 for 3 years", "start", 10000),
        ("1 USD = 57 ETB. Savings account at 7% with 10,000 birr for 3 years", "start", 10000),
        ("at 57 birr to the dollar, savings account at 7% with 10,000 birr for 3 years", "start", 10000),
        ("USD 1 = EUR 0.92, my balance is EUR 3,000 at 19% APR paying EUR 150 a month on my credit card", "balance", 3000),
    ],
)  # fmt: skip
def test_a_currency_before_its_sum_is_money_but_a_rate_between_currencies_is_not(
    text: str, name: str, value: float
) -> None:
    request = read_money_request(text)
    assert request is not None and request.values[name] == value


def test_a_note_or_a_coin_is_no_sum() -> None:
    assert read_money_request("I have some Birr 500 notes, any tips on mortgage rates?") is None
