"""A loan reply whose stated payment is not its card's gets the card's figures in a line.

Live (2026-10-26, free model): "House buying for 400k" then "60k at 6 percent". The card
and the note under the reply said 340,000 borrowed at $2,038.47 a month; the reply above
them said "**Monthly Payment:** $359.82", worked on 60,000. A reply that contradicts its
own card is the worst a money turn can do.

The model's words are never replaced or removed: a review (2026-10-26) found that rule
dropped correct replies with taxes, other scenarios, rounding, the worked formula, and
the user's own question. Only a payment the reply states next to its label ("monthly
payment is $X", "$X a month", "$X/month", "$X per month") is read; an approximate one
("about $2,040", "≈", a range) is not. When the reply states at least one, none is the
card's payment (to the cent or the whole unit), and none sits in a sentence about another
scenario (another term, rate or sum; "if you", "instead", taxes, insurance, PMI, HOA), the
server adds one line above the note: "The card's figures: **$2,038.47** a month on a
$340,000 loan at 6% over 30 years."
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.modules.money.numbers import money_text, percent_text
from app.modules.money.phrases import percent_value
from app.modules.money.read import MoneyRequest
from app.modules.money.solve import Worked, rate_name

logger = logging.getLogger(__name__)

_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "₹", "NGN": "₦"}
_SUM = (
    r"(?P<sign>\\?[$€£¥₹₦])?\s?(?P<whole>\d{1,3}(?:(?:,|\{,\})\d{3})+|\d+)"
    r"(?:\.(?P<cents>\d{2}))?(?!\d)"
)
# A dash, an en dash, an em dash or "to" between two sums.
_DASH = "(?:-|\u2013|\u2014|to)"
_LABELLED = (
    re.compile(
        rf"monthly\s+payments?\W{{0,6}}(?:(?:is|of|would\s+be|will\s+be|comes\s+to|=)\W{{0,4}})?{_SUM}",
        re.IGNORECASE,
    ),
    re.compile(rf"(?<![\d.,]){_SUM}\W{{0,4}}(?:a|per|/|each)\s?(?:month|mo)\b", re.IGNORECASE),
)
# Before a sum: it is approximate. Around it: a range.
_APPROX = re.compile(
    r"(?:about|around|roughly|approximately|approx\.?|nearly|almost|close\s+to|just\s+(?:under"
    r"|over)|under|over|up\s+to|at\s+least|~|≈|\\approx)\W{0,3}$",
    re.IGNORECASE,
)
_RANGE = re.compile(rf"^\s?{_DASH}\s?\W?\d")
_RANGE_BEFORE = re.compile(rf"\d\s?{_DASH}\s?\W?$")
_OTHER_SCENARIO = re.compile(
    r"\b(?:if\s+you|instead|plus|including|includes|extra|tax(?:es)?|insurance|pmi|hoa|escrow"
    r"|total\s+housing|split|each\s+of\s+you|refinanc\w*|with\s+\d+(?:\.\d+)?\s?%\s+down"
    r"|without|for\s+comparison|compared|the\s+full|no\s+(?:money\s+)?down|zero\s+down"
    r"|what\s+if|if\s+(?:you|we|the|your)|each\s+\$|per\s+\$|income|salary|earn\w*|gross"
    r"|rent|budget|savings?)\b",
    re.IGNORECASE,
)
# Read whole, as the asker's rate is: "3,5%" is 3.5, never a 5% scenario of its own.
_PERCENT = re.compile(r"(?<![\d.])(?<!\d,)(\d+(?:[.,]\d+)?)\s?(?:\\?%|percent\b)", re.IGNORECASE)
_TERM = re.compile(r"\b(\d{1,3})[\s-]?(years?|yrs?|months?)\b", re.IGNORECASE)
_MONEY = re.compile(
    r"(?<![\d.,])[$€£¥₹₦]\s?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?)(?:\s?([km])\b)?", re.I
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
# Any sum in any written form: "340,000", "$340k", "340 thousand", "2,038.47".
_ANY_SUM = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(\s?(?:k|m|thousand)\b)?",
    re.IGNORECASE,
)
_SCALES = {"k": 1_000, "m": 1_000_000, "thousand": 1_000}
# A payment this near the card's is the card's; one this far off, on a reply that never
# names the card's figures, is another loan's.
_NEAR_PAYMENT = 0.01
_MISREAD = 0.05


@dataclass(frozen=True)
class CardFigures:
    """The server's line, and whether it opens the reply (a misread loan) or follows it."""

    line: str
    on_top: bool


def card_figures(text: str, request: MoneyRequest, worked: Worked) -> CardFigures | None:
    """The card's figures in a line when the reply states another payment, else None.

    A reply that never states the card's principal or payment but gives a payment more than
    ``_MISREAD`` off it worked another loan (live, 2026-10-26: "the monthly payment for $60k
    is roughly **$360**" above a card of $340,000 at $2,038.47): the line opens the reply.
    Otherwise the reply compares; only an exact payment outside any other scenario gets
    the line, after the reply."""
    product = worked.product
    payment = worked.outputs.get("payment")
    if product.family != "loan" or payment is None:
        return None
    sentences = _SENTENCE.split(text or "")
    if not _states_card(text, worked.values["amount"], payment):
        misread = [
            value
            for sentence in sentences
            for value, _cents in _labelled(sentence, approximate=True)
            if not _other_scenario(sentence, request, worked, value, sums=False)
        ]
        if any(abs(value - payment) > _MISREAD * payment for value in misread):
            logger.info("money reply worked another loan than its card; the card's figures lead")
            return CardFigures(_line(request, worked, payment, on_top=True), on_top=True)
    stated: list[tuple[float, bool]] = []
    for sentence in sentences:
        for value, cents in _labelled(sentence):
            if _other_scenario(sentence, request, worked, value):
                return None
            stated.append((value, cents))
    if not stated or any(_is(value, cents, payment) for value, cents in stated):
        return None
    logger.info("money reply stated a payment its card does not; the card's figures added")
    return CardFigures(_line(request, worked, payment, on_top=False), on_top=False)


def _states_card(text: str, principal: float, payment: float) -> bool:
    """The reply names the card's principal ("340,000", "$340k") or its payment (to the cent,
    the whole unit, or within ``_NEAR_PAYMENT``)."""
    plain = (text or "").replace("{,}", ",")
    for found in _ANY_SUM.finditer(plain):
        value = float(found.group(1).replace(",", ""))
        value *= _SCALES.get((found.group(2) or "").lower().strip(), 1)
        if value == principal or abs(value - payment) <= _NEAR_PAYMENT * payment:
            return True
    return False


def _labelled(sentence: str, *, approximate: bool = False) -> list[tuple[float, bool]]:
    """Payments stated beside their label; an approximate one only when ``approximate``."""
    found: list[tuple[float, bool]] = []
    for pattern in _LABELLED:
        for match in pattern.finditer(sentence):
            if not approximate and _APPROX.search(sentence[: match.start("whole")]):
                continue
            if _RANGE.match(sentence[match.end() :]) or _RANGE_BEFORE.search(
                sentence[: match.start("whole")]
            ):
                continue
            whole = match.group("whole").replace("{,}", "").replace(",", "")
            cents = match.group("cents")
            value = float(whole) + (float("0." + cents) if cents else 0.0)
            found.append((value, cents is not None))
    return found


def _is(value: float, cents: bool, payment: float) -> bool:
    return round(value, 2) == round(payment, 2) if cents else value == round(payment)


def _other_scenario(
    sentence: str, request: MoneyRequest, worked: Worked, value: float, *, sums: bool = True
) -> bool:
    """The sentence is about another loan: other words, rate, term or (``sums``) sum."""
    if _OTHER_SCENARIO.search(sentence):
        return True
    rate = worked.values[rate_name(worked.product)]
    for found in _PERCENT.findall(sentence):
        said = percent_value(found)
        if said is None or abs(said - rate) > 1e-6:
            return True
    term_name = "years" if "years" in worked.values else "months"
    for count, unit in _TERM.findall(sentence):
        months = float(count) * (12 if unit.lower().startswith(("y", "yr")) else 1)
        own = worked.values[term_name] * (12 if term_name == "years" else 1)
        if months != own:
            return True
    if not sums:
        return False
    own_sums = {round(v) for v in (worked.values.get("amount"), request.price, request.down) if v}
    own_sums |= {round(v) for v in worked.outputs.values() if v is not None}
    for digits, scale in _MONEY.findall(sentence):
        amount = float(digits.replace(",", "")) * {"k": 1_000, "m": 1_000_000}.get(scale.lower(), 1)
        if amount >= 1_000 and round(amount) not in own_sums and amount != value:
            return True
    return False


def _line(request: MoneyRequest, worked: Worked, payment: float, *, on_top: bool) -> str:
    symbol = _SYMBOLS.get(request.currency, "")
    values = worked.values
    term_name = "years" if "years" in values else "months"
    rate = percent_text(values[rate_name(worked.product)])
    rest = (
        f"a month on a {symbol}{money_text(values['amount'])} loan at {rate} over "
        f"{values[term_name]:g} {term_name}."
    )
    if on_top:
        return f"**The card's figures:** {symbol}{money_text(payment)} {rest}"
    return f"The card's figures: **{symbol}{money_text(payment)}** {rest}"
