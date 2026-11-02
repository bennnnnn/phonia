"""A loan reply whose stated payment is not its card's gets the card's figures in a line."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.money.agreement import CardFigures, card_figures
from app.modules.money.block import money_block
from app.modules.money.purchase import purchase_request
from app.modules.money.read import read_money_request
from app.modules.money.service import MoneyTurn, finish_money_reply
from app.modules.money.solve import work

# The live reply (2026-10-26, free model): the card said 340,000 at $2,038.47.
_WRONG = (
    "Here is the breakdown for **$60k** at **6%** over a standard **30-year** term:\n\n"
    "*   **Monthly Payment:** $359.82\n*   **Total Interest Paid:** $71,535.54\n"
    "*   **Total Amount Paid:** $131,535.54"
)
_LINE = "The card's figures: **$2,038.47** a month on a $340,000 loan at 6% over 30 years."
_TOP = "**The card's figures:** $2,038.47 a month on a $340,000 loan at 6% over 30 years."
# The live reply on c7a37ce56 (2026-10-26, free model), verbatim.
_ROUGHLY = (
    "At **6%** interest over a standard **30-year** term, the monthly payment for $60k is "
    "roughly **$360**.\n\n*   **Monthly Payment**: ~$360\n*   **Total Interest**: ~$69,600"
)


def _house():
    request = purchase_request("60k at 6 percent", ("House buying for 400k",))
    assert request is not None
    request = replace(request, currency="USD")
    worked = work(request, None)
    assert worked is not None
    return request, worked


@pytest.mark.parametrize("reply", [_WRONG, _ROUGHLY])
def test_a_reply_that_worked_another_loan_gets_the_cards_figures_on_top(reply: str) -> None:
    request, worked = _house()

    assert card_figures(reply, request, worked) == CardFigures(_TOP, on_top=True)


@pytest.mark.parametrize(
    "reply",
    [
        "The principal is $340,000. Your monthly payment is $2,037.97.",
        "On the $340k loan, that works out to $2,100.00 a month.",
        "Borrowing 340,000, you'd pay $2,100/month.",
    ],
)
def test_a_payment_that_is_not_the_cards_gets_the_cards_figures(reply: str) -> None:
    request, worked = _house()

    assert card_figures(reply, request, worked) == CardFigures(_LINE, on_top=False)


@pytest.mark.parametrize(
    "reply",
    [
        "Your monthly payment is **$2,038.47**.",
        "That comes to $2,038 a month.",
        # Taxes, PMI, other scenarios and the full price (review, 2026-10-26).
        "Your payment is $2,038.47. With taxes and insurance (about $400 a month), plan on "
        "roughly $2,438.",
        "Add PMI only if you put less than 20% down; expect about $150 a month extra.",
        "For comparison, with 20% down ($80,000) the payment would be $1,918.56 a month.",
        "Without a down payment, borrowing the full $400,000 would cost $2,398.20 a month.",
        "With $80,000 down instead, the monthly payment is $1,918.56.",
        # Rounding and ranges.
        "That's about $2,040 a month.",
        "Roughly $2,000 a month.",
        "Expect $2,000–$2,100 a month depending on taxes.",
        "Your payment is $2,038.47 (≈ $2,038.50).",
        "Your payment is $2,038.47 — about $24,462 a year.",
        # The worked formula, ratios and other numbers.
        "Monthly rate: r = 0.06/12 = 0.005. Payment $2,038.47.",
        "$(1.005)^{360} \\approx 6.02$, so the payment is $2,038.47.",
        "Each $1,000 borrowed costs about $6 a month.",
        "That's about 1.5 times your rent. Payment: $2,038.47.",
        "On a 1,800 sq ft home, the payment is $2,038.47.",
        "```python\npayment = 2921.00\n```\nThe payment is $2,038.47.",
        "| Term | Payment |\n|---|---|\n| 30-year | $2,038.47 |\n| 15-year | $2,869.11 |",
        "Over 15 years it would be $2,869.11 a month instead.",
        "If you split it, each of you pays $1,019.24 a month.",
        # No labelled payment at all.
        "Here are your numbers. The card below lets you try other terms.",
        # A comparison with a side note about another loan.
        "Your monthly payment is $2,038.47. For comparison, a $60k loan would be $359.82 a month.",
        "Lenders like housing costs under 28% of gross income, so aim for income of at least "
        "$7,280 a month.",
        "In the first year, about $20,300 goes to interest and $4,160 to principal.",
    ],
)
def test_other_replies_get_nothing(reply: str) -> None:
    request, worked = _house()

    assert card_figures(reply, request, worked) is None


@pytest.mark.parametrize(
    ("ask", "reply"),
    [
        (
            "Can I afford a 300k mortgage at 6.5% on a 90k salary?",
            "Your monthly payment is $1,896.20. Your gross monthly income is $7,500, and 28% "
            "of that is $2,100, so yes, it fits.",
        ),
        (
            "20000 car loan at 7% for 60 months, plus insurance of 150 a month",
            "Payment $396.02, plus $150 insurance = $546.02 a month.",
        ),
        ("car loan 17000 at 6% for 60 months", "You'd borrow $17,000 at **$328.66** a month."),
    ],
)
def test_a_reply_that_answers_its_own_request_gets_nothing(ask: str, reply: str) -> None:
    request = read_money_request(ask)
    assert request is not None
    worked = work(request, None)
    assert worked is not None

    assert card_figures(reply, request, worked) is None


def test_card_and_savings_turns_get_nothing() -> None:
    for ask in (
        "credit card balance 5000 at 22% apr paying 200 a month",
        "save 500 a month at 5% for 20 years",
    ):
        request = read_money_request(ask)
        assert request is not None
        worked = work(request, None)
        assert worked is not None
        assert card_figures("You'll pay $999.99 a month.", request, worked) is None


def _turn(*, multi: bool = False) -> MoneyTurn:
    request, worked = _house()
    return MoneyTurn(request, worked, money_block(request, worked, None), None, None, multi=multi)


async def test_the_line_opens_a_misread_reply_and_the_reply_is_kept() -> None:
    settings = Settings()

    english = await finish_money_reply(_turn(), _WRONG, settings)
    other = await finish_money_reply(_turn(), _WRONG, settings, english=False)
    multi = await finish_money_reply(_turn(multi=True), _WRONG, settings)

    assert english.startswith(_TOP + "\n\n" + _WRONG + "\n\n**Read as:**")
    assert "```calculator" in english
    assert _TOP not in other and _TOP not in multi
    assert other.startswith(_WRONG) and multi.startswith(_WRONG)


async def test_the_line_follows_a_comparing_reply() -> None:
    reply = "On the $340k loan, your monthly payment is $2,100.00."

    finished = await finish_money_reply(_turn(), reply, Settings())

    assert finished.startswith(reply + "\n\n" + _LINE + "\n\n")


@pytest.mark.parametrize(
    ("reply", "corrected"),
    [
        # "3,5%" in the reply is the asker's 3.5%, not a 5% loan of its own (PR review).
        ("At 3,5% over 25 years, the monthly payment is €950.00.", True),
        ("At 3,5% over 25 years, the monthly payment is €901.12.", False),
        ("At 4,5% over 25 years, the monthly payment would be €1,000.50.", False),
        # Two rates after a separator are both read: another scenario.
        ("At 3,5%,4% over 25 years, the monthly payment would be €1,000.50.", False),
    ],
)
def test_a_decimal_comma_rate_in_the_reply_is_the_cards(reply: str, corrected: bool) -> None:
    request = read_money_request(
        "Sara takes out a mortgage of €180.000 at 3,5% for 25 years. What is her monthly payment?"
    )
    assert request is not None
    worked = work(request, None)
    assert worked is not None
    assert (card_figures(reply, request, worked) is not None) is corrected
