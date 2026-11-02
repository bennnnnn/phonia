"""A turn about the chat's earlier loan: its figures for the model, the reply left as written."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.money.block import MONEY_HEADER, MONEY_STANDING_HEADER
from app.modules.money.follow_up import standing_request
from app.modules.money.note import reading_note
from app.modules.money.purchase import purchase_request
from app.modules.money.service import finish_money_reply, prepare_standing_turn
from app.modules.money.solve import work
from app.modules.money.standing import about_the_loan

# The live chat (2026-10-25): a 400k house, 60k down at 6%, then "How", "Yes", "Yes".
_HOUSE = [("House buying for 400k",), ("60k at 6 percent",), ("How",), ("Yes",)]
_OFFER = "If you'd like, I can also show how a 15-year term changes the monthly payment."
_REPLY = "Over 15 years the payment would be $2,921.00 a month."


def test_the_house_still_stands_after_lines_about_something_else() -> None:
    request = standing_request(_HOUSE)
    assert request is not None
    worked = work(request, None)
    assert worked is not None

    assert request.product.key == "mortgage"
    assert worked.values["amount"] == 340_000
    assert round(worked.outputs["payment"] or 0, 2) == 2038.47


@pytest.mark.parametrize(
    ("text", "last_reply"),
    [
        ("Yes", _OFFER),
        ("How", "Want me to break down the monthly payment for you?"),
        ("Yes", "Your payment is $2,038.47. Would you like a 15-year comparison?"),
        ("what if i only do 3 years instead", ""),
        ("what would a 15-year loan cost?", ""),
        ("which is cheaper overall, 15 or 30 years?", ""),
        ("show me the math", ""),
        ("how did you get that?", ""),
        ("what about 20 years?", ""),
        ("what would the payment be over 15 years?", ""),
        ("is the interest rate fixed?", ""),
        ("can I pay the mortgage off early?", ""),
    ],
)
def test_a_message_about_the_loan(text: str, last_reply: str) -> None:
    assert about_the_loan(text, last_reply)


@pytest.mark.parametrize(
    ("text", "last_reply"),
    [
        ("thanks", _OFFER),
        ("how do I bake bread?", _OFFER),
        ("tell me a joke", _OFFER),
        # Years, months, costs and totals with no loan in them (review, 2026-10-26).
        ("how many years did WW2 last?", _OFFER),
        ("how many months until christmas?", _OFFER),
        ("what's the cost of a trip to Paris?", _OFFER),
        ("what's the total for 3 coffees at $4?", _OFFER),
        # A "yes" to an offer about something else.
        ("Yes", "Mix flour, water and yeast. Want a full recipe?"),
        ("Yes", "Want me to set a reminder for Friday at 9?"),
        ("Yes", "Should I draft an email to your landlord?"),
        ("Yes", "Your payment is $2,038.47. Anything else?"),
        # An offer that only mentions the payment or the loan (review, 2026-10-26).
        ("Yes", "Your payment is $2,038.47. Want me to set a reminder for the first payment?"),
        ("Yes", "Shall I draft an email to your realtor about the loan?"),
        ("Yes", "Want me to remind you when the payment is due?"),
        # Terms of service and an age are no loan terms.
        ("what are the terms of service?", ""),
        ("I'm 30 years old, what's a good workout?", ""),
    ],
)
def test_a_message_about_something_else(text: str, last_reply: str) -> None:
    assert not about_the_loan(text, last_reply)


async def test_a_yes_about_the_loan_gets_its_figures_and_no_card() -> None:
    turn = await prepare_standing_turn(
        "Yes", Settings(), None, user=None, location=None, earlier=_HOUSE, last_reply=_OFFER
    )

    assert turn is not None and turn.standing
    assert turn.block.startswith(MONEY_STANDING_HEADER)
    assert MONEY_HEADER + ":" not in turn.block
    assert "With term in years 15: monthly payment 2,869.11" in turn.block
    assert "monthly payment 2,038.47" in turn.block
    # The reply is left exactly as written: no card, no note, no sum changed.
    assert await finish_money_reply(turn, _REPLY, Settings()) == _REPLY


@pytest.mark.parametrize(
    "earlier",
    [
        [],
        [("How do I start running?",), ("Yes",)],
        [("what are mortgage rates now?",)],
    ],
)
async def test_no_loan_in_the_chat_no_block(earlier: list[tuple[str, ...]]) -> None:
    turn = await prepare_standing_turn(
        "Yes", Settings(), None, user=None, location=None, earlier=earlier, last_reply=_OFFER
    )

    assert turn is None


async def test_a_message_about_another_product_gets_no_block() -> None:
    turn = await prepare_standing_turn(
        "what's the interest rate on a savings account?",
        Settings(),
        None,
        user=None,
        location=None,
        earlier=_HOUSE,
        last_reply="",
    )

    assert turn is None


async def test_money_off_no_block() -> None:
    turn = await prepare_standing_turn(
        "Yes",
        Settings(money_enabled=False),
        None,
        user=None,
        location=None,
        earlier=_HOUSE,
        last_reply=_OFFER,
    )

    assert turn is None


_FULL = "**Read as:**"
_SHORT = "If 60,000 is the loan, not the down payment, say so."


@pytest.mark.parametrize(
    ("reply", "note"),
    [
        ("I treated your $60,000 as the down payment on the $400,000 price.", _SHORT),
        ("Here is the breakdown for a $60k down payment on a $400k home.", _SHORT),
        ("With a down payment of $60,000 on the $400,000 house, you borrow $340,000.", _SHORT),
        # The other reading, no reading, or another price: the whole note.
        ("A $60,000 loan instead of a down payment on the $400,000 house.", _FULL),
        ("Your payment is $2,038.47.", _FULL),
        ("Put $60,000 down on any $500,000 home.", _FULL),
    ],
)
def test_the_note_is_short_only_when_the_reply_says_the_same_reading(reply: str, note: str) -> None:
    request = purchase_request("60k at 6 percent", ("House buying for 400k",))
    assert request is not None

    assert (reading_note(request, reply) or "").startswith(note)
