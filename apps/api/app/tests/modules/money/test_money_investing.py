"""Investing is not a savings account (2026-10-29).

"If I invest $200 a month at 7% for 10 years how much will I have?" was worked as savings,
and its note said "7% is not a realistic savings account interest rate (APY)" beside the
0.37% average: 7% is a usual long-run market assumption, and no bank average judges it.
"""

from __future__ import annotations

import json

import pytest

from app.modules.money.fence import calculator_fence
from app.modules.money.follow_up import follow_up_request
from app.modules.money.read import read_money_request
from app.modules.money.solve import work


@pytest.mark.parametrize(
    "text",
    [
        "if I invest $200 a month at 7% for 10 years how much will I have?",
        "investing $500 a month at 8% for 20 years, what do I end up with?",
        "my retirement: $300 a month at 6% for 30 years",
    ],
)
def test_money_put_into_a_market_is_investing_with_no_bank_average(text: str) -> None:
    request = read_money_request(text)
    assert request is not None
    assert request.product.key == "investing"
    # Nothing looked up, so no "not a realistic … APY" note and no average on the slider.
    assert request.product.rate_lookup(request.variant) is None
    worked = work(request, None)
    assert worked is not None
    card = calculator_fence(worked, None, "USD")
    assert card is not None
    body = json.loads(card.split("\n", 1)[1].rsplit("```", 1)[0])
    assert body["title_key"] == "money.title.investing"
    assert all("marker" not in control for control in body["controls"])


def test_the_same_deposits_grow_the_same_as_savings() -> None:
    invested = read_money_request("if I invest $200 a month at 7% for 10 years, how much?")
    saved = read_money_request("if I save $200 a month at 7% for 10 years, how much?")
    assert invested is not None and saved is not None
    assert saved.product.key == "savings"
    worked_invested, worked_saved = work(invested, None), work(saved, None)
    assert worked_invested is not None and worked_saved is not None
    assert worked_invested.outputs == worked_saved.outputs
    assert round(worked_invested.outputs["balance"] or 0, 2) == 34616.96


def test_a_savings_account_keeps_its_average() -> None:
    request = read_money_request("I save $200 a month at 4% for 10 years, how much?")
    assert request is not None
    assert request.product.rate_lookup(request.variant) is not None


def test_a_savings_account_for_retirement_is_a_savings_account() -> None:
    text = "I put $5000 in a high yield savings account for my retirement at 4.5% for 10 years, how much?"
    request = read_money_request(text)
    assert request is not None and request.product.key == "savings"


@pytest.mark.parametrize(
    ("earlier", "line", "product"),
    [
        (
            "If I save $200 a month at 4% for 10 years how much will I have?",
            "what if I invest for 20 years",
            "savings",
        ),
        (
            "if I invest $200 a month at 7% for 10 years how much will I have?",
            "what if I save for 20 years",
            "investing",
        ),
    ],
)
def test_moving_between_saving_and_investing_keeps_the_worked_request(
    earlier: str, line: str, product: str
) -> None:
    request = follow_up_request(line, [earlier])
    assert request is not None
    assert request.product.key == product
    assert request.values["years"] == 20
