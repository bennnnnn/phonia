"""The pieces every money reader shares: a percent, a length of time, a sum and its currency.

``read`` (a first ask), ``change_line`` (a follow-up) and ``purchase`` (a loan told over two
lines) read these the same way, so "seven years" is a term in all three.
"""

from __future__ import annotations

import re

from app.services.number_text import NUMBER_WORDS, count_word_pattern

# A count in words, as a book writes a term: "seven", "twenty-five", "two and a half",
# "one hundred twenty" (read whole: "twenty" alone of "one hundred twenty months" was a
# 20-month car loan, 2026-11-01).
_TENS = "|".join(word for word, value in NUMBER_WORDS.items() if value >= 20)
_ONES = count_word_pattern(low=1, high=9)
_BELOW_HUNDRED = rf"(?:(?:{_TENS})(?:[\s-](?:{_ONES}))?|{count_word_pattern(low=1, high=19)})"
_SPELLED = (
    rf"(?:(?:a|{_ONES})\shundred(?:\s(?:and\s)?{_BELOW_HUNDRED})?|{_BELOW_HUNDRED})"
    r"(?:\sand\sa\shalf)?"
)
# A decimal comma is a decimal point ("3,5%" is 3.5). It starts at no digit, decimal point
# or a digit's comma, so "3,5%" is never read as "5%" (2026-11-01: a 5% mortgage worked from
# "3,5%"), and "3%,4%" is two rates.
PERCENT = r"(?<![\d.])(?<!\d,)(?P<pct>\d{1,3}(?:[.,]\d{1,4})?)\s?(?:%|percent\b|per\s?cent\b|pct\b)"
# A length of time; its count is ``count_value``'s.
DURATION = (
    rf"(?P<n>\d{{1,3}}(?:\.\d{{1,2}})?|{_SPELLED})\s?-?\s?(?P<unit>years?|yrs?|months?|mos?)\b"
)
RATE = re.compile(PERCENT, re.I)
TERM = re.compile(rf"\b{DURATION}", re.I)
_SCALE = r"(?:k|m|thousand|million|mil|grand)\b"
# A sum's digits in every grouping people write: "250,000.50", "5,00,000" (lakh),
# "250.000,50" (a dot between thousands, a comma before the cents), "250000".
_US = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"
_LAKH = r"\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d{1,2})?"
_DOTTED = rf"\d{{1,3}}(?:\.\d{{3}})+(?:,\d{{1,2}})?(?!\s?{_SCALE})"
AMOUNT = re.compile(
    rf"(?P<sym>[$€£¥₹₦])?\s?(?P<num>{_US}|{_LAKH}|{_DOTTED}|\d+(?:\.\d{{1,2}})?)"
    rf"(?:\s?(?P<mult>{_SCALE}))?",
    re.I,
)
# Digits left over after a sum: "25.000" read as 25.00 and a 0, "5,00,000" as 5.
UNREAD_DIGITS = re.compile(r"[.,]?\d")
MULTIPLIERS = {"k": 1e3, "thousand": 1e3, "grand": 1e3, "m": 1e6, "million": 1e6, "mil": 1e6}
CURRENCY_WORDS = (
    r"dollars?|bucks|usd|euros?|eur|pounds?|gbp|birr|etb|rupees?|inr|naira|ngn|"
    r"shillings?|kes|yen|jpy|cad|aud"
)
CURRENCY_WORD = re.compile(rf"\s?({CURRENCY_WORDS})\b", re.I)


def sum_phrase(name: str) -> str:
    """A sum as a phrase in a lower-cased line ("$20k", "3 grand"), read by ``read_sum``."""
    return (
        rf"(?P<{name}>[$€£¥₹₦]?\s?\d[\d,]*(?:\.\d{{1,2}})?"
        rf"(?:\s?(?:k|m|thousand|million|mil|grand))?(?:\s(?:{CURRENCY_WORDS}))?)"
    )


def grouped(num: str) -> bool:
    """The digits are grouped as money is written ("250,000", "250.000", "5,00,000")."""
    return "," in num or re.fullmatch(_DOTTED, num) is not None


def amount_value(num: str) -> float:
    """The ``num`` group of ``AMOUNT`` as a number, in the grouping it was written in."""
    if re.fullmatch(_DOTTED, num):
        return float(num.replace(".", "").replace(",", "."))
    return float(num.replace(",", ""))


def percent_value(text: str) -> float | None:
    """A percent's number ("3.5", "3,5"); None when a comma may mark thousands ("3,125" is
    3.125 or 3125) and the reader cannot tell which."""
    whole, comma, fraction = text.partition(",")
    if not comma:
        return float(text)
    return None if len(fraction) == 3 else float(f"{whole}.{fraction}")


def count_value(text: str) -> float:
    """A duration's count, in digits or words: "3.5", "seven", "twenty-five", "two and a half",
    "a hundred and eighty"."""
    words = text.lower().replace("-", " ").split()
    if not words or (words[0] not in NUMBER_WORDS and words[:2] != ["a", "hundred"]):
        return float(text)
    half = words[-3:] == ["and", "a", "half"]
    words = words[: -3 if half else None]
    hundreds = 0
    if "hundred" in words:
        head = words[: words.index("hundred")]
        hundreds = 100 * (1 if head == ["a"] else sum(NUMBER_WORDS[word] for word in head))
        words = [word for word in words[words.index("hundred") + 1 :] if word != "and"]
    return hundreds + sum(NUMBER_WORDS[word] for word in words) + 0.5 * half
