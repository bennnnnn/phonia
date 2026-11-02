"""The words around a stated value, which say which input of a law it fills.

The binder (``law_binding.fit``) reads a question's values by dimension; these helpers read
the words: the phrase before a value ("from 10 m/s", "reaches 18 m/s"), the
phrase after it ("100 turns on the primary"), the asked phrase, and words
that state a value without a number ("from rest").
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.services.law_binding.spec import Binding, VariableSpec
from app.services.law_binding.units import UnitTable, unit_dimension

_SENTENCE_BREAK = re.compile(r"[.;?!](?:\s|$)")
_CONNECTOR = re.compile(
    r"[,;:]|\b(?:and|but|while|then|is|are|was|were|it|its|from|at|by|into|until)\b"
    # "50 N to the right" is the value's direction, not a link to the next one.
    r"|\bto\b(?!\s+the\s+(?:right|left)\b)"
)
# An asked phrase followed by its own value labels a given: "an acceleration of 2".
_LABELLED = re.compile(r"\S\s*(?:(?:of|=|is|:|was)\s*)?[-+]?\.?\d[\d.]*(?:[eE][-+]?\d+)?")
_CHANGE_VERBS = {
    "change": r"chang\w*",
    "increase": r"increas\w*",
    "rise": r"ris(?:e|es|en|ing)",
    "decrease": r"decreas\w*",
    "drop": r"drop(?:s|ped|ping)?",
    "fall": r"fall(?:s|en|ing)?",
}


@lru_cache(maxsize=1024)
def word_pattern(phrase: str) -> re.Pattern[str]:
    # A leading word boundary only: "climb" names "climbs", "accelerat" both forms.
    return re.compile(rf"(?<![\w]){re.escape(phrase)}")


def last_said(window: str, words: tuple[str, ...]) -> int:
    """Where the last of these words ends in the window; -1 when none is there."""
    ends = [match.end() for word in words for match in word_pattern(word).finditer(window)]
    return max(ends, default=-1)


def first_said(window: str, words: tuple[str, ...]) -> int:
    """Where the first of these words starts in the window; -1 when none is there."""
    starts = [match.start() for word in words for match in word_pattern(word).finditer(window)]
    return min(starts, default=-1)


def words_before(lower: str, start: int, end: int) -> str:
    """The words before a value, back to the previous value or sentence."""
    breaks = [match.end() for match in _SENTENCE_BREAK.finditer(lower, start, end)]
    return lower[max([start, *breaks]) : end]


def words_after(lower: str, start: int, end: int) -> str:
    """The words after a value that still describe it: "100 turns on the primary".

    They end at the sentence, the next value, or the first connector: in
    "300 K is heated to 450 K", "to" names 450 K, not 300 K.
    """
    stop = _SENTENCE_BREAK.search(lower, start, end)
    after = lower[start : stop.start() if stop is not None else end]
    link = _CONNECTOR.search(after)
    return after[: link.start()] if link is not None else after


@lru_cache(maxsize=1024)
def _asked_pattern(phrase: str) -> re.Pattern[str]:
    # Questions often put the quantity before its verb: "how much does the
    # temperature of the water increase?" A catalog ask such as "temperature
    # increase" should match that wording without treating a plain temperature
    # reading as a change.
    words = phrase.rsplit(" ", 1)
    if len(words) == 2 and (verb := _CHANGE_VERBS.get(words[1])) is not None:
        return re.compile(
            rf"(?<![\w]){re.escape(words[0])}\b[^.?!,;]{{0,80}}?\b{verb}\b",
            re.IGNORECASE,
        )
    return re.compile(rf"(?<![\w]){re.escape(phrase)}", re.IGNORECASE)


def ask_strength(
    clause: str, asks: tuple[str, ...], result: tuple[str, ...], units: UnitTable
) -> int:
    """The longest asked phrase this clause names, not counting a given's label.

    The clause keeps its case: the unit after a value is read as written ("5 mM" is a
    concentration, "5 mm" a length), and the phrase is matched without case.
    """
    strength = 0
    for phrase in asks:
        for match in _asked_pattern(phrase).finditer(clause):
            label = _LABELLED.match(clause, match.end() - 1)
            if label is None or not _labels(clause, label.end(), result, units):
                strength = max(strength, len(phrase))
    return strength


def _labels(clause: str, end: int, result: tuple[str, ...], units: UnitTable) -> bool:
    """A value right after the asked phrase is its label when it is of that kind.

    "an acceleration of 2 m/s²" states an acceleration; "the internal energy
    of 2 mol of gas" asks for an energy of an amount. A bare number labels.
    """
    unit = units.at(clause, end)
    if unit is None:
        return True
    reading = unit_dimension(unit[1])
    return reading is None or reading[0] in _result_kinds(result)


@lru_cache(maxsize=256)
def _result_kinds(result: tuple[str, ...]) -> frozenset[str]:
    readings = (unit_dimension(unit) for unit in result)
    return frozenset(reading[0] for reading in readings if reading is not None)


def choose(
    options: list[VariableSpec],
    before: str,
    after: str,
    binding: Binding,
    is_result_kind: bool,
    *,
    listed: bool = False,
) -> VariableSpec | None:
    """The input this value fills, or None when the words do not say.

    The words just before a value name it ("from 10 m/s"); when none do, the
    words just after it can ("100 turns on the primary"). In a list read
    "respectively", the words before the first value name every value, so
    only inputs the law fills in stated order can take them. An input that
    ``needs_words`` takes a value only when its words name it.
    """
    choice = _pick(options, before, after, binding, is_result_kind, listed=listed)
    if choice is not None and choice.needs_words and not _named(choice, before, after):
        return None
    return choice


def _named(variable: VariableSpec, before: str, after: str) -> bool:
    return last_said(before, variable.words) >= 0 or first_said(after, variable.words) >= 0


def _pick(
    options: list[VariableSpec],
    before: str,
    after: str,
    binding: Binding,
    is_result_kind: bool,
    *,
    listed: bool,
) -> VariableSpec | None:
    ordered = all(
        option.name in (*binding.descending, *binding.interchangeable) for option in options
    )
    if listed and len(options) > 1:
        return options[0] if ordered else None
    said = [(last_said(before, option.words), option) for option in options]
    latest = max(position for position, _ in said)
    if is_result_kind and last_said(before, binding.result_words) > latest:
        # "reaches 18 m/s" while the final speed is asked: that is the answer.
        return None
    if latest >= 0:
        named = [option for position, option in said if position == latest]
        return named[0] if len(named) == 1 else None
    if len(options) > 1:
        later = [(first_said(after, option.words), option) for option in options]
        found = [(position, option) for position, option in later if position >= 0]
        if found:
            nearest = min(position for position, _ in found)
            named = [option for position, option in found if position == nearest]
            return named[0] if len(named) == 1 else None
    if len(options) == 1 or ordered:
        return options[0]
    return None


def implied_value(variable: VariableSpec, lower: str) -> float | None:
    """A value the words state without a number: "from rest", "horizontally"."""
    for phrase, value in variable.implied:
        if word_pattern(phrase).search(lower):
            return value
    return None
