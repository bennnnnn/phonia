"""What the server checks in a model's read before any binder sees it.

A read names values; each must be the question's own: its quote appears in the message,
its number is written in that quote, and every number the message states is quoted by
some given or listed as unused, so a value the model dropped or invented never reaches a
solver. Text is compared after every Unicode digit is read as its ASCII digit (Arabic-
Indic, Devanagari, full-width) and a superscript power is written as ``^``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable

from app.modules.model_reader.schemas import LawRead, Reason

_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_SUPERSCRIPT_RUN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+")
_SPACE = re.compile(r"\s+")
# One number as written: "3", "3.5", "3,5", ".5", "-2". A digit right after a letter belongs to
# a name ("H2O", "v0", "m1"), and one after "^" is a power ("m/s^2"), not a stated value.
_NUMBER = re.compile(r"(?<![A-Za-z\d.,^])-?(?:\d+(?:[.,]\d+)*|[.,]\d+)")
# "3 x 10^8" (a times sign or an x), "3*10^8", "3e8": one value.
_POWER = re.compile(r"(-?\d+(?:[.,]\d+)?)\s?(?:[\u00d7x*\u00b7]\s?10\^|e)(-?\d+)", re.IGNORECASE)


def normalized(text: str) -> str:
    """``text`` with every digit ASCII, superscript powers as ``^n``, spaces single, and
    lowercase."""
    text = _SUPERSCRIPT_RUN.sub(lambda run: "^" + run.group(0).translate(_SUPERSCRIPTS), text)
    digits = "".join(
        str(unicodedata.digit(char)) if char.isdigit() and not char.isascii() else char
        for char in text
    )
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", digits)).strip().lower()


def _readings(number: str) -> set[float]:
    """The values one written number may mean: "3,5" is 3.5 or 35; "3,000" is 3000."""
    found: set[float] = set()
    plain = number.replace(",", "")
    for candidate in {plain, number.replace(",", "."), number.replace(".", "").replace(",", ".")}:
        try:
            found.add(float(candidate))
        except ValueError:
            continue
    return found


def values_in(quote: str) -> set[float]:
    """Every value ``quote`` writes, powers of ten included."""
    found: set[float] = set()
    for power in _POWER.finditer(quote):
        for mantissa in _readings(power.group(1)):
            found.add(mantissa * 10 ** int(power.group(2)))
    for number in _NUMBER.finditer(quote):
        found |= _readings(number.group(0))
    return found


def _written_in(value: float, quote: str) -> bool:
    return any(math.isclose(value, seen, rel_tol=1e-9, abs_tol=1e-12) for seen in values_in(quote))


def _numbers_written(quote: str) -> int:
    """How many values ``quote`` writes: "3 x 10^8 m/s" is one."""
    powers = len(_POWER.findall(quote))
    return powers + len(_NUMBER.findall(_POWER.sub(" ", quote)))


def _own_spans(text: str, quotes: list[str]) -> list[tuple[int, int]] | None:
    """A place in the message for each quote, no two overlapping; None when the quotes
    share words (two values read from one stretch of the message)."""
    taken: list[tuple[int, int]] = []
    for quote in quotes:
        start = text.find(quote)
        while start != -1 and any(
            start < end and begin < start + len(quote) for begin, end in taken
        ):
            start = text.find(quote, start + 1)
        if start == -1:
            return None
        taken.append((start, start + len(quote)))
    return taken


def _covered(text: str, quotes: Iterable[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for quote in quotes:
        if not quote:
            continue
        start = text.find(quote)
        while start != -1:
            spans.append((start, start + len(quote)))
            start = text.find(quote, start + 1)
    return spans


def check_read(message: str, read: LawRead) -> Reason:
    """``ok``, or the first thing that makes the read the model's, not the message's."""
    text = normalized(message)
    givens = [(given, normalized(given.quote)) for given in read.givens]
    unused = [normalized(quote) for quote in read.unused]
    for given, quote in givens:
        if not quote or quote not in text:
            return "quote_missing"
        if not _written_in(given.value, quote):
            return "value_not_in_quote"
        # One value per quote, each from its own words: a quote of the whole message lets
        # any value fill any input.
        if _numbers_written(quote) != 1:
            return "quote_not_one_value"
    if _own_spans(text, [quote for _, quote in givens]) is None:
        return "quotes_overlap"
    if any(quote and quote not in text for quote in unused):
        return "quote_missing"
    spans = _covered(text, [quote for _, quote in givens] + unused)
    for number in _NUMBER.finditer(text):
        if not any(start <= number.start() and number.end() <= end for start, end in spans):
            return "number_unaccounted"
    return "ok"
