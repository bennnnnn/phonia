"""Which sum in a loan request is the loan: the one borrowed, or the price less what is put
down, or none.

Live (2026-10-31, an Ethiopian grade 12 book): "a house that costs Birr 250,000. He has
saved Birr 50,000 which he will use as a deposit, and will finance the rest of the cost
by taking out a loan" was worked as a loan of 250,000, the first sum, and the card's
payment was the price's.

- A sum said to be borrowed or owed ("still owe 20k", "I borrowed $20,000") is the loan as
  it stands: money put down came off it already.
- Otherwise the loan is the price less the sum put down, said as a down payment or a
  deposit (also in a clause after it, "which he will use as a deposit"), or as paid toward
  it when "the rest" is borrowed ("she pays $5,000 and borrows the rest").
- Two sums with one said to be a price and none borrowed or named a loan say no loan
  ("the difference between a $300,000 house and a $350,000 house"): none is read, and the
  model answers. An income ("my salary is $90,000") is never a candidate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.money.sums import Sum


@dataclass(frozen=True)
class LoanSums:
    amount: float | None
    # A price with money down; a new down payment is taken off this price (``follow_up``).
    price: float | None = None
    down: float | None = None


# "Finance the rest of the cost", "borrows the remainder", "the rest is on a loan".
_REST = re.compile(
    r"\b(?:borrow\w*|financ\w*|cover\w*)\s(?:for\s)?the\s(?:rest|remainder|difference|"
    r"remaining\s(?:amount|cost|price|sum))\b"
    r"|\bthe\s(?:rest|remainder)\b[^.;!?]{0,40}?\b(?:borrowed|financed|on\s(?:a|the)\s(?:loan|"
    r"mortgage)|(?:by|with|through)\s(?:taking\s(?:out\s)?)?(?:a|the)\s(?:loan|mortgage))\b",
    re.I,
)


def rest_is_borrowed(text: str) -> bool:
    """The message borrows what is left of the price: "and borrows the rest"."""
    return _REST.search(text) is not None


def loan_sums(sums: list[Sum], share: float | None, rest: bool) -> LoanSums:
    """The loan, and its price and down payment when the request gives money down."""
    once = [item for item in sums if not item.monthly and not item.income]
    named = [item for item in once if not item.down]
    borrowed = {item.value for item in named if item.borrowed}
    if borrowed:
        return LoanSums(borrowed.pop()) if len(borrowed) == 1 else LoanSums(None)
    if rest and len(named) == 2 and len(once) == 2 and not any(item.loan for item in named):
        put, cost = sorted(named, key=lambda item: item.value)
        if put.paid and put.value < cost.value:
            return LoanSums(cost.value - put.value, cost.value, put.value)
        return LoanSums(None)
    if len(named) > 1:
        loans = [item for item in named if item.loan]
        if len(loans) == 1 and len(named) == len(once):
            return LoanSums(loans[0].value)
        if any(item.price for item in named):
            return LoanSums(None)
    first = named[0].value if named else None
    down = _down(once, first, share)
    if first is None or first <= (down or 0.0) or (down is not None and down < 0):
        return LoanSums(None)
    if down is not None and 0 < down < first:
        return LoanSums(first - down, first, down)
    return LoanSums(first)


def _down(once: list[Sum], first: float | None, share: float | None) -> float | None:
    """The sum down: said ("3000 down"), else a share of the first sum ("20% down"); -1
    (no loan) when two are given that differ."""
    said = {item.value for item in once if item.down}
    if share is not None and first is not None:
        said.add(first * share / 100)
    if len(said) > 1:
        return -1.0
    return said.pop() if said else None
