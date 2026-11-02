"""Read a money request from the user's words: which product, and the numbers they gave.

"what is my mortgage for 300k dollars house if mr rate is 1 percent" is a mortgage of
300 000 USD at 1 %, its term left to the product's default. The reader is word rules
only, no model call, and it reads nothing it cannot find: a missing number stays
missing for ``solve`` to fill from a default or today's average, or for the model to ask.

A product word alone is not a request ("I'm saving for a house", "credit card design"):
the message also needs a rate, an amount with a loan word, or a question about today's
rates. Yearly simple or compound interest ("compound interest on 1000 at 5% for 3
years") is maths homework and stays with maths.

The kind of the product is read by ``kinds`` ("buying a used car" is looked up at the
used-car average), each sum's role by ``sums`` and the loan among them by ``loan_sums``.
The percent and the length of time (``phrases``) are shared with ``change_line``, which
reads a follow-up ("what if i only do 3 years instead") by its own stricter grammar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.money.catalog import PRODUCTS, Product
from app.modules.money.compounding import UNKNOWN, compounding_per_year
from app.modules.money.kinds import named_variant
from app.modules.money.loan_sums import LoanSums, loan_sums, rest_is_borrowed
from app.modules.money.phrases import (
    AMOUNT,
    CURRENCY_WORD,
    CURRENCY_WORDS,
    MULTIPLIERS,
    RATE,
    TERM,
    amount_value,
    count_value,
    grouped,
    percent_value,
)
from app.modules.money.sums import MEASUREMENT, SAYS_MONEY, Sum, amounts

_YEAR = re.compile(r"(?:19|20)\d{2}")
# A percent that is a share of the price put down: "20% down", "a down payment of 20%",
# "down payment 20%", "putting down 20%". Not a rate beside a sum down ("at 7% down
# payment of 5000", "100k down payment 6.25%"), "6% down payment 20%" (the 20% is the
# share), "rate is 6% down from 7%" or "at 6%".
_MONEY_NEXT = (
    r"\s?(?:[$€£¥₹₦]\s?\d|\d[\d,]*(?:\.\d+)?\s?(?:k|m|thousand|million|mil|grand)\b"
    r"|\d{1,3}(?:,\d{3})+|\d{4,})"
)
_PERCENT_NEXT = r"\s?\d{1,3}(?:\.\d+)?\s?(?:%|percent\b|per\s?cent\b|pct\b)"
# "6% down from 7%" is a rate that fell; "20% down on a $400k home" is the share put down.
_NOT_A_SHARE = r"(?!\s(?:from|to|by)\b)"
_SHARE_DOWN_AFTER = re.compile(
    rf"\s?down\s?payment\b{_NOT_A_SHARE}(?!{_MONEY_NEXT})(?!{_PERCENT_NEXT})"
    rf"|\s?(?:as\s(?:a\s)?down\s?payment|down(?!\s?payment))\b{_NOT_A_SHARE}(?!{_MONEY_NEXT})",
    re.I,
)
_SHARE_DOWN_BEFORE = re.compile(
    r"\bdown\s?payment(?:\s(?:of|is))?\s?$|\bput(?:ting)?\s(?:down\s)?$", re.I
)
# "100k down payment 6.25%": a sum is the down payment, so the percent is the rate.
_SUM_DOWN_BEFORE = re.compile(
    r"(?:[$€£¥₹₦]\s?)?\d[\d,.]*\s?(?:k|m|thousand|million|mil|grand)?\s"
    r"(?:as\s(?:a\s)?)?down\s?payment(?:\s(?:of|is))?\s?$",
    re.I,
)
_RATE_BEFORE = re.compile(r"\b(?:at|@)\s?$", re.I)
# Words that make a product word a money request ("car" alone is not; "car loan" at 6 % is).
_FINANCE = re.compile(
    r"\b(?:loan|loans|mortgage|payments?|pay|paying|apr|interest|rates?|finance|financing|"
    r"borrow(?:ing)?|owe|balance|monthly|deposit(?:ing)?|compounded|save\s\d)\b",
    re.I,
)
_RATES_QUESTION = re.compile(
    r"\b(?:current|today'?s|latest|average|typical|going)\b[^.?!\n]{0,40}\b(?:rates?|aprs?|apy)\b"
    r"|\b(?:rates?|aprs?|apy)\b[^.?!\n]{0,40}\b(?:now|today|currently|these\sdays|"
    r"this\s(?:week|month|year))\b",
    re.I,
)
# Yearly simple or compound interest is a school exercise maths works (math.school), and
# interest said to be simple ("if interest is simple", "no compounding", "I = PRT") is no
# amortised loan or compounded saving.
_HOMEWORK_INTEREST = re.compile(
    r"\b(?:simple|compound)\s+interest\b|\bcompounded\s+(?:annually|yearly|every\s+year)\b"
    r"|\binterest\s+is\s+simple\b|\b(?:no|without)\s+compounding\b|\bnot\s+compounded\b"
    r"|\bI\s*=\s*P\s*[*\u00d7\u00b7]?\s*R\s*[*\u00d7\u00b7]?\s*T\b",
    re.I,
)
# A recurring deposit pays in every month: "Rs 10,000 in a recurring deposit" read as one
# lump sum worked the wrong account (2026-10-31). Savings that says so must read a monthly
# deposit, or it is not worked.
_RECURRING = re.compile(r"\brecurring\s+deposits?\b|\binstal+ments?\b", re.I)
_RD = re.compile(r"\bRDs?\b")
_CURRENCIES = {
    "$": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "bucks": "USD",
    "usd": "USD",
    "€": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "gbp": "GBP",
    "birr": "ETB",
    "etb": "ETB",
    "₹": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "inr": "INR",
    "₦": "NGN",
    "naira": "NGN",
    "ngn": "NGN",
    "shilling": "KES",
    "shillings": "KES",
    "kes": "KES",
    "¥": "JPY",
    "yen": "JPY",
    "jpy": "JPY",
    "cad": "CAD",
    "aud": "AUD",
}
_TERM_UNITS = {"year": "years", "years": "years", "yr": "years", "yrs": "years"}
# A length of time that is no term: an age, time gone by, a gap, payments already made
# ("ten years ago", "thirty years old", "five years apart", "been paying for three years",
# "twelve months of payments", "for the past 3 years", "every 3 months").
_SPAN_AFTER = re.compile(
    r"\s?(?:-\s?)?(?:ago|old|apart|of\sage|"
    r"of\s(?:payments?|paying|saving|savings|work|experience|service|marriage))\b",
    re.I,
)
# Another length offered beside a term: "15 or 30 years", "36 or 60 months", "15 vs 30 year".
_TERM_CHOICE = re.compile(
    r"(?<![\w.])\d{1,3}(?:\.\d+)?(?:[\s-]?(?:years?|yrs?|months?))?\s*(?:or|to|-|\u2013|/|vs\.?|versus)\s*$",
    re.I,
)
_SPAN_BEFORE = re.compile(
    r"\b(?:been\s(?:\w+\s){0,2}(?:for\s)?|(?:the|my|our)\s(?:past|last|previous)\s|made\s|"
    r"every\s|each\s|per\s|aged?\s)$",
    re.I,
)
# "for five years" in a clause about time already spent on a loan held ("I've been paying my
# mortgage at 4% for five years", "we have had our loan for 5 years") is time gone by, not
# the loan's term (2026-11-01: a 5-year mortgage worked from it). Only paying, owning or
# holding a loan counts, with the loan as the verb's object: "I've been looking at a car
# loan at 6% for 3 years", "I've had my eye on one", "I've paid $5k toward a down payment
# on a $300k mortgage at 6% for 15 years" and "we have had a mortgage offer of $300k … for
# 15 years" ask about a new loan's term.
_HELD = r"(?:mortgage|loan|card|balance|debt)s?"
# The held loan ends its noun phrase: a preposition, a conjunction, punctuation or a sum
# follows it. "a car loan quote at 7% for 6 years" and "a mortgage offer of $300k" are a new
# loan's quote and offer, never one held.
_HELD_ENDS = (
    r"\b(?=\s*(?:(?:at|for|of|with|on|since|from|in|and|but|so|or)\b|[,.;:!?)]|[$€£¥₹₦\d]|$))"
)
_SPENT_CLAUSE = re.compile(
    r"\b(?:been\s(?:paying|repaying|making\s(?:payments|repayments)|servicing|carrying)"
    r"|(?:have|has|'ve|\u2019ve|'s|\u2019s)\s(?:paid|repaid|owned|held|carried|had))"
    r"\s(?:(?:on|off|down)\s)?(?:it|(?:my|our|his|her|their|the|this|that|a|an)\s"
    rf"(?:\S+\s){{0,3}}?{_HELD}{_HELD_ENDS})\b.*\bfor\s$",
    re.I | re.S,
)
# Where a clause starts: a sentence's end (never a decimal point, "4.5%"), a comma before a
# space (never "250,000"), or a conjunction.
_CLAUSE_BREAK = re.compile(
    r"[.?!;](?=\s|$)|\n|,\s|\b(?:and|but|so|or|yet|then|because|while|although|though)\b",
    re.I,
)
# A count word right before a term the reader did not take in whole ("two thousand and
# twenty months"): the term is not read.
_SCALE_BEFORE = re.compile(r"\b(?:hundred|thousand)\s(?:and\s)?$", re.I)


@dataclass(frozen=True)
class MoneyRequest:
    """What the user asked: a product, the inputs they gave, and their currency."""

    product: Product
    values: dict[str, float] = field(default_factory=dict)
    # ISO code from a symbol or word in the message; "" when it names none.
    currency: str = ""
    # "What are mortgage rates now?": today's average is the answer, with no numbers to work.
    rates_only: bool = False
    # The kind of the product named (a catalog ``Variant`` key: "used"); "" for none.
    variant: str = ""
    # What a follow-up changed ("months", "rate"); empty for a first ask.
    changed: tuple[str, ...] = ()
    # A loan for something bought with money down: its price and the down payment. A new
    # down payment is taken off this price, never off the loan ("follow_up").
    price: float | None = None
    down: float | None = None
    # A bare amount beside a price, read as the "down" payment or the "loan" (``purchase``).
    guessed: str = ""
    # How many rates the line gave: a down payment is worked after one only, so a line
    # read wrong ("20% down … 6%") never carries into a worked follow-up.
    rates_given: int = 0
    # Settings the request fixed (``Product.settings``): "compounded quarterly" is
    # ``per_year`` 4. One it left out takes the product's usual value.
    settings: dict[str, float] = field(default_factory=dict)


def bare_year(text: str) -> bool:
    """``text`` is a year written as a bare number ("2026"), not a sum."""
    return _YEAR.fullmatch(text.strip()) is not None


def read_money_request(text: str) -> MoneyRequest | None:
    """The money request in ``text``, or None when it is not one.

    Each slot (the sum, the rate, the term, the money down, the compounding) is read only
    when the message gives one value for it, read whole. Two rates or two terms ("a
    15-year at 5.5% or a 30-year at 6.25%"), two sums for one slot, a sum the reader
    cannot read whole ("₹5,00,00") or one paid each week give no worked numbers: the model
    answers."""
    if not text or len(text) > 600:
        return None
    found = named_product(text)
    if found is None or _HOMEWORK_INTEREST.search(text) or measures_without_money(text):
        return None
    rates, shares = _percents(text)
    sums = amounts(text)
    if sums is None or len(rates) > 1 or len(shares) > 1:
        return None
    if any(item.other_period and not item.income for item in sums):
        return None
    rate, share = next(iter(rates), None), next(iter(shares), None)
    currency = _currency(text)
    variant = named_variant(found, text)
    if rate is None and not sums:
        if _RATES_QUESTION.search(text):
            return MoneyRequest(found, {}, currency, rates_only=True, variant=variant)
        return None
    if rate is None and not _FINANCE.search(_RATE_OF_A_QUANTITY.sub(" ", text)):
        return None
    settings = _settings(found, text)
    if settings is None:
        return None
    loan = loan_sums(sums, share, rest_is_borrowed(text)) if found.family == "loan" else None
    values = _values(found, rate, sums, loan)
    term = _term(found, text)
    if values is None or term is None:
        return None
    values.update(term)
    if not any(name in values for name in _principal_names(found)):
        return None
    recurring = _RECURRING.search(text) is not None or _RD.search(text) is not None
    if found.family == "savings" and recurring and "deposit" not in values:
        return None
    return MoneyRequest(
        found,
        values,
        currency,
        variant=variant,
        price=loan.price if loan else None,
        down=loan.down if loan else None,
        rates_given=len(rates),
        settings=settings,
    )


def _settings(product: Product, text: str) -> dict[str, float] | None:
    """The settings ``text`` fixes; None when it says one the product cannot work: savings
    "compounded continuously", or a loan compounded other than monthly. A card's APR is
    charged a month at a time however it compounds, as its statement works it."""
    per_year = compounding_per_year(text)
    if per_year is None or product.family == "card_payoff":
        return {}
    if "per_year" in product.settings:
        return None if per_year == UNKNOWN else {"per_year": per_year}
    return {} if per_year == 12 else None


def named_product(text: str) -> Product | None:
    """The first product, most specific words first, that the message names."""
    lowered = text.lower()
    best: tuple[int, Product] | None = None
    for item in PRODUCTS:
        for word in item.words:
            match = re.search(rf"\b{re.escape(word)}\b", lowered)
            if match is None:
                continue
            # A longer phrase ("car loan") beats a word inside it ("loan").
            if best is None or len(word) > best[0]:
                best = (len(word), item)
    return best[1] if best is not None else None


def _percents(text: str) -> tuple[set[float], set[float]]:
    """The rates and the shares of the price put down ("20% down") the message gives:
    "a 400k house with 20% down at 6%" is the rate 6 and the share 20. A share that is no
    part of a price (0%, 100%) is one the reader cannot use, given as two."""
    rates: set[float] = set()
    shares: set[float] = set()
    for match in RATE.finditer(text):
        value = percent_value(match["pct"])
        if value is None:
            # A percent the reader cannot read ("3,125%") is one it cannot certify: given
            # as two, so the slot takes no value.
            rates |= {-1.0, -2.0}
        elif not _is_share_down(text, match):
            rates.add(value)
        else:
            shares |= {value} if 0 < value < 100 else {-1.0, -2.0}
    return rates, shares


def stated_sums(text: str) -> list[float]:
    """Every sum of money the message states, in order."""
    return [item.value for item in amounts(text) or []]


def _is_share_down(text: str, match: re.Match[str]) -> bool:
    before = text[max(0, match.start() - 24) : match.start()]
    if _RATE_BEFORE.search(before) or _SUM_DOWN_BEFORE.search(before):
        return False
    return bool(_SHARE_DOWN_AFTER.match(text, match.end()) or _SHARE_DOWN_BEFORE.search(before))


# "at the rate of 40 miles per hour", "a rate of 6 m/s2": a rate with no percent is no
# interest rate.
_RATE_OF_A_QUANTITY = re.compile(
    r"\brates?\s+of\s+\d[\d.,]*\s*(?!\d|%|per\s?cent|percent|pct)"
    r"|\b(?:constant|steady|uniform|same|average)\s+rates?\b",
    re.I,
)


def measures_without_money(text: str) -> bool:
    """A physics or maths quantity ("a 1500 kg car at the rate of 6m/s2") and no money
    word, currency or percent: "car" and "rate" there are no car loan (2026-10-30)."""
    return MEASUREMENT.search(text) is not None and SAYS_MONEY.search(text) is None


def read_sum(text: str) -> tuple[float, str] | None:
    """The one sum ``text`` is, whole ("$20k", "20,000 dollars", "3 grand"), with the
    currency it names (""), or None. A bare number is a sum only from 1000 up: "20 at 6%"
    is no loan."""
    text = text.strip()
    word = re.search(rf"\s?\b(?:{CURRENCY_WORDS})$", text, re.I)
    match = AMOUNT.fullmatch(text[: word.start()] if word else text)
    if match is None:
        return None
    number = amount_value(match["num"])
    if match["mult"]:
        number *= MULTIPLIERS[match["mult"].lower()]
    elif not (match["sym"] or word or grouped(match["num"]) or number >= 1000):
        return None
    return number, _currency(text)


def _currency(text: str) -> str:
    symbol = re.search(r"[$€£¥₹₦]", text)
    if symbol is not None:
        return _CURRENCIES[symbol.group(0)]
    for match in CURRENCY_WORD.finditer(text):
        return _CURRENCIES.get(match.group(1).lower(), "")
    return ""


def _principal_names(product: Product) -> tuple[str, ...]:
    """The inputs that size the problem: without one there is nothing to work."""
    return {"loan": ("amount",), "card_payoff": ("balance",), "savings": ("start", "deposit")}[
        product.family
    ]


def _values(
    product: Product, rate: float | None, amounts: list[Sum], loan: LoanSums | None
) -> dict[str, float] | None:
    """The inputs the sums give, each read from one sum; None when a slot has two."""
    values: dict[str, float] = {}
    if rate is not None:
        values["apr" if product.family == "card_payoff" else "rate"] = rate
    once = [item for item in amounts if not item.monthly and not item.income]
    monthly = {item.value for item in amounts if item.monthly}
    if loan is not None:
        slots = {"amount": {loan.amount} if loan.amount else set()}
    elif product.family == "card_payoff":
        slots = {"balance": {item.value for item in once}, "payment": monthly}
    else:
        starts = {item.value for item in once if item.start}
        slots = {"start": starts or {item.value for item in once}, "deposit": monthly}
    for name, said in slots.items():
        if len(said) > 1:
            return None
        if said and (value := said.pop()) > 0:
            values[name] = value
    return values


def _term(product: Product, text: str) -> dict[str, float] | None:
    """The term the message gives, in the product's own unit (a car loan counts months);
    {} for none, None for two ("15 or 30 years", "a 3 year or 5 year car loan").

    A length of time that is no term (an age, time gone by) is left out."""
    terms: set[tuple[tuple[str, float], ...]] = set()
    for match in TERM.finditer(text):
        before = text[max(0, match.start() - 30) : match.start()]
        if _SCALE_BEFORE.search(before):
            return None
        breaks = [end.end() for end in _CLAUSE_BREAK.finditer(text, 0, match.start())]
        clause = text[breaks[-1] if breaks else 0 : match.start()]
        if (
            _SPAN_AFTER.match(text, match.end())
            or _SPAN_BEFORE.search(before)
            or _SPENT_CLAUSE.search(clause[-200:])
        ):
            continue
        if _TERM_CHOICE.search(before):
            return None
        terms.add(tuple(term_in(product, count_value(match["n"]), match["unit"]).items()))
    if len(terms) > 1:
        return None
    return dict(terms.pop()) if terms else {}


def term_in(product: Product, number: float, unit: str) -> dict[str, float]:
    """``number`` ``unit`` ("3 years") in the product's own term unit (a car loan counts months)."""
    in_years = _TERM_UNITS.get(unit.lower()) == "years"
    if product.input("years") is not None:
        return {"years": number if in_years else number / 12}
    if product.input("months") is not None:
        return {"months": number * 12 if in_years else number}
    return {}
