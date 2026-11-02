"""The block the model reads: numbers to copy, what was assumed, what the app adds."""

from __future__ import annotations

from app.modules.money.block import (
    MONEY_FOLLOW_UP,
    MONEY_HEADER,
    MONEY_RATE_MISSING,
    MONEY_RATES_FOUND,
    MONEY_RATES_MISSING,
    MONEY_REPLY_RULES,
    money_block,
)
from app.modules.money.catalog import product
from app.modules.money.follow_up import follow_up_request
from app.modules.money.read import MoneyRequest, read_money_request
from app.modules.money.solve import work
from app.tests.modules.money.money_support import average


def test_the_block_gives_the_worked_numbers_and_the_assumption() -> None:
    request = MoneyRequest(product("mortgage"), {"amount": 300000, "rate": 1}, "USD")
    block = money_block(request, work(request, None), None)
    assert "Currency: USD." in block
    assert "amount 300,000; yearly rate 1%; term in years 30 (assumed" in block
    assert "monthly payment 964.92; total interest 47,370.68; total paid 347,370.68" in block
    assert MONEY_REPLY_RULES in block


def test_the_block_asks_for_a_rate_when_there_is_none() -> None:
    request = MoneyRequest(product("mortgage"), {"amount": 300000})
    assert MONEY_RATE_MISSING in money_block(request, None, None)


def test_a_payment_that_never_clears_the_card_is_said_plainly() -> None:
    request = MoneyRequest(product("card"), {"balance": 5000, "apr": 24, "payment": 100})
    block = money_block(request, work(request, None), None)
    assert "months to pay off: never" in block


def test_a_rates_question_gets_the_checked_average_or_none() -> None:
    request = MoneyRequest(product("mortgage"), {}, rates_only=True)
    found = money_block(request, None, average())
    assert "6.27% as of Oct 16, 2026" in found and MONEY_RATES_FOUND in found
    assert MONEY_RATES_MISSING in money_block(request, None, None)


def test_the_block_names_the_kind_of_product() -> None:
    request = read_money_request("buying a used car, car loan of 11000 at 7% for 60 months")
    assert request is not None
    assert money_block(request, work(request, None), None).startswith(f"{MONEY_HEADER}: used car.")


def test_a_follow_up_is_told_the_numbers_already_include_its_change() -> None:
    """Live (2026-10-25): the model redid "3 years instead" itself and was off by dollars."""
    earlier = ["car loan 14000 with 3000 down at 7.16% for 5 years, what's the payment"]
    request = follow_up_request("hmm what if i only do 3 years instead", earlier)
    assert request is not None
    block = money_block(request, work(request, None), None)
    lead = MONEY_FOLLOW_UP.split("{changes}")[0]
    assert f"{lead}term in months 36." in block
    assert "monthly payment 340.45; total interest 1,256.32" in block
    both = follow_up_request("what about 4 years at 6%?", earlier)
    assert both is not None
    assert f"{lead}yearly rate 6%; term in months 48." in money_block(both, work(both, None), None)
    first = read_money_request(earlier[0])
    assert first is not None and lead not in money_block(first, work(first, None), None)


def test_the_block_says_how_often_savings_compound() -> None:
    """2026-10-31: "compounded quarterly" was worked monthly; the block now says which."""
    said = read_money_request(
        "Birr 3,000 in a saving account at 6% per year, compounded quarterly, for seven years"
    )
    assert said is not None
    block = money_block(said, work(said, None), None)
    assert "term in years 7; interest compounded quarterly." in block
    assert "final balance 4,551.67" in block and "total interest 1,551.67" in block
    usual = MoneyRequest(product("savings"), {"start": 1000, "rate": 4, "years": 5})
    assert "interest compounded monthly (assumed: the user did not say)" in money_block(
        usual, work(usual, None), None
    )
