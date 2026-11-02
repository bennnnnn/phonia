"""An equivalence the question states, applied to its own amounts.

"An electric motor pumps 200 liter of water to a reservoir of height 6 m in 2 s …
Take 1 liter of water = 1 kg of water." (a grade 7 physics book, 2026-10-29): the
solver needs the water's mass, and the book says what a litre of it weighs. The amount
"200 liter of water" is read as "200 kg of water", and the sentence stating the
equivalence goes, so its 1 and 1 are not read as givens.
"""

from __future__ import annotations

import re

_UNIT = r"[A-Za-z]+"
_NUMBER = r"\d+(?:\.\d+)?"
# An amount as written: "1,500", "200", ".5".
_AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"
# "Take 1 liter of water = 1 kg of water.", "1 L of water has a mass of 1 kg."
_STATED = re.compile(
    rf"(?<![\w.,])(?:take\s+|assume\s+(?:that\s+)?)?1\s*(?P<from>{_UNIT})\s+of\s+"
    rf"(?P<what>[a-z]+)\s+(?:=|is|equals|has\s+a\s+mass\s+of|weighs)\s*(?P<k>{_NUMBER})\s*"
    rf"(?P<to>{_UNIT})(?:\s+of\s+(?P=what))?\s*(?:[.;]|$)",
    re.IGNORECASE,
)


def _plural_of(unit: str) -> str:
    stem = unit.lower().removesuffix("s")
    return rf"{re.escape(stem)}s?"


def apply_stated_equivalence(text: str) -> str:
    """``text`` with its amounts of the thing in the stated unit, and that statement
    taken out; ``text`` unchanged when it states none, or the amount is not there."""
    stated = _STATED.search(text)
    if stated is None:
        return text
    rest = f"{text[: stated.start()]} {text[stated.end() :]}".strip()
    amount = re.compile(
        rf"(?<![\w.,])(?P<n>{_AMOUNT})\s*{_plural_of(stated.group('from'))}\s+of\s+"
        rf"(?={re.escape(stated.group('what'))}\b)",
        re.IGNORECASE,
    )
    factor = float(stated.group("k"))
    to = stated.group("to")
    if _known_density(stated.group("what"), stated.group("from"), factor, to):
        # Water's own density, which the solver already uses: the statement adds nothing.
        return rest if amount.search(rest) else text
    rewritten, count = amount.subn(
        lambda match: f"{float(match.group('n').replace(',', '')) * factor:.10g} {to} of ", rest
    )
    return rewritten if count else text


_LITRES = frozenset({"l", "liter", "liters", "litre", "litres"})


def _known_density(what: str, unit: str, factor: float, to: str) -> bool:
    """1 litre of water is 1 kg: what the solver takes water to weigh anyway."""
    return (
        what.lower() == "water"
        and unit.lower() in _LITRES
        and to.lower() in {"kg", "kilogram", "kilograms"}
        and factor == 1.0
    )
