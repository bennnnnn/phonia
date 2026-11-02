"""A loan told over two lines: what the user is buying, then its amount and rate.

Live (2026-10-25): "I am planing to buy a car", the reply asking new or used and the
budget, then "20k with 6 percent". Neither line is a request on its own (``read`` needs
the product, the amount and the rate in one line), so no card was built and the model's
own totals were off ($1,930 interest where 20k at 6% over 36 months is $1,904).

Both lines are read by a positive grammar: every word belongs to a known phrase, and any
other word means the line is not this, and the model answers it as before.

- The user's line before says they are buying what a loan product finances
  (``Product.goods``): "I am planning to buy a car", "we want to buy a used car", "buying
  a house for 400k", "House buying for 400k", "car shopping for 20k", "I'm house hunting",
  "shopping for a car", "I'm getting a 30k truck next month". Not "I bought a car last
  week", "buy a house in minecraft", "buying a car for my son" or "car shopping for 3
  hours".
- With no price there, this line is only an amount and a rate, and maybe a term: "20k
  with 6 percent", "$20,000 at 6% apr", "20k at 6% for 5 years". The amount is what they
  will pay for it, financed whole, so a down payment told after it comes off it.
- With a price there, an amount said to be down comes off it ("60k down at 6%", "with 60k
  down", "down payment of 60k at 6 percent"). A bare amount may be either: "60k at 6
  percent" after "House buying for 400k" (live) was the down payment the reply had asked
  for. A third of the price or less is read as the down payment, two thirds or more as
  the loan; between, it stays with the model. A year ("2026 at 6%") and a sum under 1,000
  are never read as either. The reply's note says how it was read
  (``guessed``), so a misread shows, and the amount slider puts it right.

A down payment on its own line after the loan ("down payment 3k" after "20k with 6
percent") is a change of that loan, read by ``change_line`` and worked in ``follow_up``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

from app.modules.money.catalog import PRODUCTS, Product
from app.modules.money.kinds import named_variant
from app.modules.money.phrases import (
    CURRENCY_WORDS,
    DURATION,
    PERCENT,
    count_value,
    percent_value,
    sum_phrase,
)
from app.modules.money.read import MoneyRequest, bare_year, read_sum, term_in
from app.modules.money.solve import rate_name
from app.services.text_normalize import collapse_ws, straighten_apostrophes

_MAX_CHARS = 120


def _marked_sum(name: str) -> str:
    """A sum written as money: a currency sign or word, k/m/grand, or thousands commas.

    A bare number before what is bought is its model year as often as its price: "a 2018
    truck", "a 1999 car". Only a sum marked as money is the price there ("a 30k car").
    """
    number = r"\d[\d,]*(?:\.\d{1,2})?"
    scale = r"(?:k|m|thousand|million|mil|grand)"
    word = rf"(?:\s(?:{CURRENCY_WORDS}))"
    return (
        rf"(?P<{name}>[$€£¥₹₦]\s?{number}(?:\s?{scale})?{word}?"
        rf"|{number}\s?{scale}{word}?"
        rf"|\d{{1,3}}(?:,\d{{3}})+(?:\.\d{{1,2}})?{word}?"
        rf"|{number}{word})"
    )


# --- The line before: what is being bought -------------------------------------------

_WHO = r"(?:i|we|i'm|im|we're|i\sam|we\sare|i'd|we'd|i'll|we'll)\s"
_INTENT = (
    r"(?:plan(?:ning|ing)?\s(?:to|on)|thinking\s(?:of|about)|looking\sto|going\sto|gonna|"
    r"about\sto|hoping\sto|want(?:ing)?\sto|wanna|would\slike\sto|like\sto|need\sto|"
    r"ready\sto|trying\sto)\s"
)
_ARTICLE = r"(?:(?:a|an|the|my|our)\s)?"
# "Get my car" is a car already theirs (from the shop, back from a friend): "my" and "our"
# go only with a verb that buys.
_VERB = (
    r"(?:(?:buy(?:ing)?|purchas(?:e|ing)|financ(?:e|ing))\s(?:(?:a|an|the|my|our)\s)?"
    r"|get(?:ting)?\s(?:(?:a|an|the)\s)?)"
)
# Shopping for one: "car shopping", "house hunting", "shopping for a car".
_SHOPPING = r"(?:buying|purchase|shopping|hunting)"
_LOOKING = r"(?:shopping\sfor|looking\s(?:for|at))\s"
# A model year describes what is bought: "a 2018 truck", "a used 2015 car".
_YEAR = r"(?:(?:19|20)\d{2}\s)?"
_PRICE_WORD = r"(?:for|at|worth|costing|priced\sat)"
_WHEN = r"(?:\s(?:soon|next\s(?:week|month|year)|this\s(?:week|month|year)))?"


@cache
def _purchase_lines(product_key: str) -> tuple[re.Pattern[str], ...]:
    item = next(row for row in PRODUCTS if row.key == product_key)
    used = "|".join(re.escape(word) for variant in item.variants for word in variant.words)
    kind = rf"(?:(?:(?:brand\s)?new|(?:certified\s)?(?:{used}))\s)?" if used else r"(?:new\s)?"
    good = "(?:" + "|".join(re.escape(word) for word in item.goods) + ")"
    price = rf"(?:\s{_PRICE_WORD}\s{sum_phrase('price')})?{_WHEN}"
    return (
        re.compile(
            rf"(?:{_WHO})?(?:{_INTENT})?{_VERB}(?:{_marked_sum('price_before')}\s)?"
            rf"{_YEAR}{kind}{_YEAR}{good}{price}"
        ),
        # "House buying for 400k", "I'm car shopping".
        re.compile(rf"(?:{_WHO})?{_ARTICLE}{_YEAR}{kind}{_YEAR}{good}\s{_SHOPPING}{price}"),
        # "Shopping for a car", "we're looking at houses for 400k".
        re.compile(
            rf"(?:{_WHO})?(?:{_INTENT})?{_LOOKING}{_ARTICLE}{_YEAR}{kind}{_YEAR}{good}s?{price}"
        ),
    )


@dataclass(frozen=True)
class _Purchase:
    product: Product
    # The price and its currency, when the line named one.
    price: tuple[float, str] | None


def _purchase(line: str) -> _Purchase | None:
    text = _normal(line)
    for item in PRODUCTS:
        if not item.goods:
            continue
        for pattern in _purchase_lines(item.key):
            match = pattern.fullmatch(text)
            if match is None:
                continue
            written = match.groupdict().get("price") or match.groupdict().get("price_before")
            price = read_sum(written) if written else None
            if written and price is None:
                return None
            return _Purchase(item, price)
    return None


# --- This line: the amount and the rate ----------------------------------------------

_RATE_WORDS = r"(?:\s(?:interest(?:\srate)?|apr|rate|fixed))?"
_TERM = rf"(?:\s(?:for|over)\s{DURATION})?"
_LOAN_LINE = re.compile(rf"{sum_phrase('sum')}\s(?:with|at|@)\s{PERCENT}{_RATE_WORDS}{_TERM}")
_DOWN_RATE = rf"(?:,?\s(?:with|at|and)\s{PERCENT}{_RATE_WORDS})?{_TERM}"
_DOWN_LINES = (
    # "60k down at 6%", "with 60k down", "I can put 60k down".
    re.compile(
        rf"(?:with\s|(?:(?:i|we)\s(?:can|could|will)\s|i'll\s|we'll\s)?put(?:ting)?\s)?"
        rf"{sum_phrase('sum')}\sdown(?:\s?payment)?{_DOWN_RATE}"
    ),
    # "Down payment of 60k at 6 percent".
    re.compile(
        rf"(?:(?:a|the|my)\s)?down\s?payment(?:\s(?:of|is))?\s{sum_phrase('sum')}{_DOWN_RATE}"
    ),
)


# A bare amount after a price: up to a third of it is the down payment ("60k" on a 400k
# house), from two thirds the loan ("320k at 6%"); between, either.
_DOWN_SHARE = 1 / 3
_LOAN_SHARE = 2 / 3
# "$500 at 6%" beside a 400k house is neither.
_LEAST_GUESSED = 1000


def purchase_request(line: str, before: Sequence[str]) -> MoneyRequest | None:
    """The loan ``line`` gives for what ``before`` says the user is buying, or None.

    ``before`` is the user's line before this one in the parts its turn read it in; it
    counts only as one part, a line about buying and nothing else.
    """
    if len(before) != 1 or len(line) > _MAX_CHARS:
        return None
    bought = _purchase(before[0])
    if bought is None:
        return None
    text = _normal(line)
    patterns = (_LOAN_LINE,) if bought.price is None else (*_DOWN_LINES, _LOAN_LINE)
    match = next((found for pattern in patterns if (found := pattern.fullmatch(text))), None)
    said = read_sum(match["sum"]) if match is not None and not bare_year(match["sum"]) else None
    if match is None or said is None:
        return None
    amount, currency = said
    price = down = None
    guessed = ""
    if bought.price is None:
        price = amount
    else:
        price, priced_in = bought.price
        if (currency and priced_in and currency != priced_in) or not 0 < amount <= price:
            return None
        currency = currency or priced_in
        if match.re is _LOAN_LINE:
            guessed = _guess(amount, price)
            if not guessed:
                return None
        if guessed in ("loan", "whole"):
            down = price - amount or None
            guessed = "" if guessed == "whole" else guessed
        else:
            if amount == price:
                return None
            down, amount = amount, price - amount
    product = bought.product
    values = {"amount": amount}
    if match["pct"] is not None:
        rate = percent_value(match["pct"])
        if rate is None:
            return None
        values[rate_name(product)] = rate
    if match["n"] is not None:
        values.update(term_in(product, count_value(match["n"]), match["unit"]))
    variant = named_variant(product, before[0])
    return MoneyRequest(
        product,
        values,
        currency,
        variant=variant,
        price=price,
        down=down,
        guessed=guessed,
        rates_given=0 if match["pct"] is None else 1,
    )


def _guess(amount: float, price: float) -> str:
    """What a bare amount beside a price is: "down", "loan", "whole" (the price itself, a
    loan for all of it: nothing to say), or "" for either."""
    share = amount / price
    if amount < _LEAST_GUESSED:
        return ""
    if share == 1:
        return "whole"
    if share <= _DOWN_SHARE:
        return "down"
    return "loan" if share >= _LOAN_SHARE else ""


def _normal(line: str) -> str:
    return collapse_ws(straighten_apostrophes(line)).lower().strip(" .!?\u2026")
