"""The notes under a money reply: today's average beside the user's rate, and how a bare
amount beside a price was read.

The server writes it, so the average, its date and its source are exactly what the
checked lookup found (``rates.py``). A rate further than ``money_unrealistic_ratio``
from the average either way "is not realistic"; any other gets the average "for
reference"; a rate that is the average (the user gave none) says so. No average, no note.
An average standing in for the kind asked (the new-car one for a used car) says so, and
judges no rate unrealistic: a used-car rate far above the new-car average is ordinary.
"""

from __future__ import annotations

import re

from app.modules.money.numbers import day_text, money_text, percent_text
from app.modules.money.rates import MarketRate
from app.modules.money.read import MoneyRequest
from app.modules.money.solve import Worked, rate_name


def reading_note(request: MoneyRequest, reply: str = "") -> str | None:
    """How a bare amount beside a price was read, so a misread shows (``purchase``).

    A reply that already says the reading ("treated your $60,000 as the down payment on
    the $400,000 price", live 2026-10-25) gets only the line that puts a misread right."""
    amount, price = request.values.get("amount"), request.price
    if amount is None or price is None:
        return None
    if request.guessed == "down" and request.down is not None:
        down = money_text(request.down)
        if states_reading(reply, request.down, price, as_down=True):
            return f"If {down} is the loan, not the down payment, say so."
        return (
            f"**Read as:** {down} is the down payment on the {money_text(price)} price, so the "
            f"loan is {money_text(amount)}. If {down} is the loan, say so."
        )
    if request.guessed == "loan":
        if states_reading(reply, amount, price, as_down=False):
            return f"If {money_text(amount)} is the down payment, not the loan, say so."
        return (
            f"**Read as:** {money_text(amount)} is the loan on the {money_text(price)} price. "
            "If it is the down payment, say so."
        )
    return None


# The guessed sum read as a down payment, or as the loan, right beside it: "$60,000 as the
# down payment", "a down payment of $60,000", "$60k down"; "a $60,000 loan", "borrow $60,000".
_AS_DOWN_AFTER = re.compile(
    r"^\W{0,3}(?:(?:as|is|for)\s+(?:the|your|a)\s+|in\s+)?down(?:[\s-]?payment)?\b",
    re.IGNORECASE,
)
_AS_DOWN_BEFORE = re.compile(r"\bdown[\s-]?payment\s+(?:of\s+|is\s+)?\W{0,3}$", re.IGNORECASE)
_AS_LOAN_AFTER = re.compile(
    r"^\W{0,3}(?:(?:as|is)\s+(?:the|your|a)\s+)?(?:loan|mortgage)\b", re.IGNORECASE
)
_AS_LOAN_BEFORE = re.compile(
    r"\b(?:loan(?:\s+amount)?|borrow(?:ing)?|financ\w*)\s+(?:of\s+|is\s+)?\W{0,3}$", re.IGNORECASE
)
_SUM = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s?([km]\b)?", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_SCALE = {"k": 1_000, "m": 1_000_000}
_NEARBY = 40


def states_reading(reply: str, guessed: float, price: float, as_down: bool) -> bool:
    """One sentence of ``reply`` says the guessed sum is the down payment (``as_down``) or
    the loan, beside the price: the reading the note would say, not the other one."""
    after, before = (
        (_AS_DOWN_AFTER, _AS_DOWN_BEFORE) if as_down else (_AS_LOAN_AFTER, _AS_LOAN_BEFORE)
    )
    for sentence in _SENTENCE.split(reply or ""):
        found = list(_SUM.finditer(sentence))
        if price not in {_value(match) for match in found}:
            continue
        for match in found:
            if _value(match) != guessed:
                continue
            ahead = sentence[match.end() : match.end() + _NEARBY]
            behind = sentence[max(0, match.start() - _NEARBY) : match.start()]
            if after.match(ahead) or before.search(behind):
                return True
    return False


def _value(match: re.Match[str]) -> float:
    return float(match.group(1).replace(",", "")) * _SCALE.get((match.group(2) or "").lower(), 1)


def market_note(worked: Worked, average: MarketRate | None, ratio: float) -> str | None:
    if average is None:
        return None
    rate_input = rate_name(worked.product)
    rate = worked.values[rate_input]
    source = f"[{average.source_title}]({average.source_url})"
    when = day_text(average.as_of)
    level = percent_text(average.value)
    caveat = f" {average.caveat}" if average.caveat else ""
    if rate_input in worked.assumed:
        return (
            f"**Note:** this uses today's average {average.name} in {average.country}, "
            f"{level} as of {when} ({source}).{caveat}"
        )
    unrealistic = average.value <= 0 or not average.value / ratio <= rate <= average.value * ratio
    if unrealistic and not caveat:
        return (
            f"**Note:** {percent_text(rate)} is not a realistic {average.name}. As of {when}, "
            f"the average in {average.country} is {level} ({source})."
        )
    return (
        f"**Note:** for reference, the average {average.name} in {average.country} is "
        f"{level} as of {when} ({source}).{caveat}"
    )
