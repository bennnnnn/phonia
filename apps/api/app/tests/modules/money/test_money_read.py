"""Which messages are money requests, and the numbers read out of them."""

from __future__ import annotations

import pytest

from app.modules.money.read import read_money_request


@pytest.mark.parametrize(
    ("text", "product", "values", "currency"),
    [
        (
            "what is my mortgage for 300k dollars house if mr rate is 1 percent",
            "mortgage",
            {"amount": 300000, "rate": 1},
            "USD",
        ),
        ("car loan 30000 at 6% for 5 years monthly payment", "car", {"amount": 30000, "rate": 6, "months": 60}, ""),
        (
            "what would my car payment be on a $32,000 car at 7.5% APR for 72 months",
            "car",
            {"amount": 32000, "rate": 7.5, "months": 72},
            "USD",
        ),
        (
            "a 400k house with 80k down at 6.5% for 15 years, what is the monthly payment",
            "mortgage",
            {"amount": 320000, "rate": 6.5, "years": 15},
            "",
        ),
        (
            "I owe 5000 on my credit card at 22% apr and pay 200 a month, how long to pay off",
            "card",
            {"balance": 5000, "apr": 22, "payment": 200},
            "",
        ),
        (
            "if I save 200 a month at 4.5% for 10 years how much will I have",
            "savings",
            {"deposit": 200, "rate": 4.5, "years": 10},
            "",
        ),
        (
            "I have $10k in savings at 4% and add $500 a month for 20 years",
            "savings",
            {"start": 10000, "deposit": 500, "rate": 4, "years": 20},
            "USD",
        ),
        ("student loan of 40,000 at 5.5%", "student", {"amount": 40000, "rate": 5.5}, ""),
        (
            "borrow 25000 for a personal loan at 11% over 3 years",
            "personal",
            {"amount": 25000, "rate": 11, "months": 36},
            "",
        ),
        (
            "mortgage of 2 million birr at 18% for 20 years",
            "mortgage",
            {"amount": 2_000_000, "rate": 18, "years": 20},
            "ETB",
        ),
        ("monthly payment on a 250000 mortgage", "mortgage", {"amount": 250000}, ""),
    ],
)  # fmt: skip
def test_read_money_request_reads_the_numbers(
    text: str, product: str, values: dict[str, float], currency: str
) -> None:
    request = read_money_request(text)
    assert request is not None
    assert request.product.key == product
    assert request.values == values
    assert request.currency == currency
    assert not request.rates_only


@pytest.mark.parametrize(
    ("text", "product"),
    [
        ("what are mortgage rates right now", "mortgage"),
        ("what's the average credit card APR these days?", "card"),
        ("current car loan rates", "car"),
    ],
)
def test_read_money_request_knows_a_rates_question(text: str, product: str) -> None:
    request = read_money_request(text)
    assert request is not None and request.rates_only and request.product.key == product


@pytest.mark.parametrize(
    "text",
    [
        "I'm interested in cars",
        "rate my essay out of 10",
        "who is the principal of my school",
        "credit card design ideas",
        "my card was declined at the store",
        "pay attention to the details",
        "the interest of the story fades in act 3",
        "savings on groceries tips",
        "how much should I save for a house",
        "mortgage rates in 2026",
        "compound interest on 1000 at 5% for 3 years",
        "simple interest on $1200 at 5% per year for 4 years",
        "$5000 invested at 4% interest compounded annually for 3 years",
        "my house is 20 years old",
        "I drove my car 300 miles",
        "",
    ],
)
def test_read_money_request_leaves_other_messages(text: str) -> None:
    assert read_money_request(text) is None


@pytest.mark.parametrize(
    ("text", "variant"),
    [
        # Live (2026-10-25): this got the new-car average.
        (
            "i'm thinking of buying a used car for 14000, i can put 3000 down. what would my "
            "monthly payment be over 5 years?",
            "used",
        ),
        ("we're buying a used car, 16k at 8.5% for 60 months, payment?", "used"),
        ("getting a used car for $9,800 at 13% for 36 months what's monthly", "used"),
        ("thinking of buying a certified pre-owned car, 22k at 6.9% for 60 months", "used"),
        ("purchase a used truck 28k at 8% 72 months car loan", "used"),
        ("I want to buy a pre-owned car for 18000 at 9% for 60 months", "used"),
        ("I need a car loan, a loan for a used car of 15000 at 9% for 5 years", "used"),
        # Missing a used car is the safe direction: no buying verb, no kind.
        ("a used car for 17000 at 7.9% for 60 months, monthly payment?", ""),
        ("used car loan 12000 at 11% for 4 years", ""),
        ("what's the payment on a used-car loan of 15000 at 10% for 5 years", ""),
        ("used car payment on 15k at 9%", ""),
        # The alternative, another car, or a verb (reviews, 2026-10-25).
        ("should I take a car loan of 30000 for 60 months or buy a used car for 12000 cash? what's the loan payment", ""),
        ("car loan 33000 for 60 months vs buying a used car for 15000, what's the payment", ""),
        ("new car loan of 28k for 72 months instead of buying a used car for 14k, monthly payment?", ""),
        ("I just sold a used car for 8000; car loan 30k over 60 months, monthly payment?", ""),
        ("I'm selling a used car for 9000 and need a car loan of 25000 for 60 months, what's the monthly", ""),
        ("car loan of 20000 for 48 months, not a used car loan, what's the payment", ""),
        ("my old used car loan is paid off, now I need a car loan of 31k for 60 months, payment?", ""),
        ("my wife's used car loan is paid off, now we need a car loan of 30k at 6% for 60 months", ""),
        ("car loan 18000 at 7% to replace my old used car, payment over 60 months", ""),
        ("trading in my used car, new car loan 30000 at 6%", ""),
        ("I used a calculator and got 400 a month on a car loan of 20000 at 6%", ""),
        ("car loan 25000 at 6%, what rate is used", ""),
        ("new car loan 30000 at 6% for 5 years", ""),
        # A product with no kinds priced apart.
        ("used furniture loan of 3000 at 9%", ""),
    ],
)  # fmt: skip
def test_read_money_request_reads_the_kind(text: str, variant: str) -> None:
    request = read_money_request(text)
    assert request is not None and request.variant == variant


def test_a_rates_question_keeps_the_kind() -> None:
    request = read_money_request("current car loan rates for buying a used car")
    assert request is not None and request.rates_only and request.variant == "used"


@pytest.mark.parametrize(
    ("text", "values"),
    [
        # The reviewers' first asks the parent reader reads right, and this branch with it.
        ("car loan 25000 with 5000 down 6.9% apr 60 months", {"amount": 20000, "rate": 6.9, "months": 60}),
        ("mortgage on a 400k house, 50k down 6.5% for 30 years", {"amount": 350000, "rate": 6.5, "years": 30}),
        ("mortgage 500k 100k down payment 6.25% 30 year", {"amount": 400000, "rate": 6.25, "years": 30}),
        ("car loan 20000, I can put 2000 down 8% 4 years", {"amount": 18000, "rate": 8, "months": 48}),
        ("300k house with 60k down 6% 30 yr", {"amount": 240000, "rate": 6, "years": 30}),
        ("car loan 25000 at 7% down payment of 5000 for 60 months", {"amount": 20000, "rate": 7, "months": 60}),
        ("mortgage 400k at 6.5% down payment 80k 30 years", {"amount": 320000, "rate": 6.5, "years": 30}),
        ("personal loan of 20000 at 10% with a 500 upfront fee", {"amount": 20000, "rate": 10}),
        ("my mortgage is 200k at 6%, rates went down 1 point, should I refinance", {"amount": 200000, "rate": 6}),
        ("car loan 20000 at 7% for 5 years, I'm 2 down on payments", {"amount": 20000, "rate": 7, "months": 60}),
        ("student loan 30000 at 5% repaid after 10 years", {"amount": 30000, "rate": 5, "years": 10}),
        ("a 300k mortgage at 6% paid off after 15 years", {"amount": 300000, "rate": 6, "years": 15}),
        ("car loan 20000 at 6%, paid off after 3 years", {"amount": 20000, "rate": 6, "months": 36}),
        ("a car loan of 20000 at 6% that will last 5 years", {"amount": 20000, "rate": 6, "months": 60}),
        ("a 2000 car with a loan at 10% for 12 months", {"amount": 2000, "rate": 10, "years": 1}),
        ("financing a 2000 car at 12% for 12 months with 500 down", {"amount": 1500, "rate": 12, "years": 1}),
        # A percent down is a share of the price, never the rate (review, 2026-10-25).
        ("400k house with 20% down at 6%", {"amount": 320000, "rate": 6}),
        ("mortgage on a 400k house, 20% down, 6%", {"amount": 320000, "rate": 6}),
        ("400k house, down payment of 20%, at 6%", {"amount": 320000, "rate": 6}),
        ("a 400k house at 6% with 20 percent down", {"amount": 320000, "rate": 6}),
        ("400k house putting down 20% at 6%", {"amount": 320000, "rate": 6}),
        # Round 2: a percent or a term after "down" is not a sum down.
        ("400k house 20% down 6% rate", {"amount": 320000, "rate": 6}),
        ("400k house 20% down 6.5% interest", {"amount": 320000, "rate": 6.5}),
        ("400k house 10% down 30 years at 6%", {"amount": 360000, "rate": 6, "years": 30}),
        ("400k house 20% down 15 years, 6%", {"amount": 320000, "rate": 6, "years": 15}),
        ("400k house 20% down 30 year fixed 6%", {"amount": 320000, "rate": 6, "years": 30}),
        ("400k house, down payment 20% 6% rate", {"amount": 320000, "rate": 6}),
        # A percent right after "down payment" is the share; the other is the rate.
        ("400k house, 6% down payment 20%", {"amount": 320000, "rate": 6}),
    ],
)  # fmt: skip
def test_read_money_request_reads_what_a_number_is(text: str, values: dict[str, float]) -> None:
    request = read_money_request(text)
    assert request is not None and request.values == values


@pytest.mark.parametrize(
    ("text", "price", "down"),
    [
        ("400k house with 20% down at 6%", 400000, 80000),
        ("car loan 25000 with 5000 down 6.9% apr 60 months", 25000, 5000),
        ("400k house, 6% down payment 20%", 400000, 80000),
        # A sum with no money down may be a loan, a balance or an equity line: no price.
        ("mortgage at 6% on a 400k house", None, None),
        ("I have a 400k home and owe 250k at 6%", None, None),
        ("a 400k home equity loan at 8%", None, None),
        ("a 400k home, refinancing at 6%", None, None),
        ("20k car repairs at 9%", None, None),
        ("a 20k car loan at 6%", None, None),
        ("car loan of 20k at 6%", None, None),
        ("I owe 15k on my car loan at 6%", None, None),
        ("refinance my 250k mortgage at 6%", None, None),
        ("mortgage of 320k at 6%", None, None),
    ],
)
def test_a_price_is_a_sum_said_to_be_what_the_thing_costs(
    text: str, price: float | None, down: float | None
) -> None:
    request = read_money_request(text)
    assert request is not None and (request.price, request.down) == (price, down)


# 2026-10-30, a grade 7 physics book: "6m/s2" was read as $6 million and "the rate of"
# as a loan's rate, and a car-loan calculator sat under F = 9000 N.
@pytest.mark.parametrize(
    "text",
    [
        "4) How much external force is required to accelerate a 1500 kg car at the rate of 6m/s2\n?",
        "A 2000 kg car moving at 20 m/s brakes at a rate of 5 m/s2. How far does it go?",
        "A car went 500m at a constant rate. What was its speed?",
        "A 1200 kg car accelerates at 3 m/s^2. What is the net force on the car?",
    ],
)
def test_a_physics_quantity_is_no_loan(text: str) -> None:
    assert read_money_request(text) is None


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("a 1.2m house with 20% down at 6.5%", 960000.0),
        ("I bought a 1500 kg car for $20k at 6% over 60 months", 20000.0),
        ("car loan of 30k at 6% for 5 years", 30000.0),
    ],
)
def test_money_beside_a_measurement_is_still_read(text: str, amount: float) -> None:
    request = read_money_request(text)
    assert request is not None and request.values["amount"] == amount


# Review (2026-10-30): a sum written apart from its "k" or "m", an "m" on the number,
# and a loan that mentions a distance are all still money.
@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("borrow 20 k for a car at 7%", 20000.0),
        ("$1.2 m mortgage at 6.5% for 30 years", 1200000.0),
        ("car loan 1.5 m birr at 12%", 1500000.0),
        ("borrow 2 m for a house over 30 years", 2000000.0),
        ("monthly payment on a 1.2m mortgage over 30 years", 1200000.0),
        ("I drive 15 km to work, what are the payments on a 30k car loan over 5 years?", 30000.0),
        ("I need a 50k loan, 10 km from the bank, 5 years", 50000.0),
    ],
)
def test_a_sum_in_any_spelling_is_still_money(text: str, amount: float) -> None:
    request = read_money_request(text)
    assert request is not None and request.values["amount"] == amount


@pytest.mark.parametrize(
    "text",
    [
        "A car travels 120 miles at a rate of 40 miles per hour. How long?",
        "A 3000 lb car accelerates at the rate of 10 ft/s^2. What force?",
        "A car went 500m at a constant rate. What was its speed?",
    ],
)
def test_a_rate_of_a_quantity_is_no_interest_rate(text: str) -> None:
    assert read_money_request(text) is None
