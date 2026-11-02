"""Change from a payment: the total of what was bought, taken from what was paid.

"I bought 3 notebooks at $2.40 each and a pen for $1.85. I paid with a $20 bill.
how much change do i get" is 20 - (3 * 2.40 + 1.85) = 10.95. Every item is a
count at a price *each*, or one item at a price; "3 notebooks for $2.40" could
be either, so it is declined. Money is kept in exact decimals, never floats.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.number_text import count_word_pattern, number_word_value
from app.services.workout import Workout, math_line, render_workout

# prepare() reads "$2.40 ... $1.85" as an inline-maths span and drops the signs,
# so the sign is optional; the item, payment and "change" words carry the money.
_PRICE = r"(?:\$\s*)?(?P<{0}>\d+(?:\.\d{{1,2}})?)(?:\s*dollars)?"
_PERSON = r"(?:i|you|we|he|she|they|[A-Z][a-z]{1,15})"
_ITEM_NAME = r"(?P<name>[a-z]+(?:\s+[a-z]+){0,2}?)"
_ITEM_FORMS = (
    re.compile(
        rf"(?P<count>\d{{1,3}}|{count_word_pattern()})\s+{_ITEM_NAME}\s+(?:at|for)\s+"
        rf"{_PRICE.format('price')}\s*(?:each|apiece|a\s+piece)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:an?|one)\s+{_ITEM_NAME}\s+(?:for|at)\s+{_PRICE.format('price')}", re.IGNORECASE
    ),
)
_ITEM_SPLIT = re.compile(r"\s?,\s*(?:and\s+)?|\sand\s+", re.IGNORECASE)
_CHANGE = re.compile(
    rf"{_PERSON}\s+(?:bought|buy|buys|purchased)\s+(?P<items>.+?)\s*[.;]\s*"
    rf"{_PERSON}\s+(?:paid|pay|pays|gave|gives|handed|hand)\s+(?:the\s+cashier\s+)?"
    rf"(?:with\s+)?(?:an?\s+)?{_PRICE.format('paid')}(?:\s+(?:bill|note))?"
    rf"\s*[.,;]?\s*(?:how\s+much\s+change\s+(?:do|does|did|will|should|would)\s+{_PERSON}\s+"
    r"(?:get|receive)(?:\s+back)?|what\s+is\s+the\s+change)\s*[?.!]?\s*",
    re.IGNORECASE,
)
_MAX_ITEMS = 6


def _price(match: re.Match[str], name: str) -> str:
    return match.group(name)


def extract_change_intent(cleaned: str) -> MathIntent | None:
    """The whole message is purchases, a payment and "how much change"."""
    if len(cleaned) > 400:
        return None
    match = _CHANGE.fullmatch(" ".join(cleaned.split()))
    if match is None:
        return None
    terms: list[str] = []
    for piece in _ITEM_SPLIT.split(match.group("items")):
        item = next((m for form in _ITEM_FORMS if (m := form.fullmatch(piece.strip()))), None)
        if item is None:
            return None
        price = _price(item, "price")
        raw_count = item.groupdict().get("count")
        count = 1 if raw_count is None else number_word_value(raw_count) or int(raw_count)
        terms.append(price if raw_count is None else f"{count}*{price}")
    paid = _price(match, "paid")
    if not 1 <= len(terms) <= _MAX_ITEMS or Decimal(paid) <= _total(terms):
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="change_from_payment",
        # The payment, then each item as "count*price" or "price".
        arithmetic_operands=[paid, *terms],
        operation="solve",
    )


def _total(terms: list[str]) -> Decimal:
    total = Decimal(0)
    for term in terms:
        count, _, price = term.rpartition("*")
        total += Decimal(price) * (int(count) if count else 1)
    return total


def _money(value: Decimal, *, cents: bool) -> str:
    """Two decimals when any price has cents ("10.95", "11.00"), else whole dollars."""
    return f"{value:.2f}" if cents else f"{value:f}"


def change_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    operands = intent.arithmetic_operands or []
    if len(operands) < 2:
        return None
    paid, terms = Decimal(operands[0]), operands[1:]
    total = _total(terms)
    change = paid - total
    if change <= 0:
        return None
    cents = any("." in operand for operand in operands)
    paid_text, total_text = _money(paid, cents=cents), _money(total, cents=cents)
    change_text = _money(change, cents=cents)
    answer = rf"\${change_text}"
    items = [term.rpartition("*") for term in terms]
    written = " + ".join(
        rf"{count} \times {price}" if count else price for count, _, price in items
    )
    lines.append(f"Total cost = {total_text}")
    lines.append(f"Change = {paid_text} - {total_text} = {change_text}")
    given = tuple(
        math_line(rf"\${price}", f"each, {count} bought" if count else "one item")
        for count, _, price in items
    )
    worked = render_workout(
        Workout(
            given=(*given, math_line(rf"\${paid_text}", "paid")),
            find=(math_line(r"\text{change}"),),
            formula=(math_line(r"\text{change} = \text{paid} - \text{total cost}"),),
            substitution=(
                math_line(rf"\text{{total cost}} = {written} = {total_text}"),
                math_line(rf"\text{{change}} = {paid_text} - {total_text} = {change_text}"),
            ),
        ),
        answer,
    )
    return replace(finish_with_answer(lines, answer), worked_reply=worked)
