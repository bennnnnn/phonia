"""Every sum of money in a request, with what its neighbours say it is.

"Borrow 20k" is borrowed, "costs 250,000" a price, "50,000 which he will use as a deposit"
money down, "200 a month" monthly, "my salary is 90,000" an income. ``loan_sums`` decides
from these which sum a loan is. Some numbers next to a currency are no sum at all: an
exchange rate ("USD 1 = ETB 57", "57 birr to the dollar"), a note or coin ("Birr 500
notes"), the same sum said again in another currency ("that's about USD 21,600") or a
plan's name ("my 401k").

A sum is read whole or not at all: digits left over ("25.000" read as 25.00) mean the
message holds a sum the reader cannot read, and ``amounts`` gives None: no numbers are
worked from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.money.phrases import (
    AMOUNT,
    CURRENCY_WORD,
    CURRENCY_WORDS,
    MULTIPLIERS,
    RATE,
    TERM,
    UNREAD_DIGITS,
    amount_value,
    grouped,
)


@dataclass(frozen=True)
class Sum:
    """One sum of money in a request, with what its neighbours say it is."""

    value: float
    monthly: bool
    down: bool
    start: bool
    # Named as a loan ("car loan 25000", "a 300k mortgage", "loan of 20000").
    loan: bool = False
    # Said to be borrowed or owed ("borrow 20k", "still owe 20k"): the loan as it stands.
    borrowed: bool = False
    # Said to be what the thing costs ("costs 250,000", "a 400k house").
    price: bool = False
    # Said to be paid toward it ("she pays 5,000", "we put in 80k", "has saved 50,000").
    paid: bool = False
    # An income ("my salary is 90,000", "I make 80k a year"): never a loan.
    income: bool = False
    # Paid each week, fortnight, day or quarter: no product works it ("$200 a week").
    other_period: bool = False


# "200 at the end of each month" is a monthly deposit too: the one the savings formula pays
# in. Paid at a month's start it earns a month more, which no product works, so it is
# another period (2026-11-01: "at the end of each month" read as one $200 lump sum).
_MONTHLY = re.compile(
    r"\s?(?:at\s+the\s+end\s+of\s+)?(?:a|per|/|each|every)\s?(?:month|mo)\b|\s?monthly\b"
    r"|\s?/\s?mo\b",
    re.I,
)
_OTHER_PERIOD = re.compile(
    r"\s?(?:a|per|/|each|every)\s?(?:week|wk|fortnight|day|quarter)\b"
    r"|\s?(?:weekly|bi-?weekly|fortnightly|daily|quarterly)\b"
    r"|\s?at\s+the\s+(?:start|beginning)\s+of\s+(?:each|every)\s+month\b",
    re.I,
)
_DOWN = re.compile(r"\b(?:down\s?payment(?:\s(?:of|is))?|put(?:ting)?\s(?:down)?|down)\s?$", re.I)
_DOWN_AFTER = re.compile(r"\s?(?:down\b|as\s(?:a\s)?down\s?payment\b)", re.I)
# A sum put toward the price in a clause after it: "50,000 which he will use as a deposit",
# "50k as the down payment". A loan's deposit is its down payment; a deposit with a
# landlord, a bank or a booking is not.
_DOWN_CLAUSE = re.compile(
    r"[^\d.;!?]{0,40}?\bas\s(?:a|an|the|his|her|their|my|our|your)\s(?:deposit|down\s?payment)\b",
    re.I,
)
_NOT_PURCHASE = re.compile(
    r"\b(?:landlord|rent\w*|lease|leasing|security|bank|account|utilit\w+|hotel|booking)\b", re.I
)
# A bare number is money only after a word that says so ("borrow 25000", "balance is 4000");
# "rates in 2026" has no sum in it.
_MONEY_BEFORE = re.compile(
    r"\b(?:for|of|borrow(?:ing)?|owe|balance(?:\sis)?|loan|price(?:d)?|costs?|worth|save|"
    r"saving|deposit(?:ing)?|invest(?:ing)?|pay(?:ing)?|put|with|is)\s?$",
    re.I,
)
_START = re.compile(
    r"\b(?:start(?:ing)?\s(?:with|at)|have|initial(?:ly)?|already|lump\s?sum(?:\sof)?|"
    r"currently|right\snow)\s?$",
    re.I,
)
# "a 250000 mortgage": a bare number right before what it buys is its price.
_PRODUCT_AFTER = re.compile(r"\s?(?:mortgage|house|home|condo|car|loan|balance)\b", re.I)
_LOAN_BEFORE = re.compile(
    r"\b(?:loan(?:\samount)?|mortgage|financ(?:e|es|ed|ing))(?:\s(?:of|is))?\s?$", re.I
)
_LOAN_AFTER = re.compile(
    r"\s?(?:(?:car|auto|home|house|student|personal|business|bank)\s)?(?:loan|mortgage)\b", re.I
)
_BORROWED_BEFORE = re.compile(r"\b(?:borrow(?:s|ed|ing)?|owe[sd]?|owing)(?:\sup\sto)?\s?$", re.I)
_PRICE_BEFORE = re.compile(
    r"\b(?:costs?|costing|priced\sat|price(?:\s(?:of|is|tag\sof))?|worth|sells?\sfor|"
    r"selling\sfor|valued\sat)\s?$",
    re.I,
)
_GOODS_AFTER = re.compile(r"\s?(?:house|home|condo|car|truck|suv|vehicle|apartment|flat)\b", re.I)
_PAID_BEFORE = re.compile(
    r"\b(?:pays?|paid|paying|put(?:s|ting)?\sin|saved(?:\sup)?|has|have|had|contribut\w+|"
    r"brings?|bringing|uses?|using)\s?$",
    re.I,
)
_INCOME_BEFORE = re.compile(
    r"\b(?:salary|income|earn(?:s|ed|ing)?|make|makes|making|wages?|take[\s-]home(?:\spay)?|"
    r"gross|net\spay)(?:\s(?:is|of|was|about|around))?\s?$",
    re.I,
)
_INCOME_AFTER = re.compile(
    r"\s?(?:(?:a|per)\s(?:year|yr|week|hour)\b|/\s?(?:yr|year|hr|hour)\b|annually\b|yearly\b|"
    r"salary\b|income\b)",
    re.I,
)
# No sum: the same sum again in another currency, an exchange rate, a note or a coin.
_RESTATED_BEFORE = re.compile(
    r"\b(?:that['\u2019]?s|that\sis|which\sis|i\.e\.?)\s(?:(?:about|around|roughly|approximately|"
    r"approx\.?|nearly|almost)\s)?$",
    re.I,
)
_EXCHANGE_BEFORE = re.compile(r"=\s*$|\bexchange\srate(?:\s(?:is|of))?\s?$", re.I)
_EXCHANGE_AFTER = re.compile(
    rf"\s*=|\s(?:to|per|for)\s(?:the\s|one\s|a\s|1\s)?(?:{CURRENCY_WORDS})\b", re.I
)
_DENOMINATION_AFTER = re.compile(r"\s?(?:notes?|bills?|coins?|banknotes?|denominations?)\b", re.I)
# A scale word the reader has no number for: "5 lakh", "2 crore", "1.2 billion".
_UNREAD_SCALE = re.compile(r"\s?(?:lakhs?|lacs?|crores?|billions?|bn|trillions?|hundred)\b", re.I)
# A retirement or college plan's name: "401k", "403(b)", "457b", "a 529 plan".
_PLAN = re.compile(r"(?:401|403|457)\s?\(?[kb]\)?(?!\w)|529\s(?:plan|account|savings)\b", re.I)
# A currency named before its sum, as many countries write it: "Birr 3,000", "USD 500".
_CURRENCY_BEFORE = re.compile(rf"\b(?:{CURRENCY_WORDS})\s?$", re.I)

# What follows an "m" or "k" that makes it a unit: "6m/s2", "5 m²", "3 km".
_UNIT_AFTER_LETTER = re.compile(r"[/^²³\d]")
# A physical measurement: "1500 kg", "6 m/s2", "20 N". Units are case-sensitive.
# A bare "m" is metres only apart from its number: "1.2m" is a sum, "500 m" a distance.
MEASUREMENT = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?(?:\s?(?:kg|mg|g|m/s(?:\^?2|²)?|km/h|kmh|mph|kN|N|kJ|J|kW|W|Pa|Hz|"
    r"cm|mm|km)|\s+m)(?![\w/])"
)
# Money named outright: a currency, a percent, or a word only money uses. "Rate" and
# "payment" are physics words too.
SAYS_MONEY = re.compile(
    rf"[$€£¥₹₦%]|\b(?:{CURRENCY_WORDS}|percent|apr|loans?|mortgages?|borrow\w*|owe[sd]?|"
    r"balance|credit\s+card|deposit\w*|invest\w*)\b",
    re.I,
)


def amounts(text: str) -> list[Sum] | None:
    """Every sum of money in the message, in order, with what its neighbours say it is;
    None when one of them cannot be read whole."""
    found: list[Sum] = []
    for match in AMOUNT.finditer(text):
        start = match.start("num")
        if RATE.match(text, start) or TERM.match(text, start) or _PLAN.match(text, start):
            continue
        word = CURRENCY_WORD.match(text, match.end())
        end = word.end() if word else match.end()
        rest, clause = text[end : end + 24], text[end : end + 64]
        at = match.start("sym") if match.group("sym") else match.start("num")
        lead = text[max(0, at - 40) : at]
        named = None if match.group("sym") else _CURRENCY_BEFORE.search(lead)
        before = (lead[: named.start()] if named else lead)[-24:]
        marked = bool(
            match.group("sym")
            or match.group("mult")
            or word
            or named
            or grouped(match["num"])
            or _PRODUCT_AFTER.match(rest)
            or _MONTHLY.match(rest)
        )
        if not marked and _MONEY_BEFORE.search(before) is None:
            continue
        if match.group("mult") and not _is_multiplier(text, match):
            # "6m/s2", "20 m/s": a measurement, never 6 million.
            continue
        if _no_sum(before, rest):
            continue
        if match.group("mult") is None and (
            UNREAD_DIGITS.match(text, match.end("num")) or _UNREAD_SCALE.match(text, end)
        ):
            return None
        number = amount_value(match["num"])
        if match.group("mult"):
            number *= MULTIPLIERS[match["mult"].lower()]
        found.append(_sum(number, before, rest, clause, lead))
    return found


def _no_sum(before: str, rest: str) -> bool:
    return bool(
        _RESTATED_BEFORE.search(before)
        or _EXCHANGE_BEFORE.search(before)
        or _EXCHANGE_AFTER.match(rest)
        or _DENOMINATION_AFTER.match(rest)
    )


def _sum(value: float, before: str, rest: str, clause: str, lead: str) -> Sum:
    deposit = _DOWN_CLAUSE.match(clause)
    return Sum(
        value=value,
        monthly=_MONTHLY.match(clause) is not None,
        down=_DOWN.search(before) is not None
        or _DOWN_AFTER.match(rest) is not None
        or (deposit is not None and not _NOT_PURCHASE.search(lead + deposit.group(0))),
        start=_START.search(before) is not None,
        loan=_LOAN_BEFORE.search(before) is not None or _LOAN_AFTER.match(rest) is not None,
        borrowed=_BORROWED_BEFORE.search(before) is not None,
        price=_PRICE_BEFORE.search(before) is not None or _GOODS_AFTER.match(rest) is not None,
        paid=_PAID_BEFORE.search(before) is not None,
        income=_INCOME_BEFORE.search(before) is not None or _INCOME_AFTER.match(rest) is not None,
        other_period=_OTHER_PERIOD.match(clause) is not None,
    )


def _is_multiplier(text: str, match: re.Match[str]) -> bool:
    """An "m" is millions written with the number ("$1.2 m", "a 1.2m house", "2 m birr"),
    not a unit: "6m/s2" and "500 m" are measurements. A "k" alone is never a unit."""
    if match["mult"].lower() != "m":
        return True
    if _UNIT_AFTER_LETTER.match(text, match.end("mult")):
        return False
    attached = match.start("mult") == match.end("num")
    return (
        attached
        or match.group("sym") is not None
        or CURRENCY_WORD.match(text, match.end("mult")) is not None
        # "borrow 2 m for a house": a loan word, and no measurement beside it.
        or (
            SAYS_MONEY.search(text) is not None
            and MEASUREMENT.search(f"{text[: match.start()]} {text[match.end() :]}") is None
        )
    )
