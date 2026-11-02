"""A law a model read as typed values, written back as questions the subject's binder reads.

A model can read a question in any language into a law's id and the values it states
(``Stated``: the input's name, the number, the unit as written). The binder already turns
an English question into a law it fills, converts and checks, so the read is written back
as English (``renderings``) and the subject keeps one only when its own binder reads it to
the same law and the same values (``same_values``). The binder then fills what the
question left out (g, a named planet's mass) as it does for a student's own words.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.services.law_binding.spec import Binding, FormulaSpec, VariableSpec
from app.services.law_binding.units import ANGLE, UnitTable, dimension_of, unit_dimension
from app.services.law_binding.words import word_pattern

_QUESTION_WORDS = frozenset({"how", "what", "which", "when", "where", "why"})
# The angle spellings a model may write, and the one the questions are written with.
_DEGREES = frozenset({"°", "deg", "degree", "degrees"})
_RADIANS = frozenset({"rad", "radian", "radians"})


@dataclass(frozen=True, slots=True)
class InputCard:
    """One input a reader may state: its name, symbol and SI unit ("" for a number)."""

    name: str
    symbol: str
    unit: str


@dataclass(frozen=True, slots=True)
class OpCard:
    """One law as a reader sees it: what it finds, the inputs it is given, the situation
    it needs and the words that rule it out (its binding's cues and excludes)."""

    op: str
    kind: str
    finds: str
    inputs: tuple[InputCard, ...]
    needs: tuple[str, ...] = ()
    not_for: tuple[str, ...] = ()

    def line(self) -> str:
        names = ", ".join(
            f"{card.name} ({card.symbol}{', ' + card.unit if card.unit else ''})"
            for card in self.inputs
        )
        needs = f"; only for: {' / '.join(self.needs)}" if self.needs else ""
        not_for = f"; never for: {' / '.join(self.not_for)}" if self.not_for else ""
        # "how many moles" asks by itself; "range" is a thing found.
        finds = self.finds if self.finds.split()[0] in _QUESTION_WORDS else f"the {self.finds}"
        return f"{self.op}: answers {finds}; inputs {names}{needs}{not_for}"


@dataclass(frozen=True, slots=True)
class Stated:
    """One value a reader found: the input it fills, the number, the unit it claims, and
    the message's own words that state it (``quote``)."""

    name: str
    value: float
    unit: str = ""
    quote: str = ""


def op_card(spec: FormulaSpec) -> OpCard | None:
    """The law as a reader's menu shows it; None for a law no question can bind to."""
    if spec.binding is None:
        return None
    inputs = tuple(
        InputCard(variable.name, _plain_symbol(variable.symbol), variable.dimension or "")
        for variable in spec.variables
        if variable.visible
    )
    binding = spec.binding
    return OpCard(
        spec.id, spec.kind, binding.asks[0], inputs, binding.cues[:3], binding.excludes[:4]
    )


def excluded(binding: Binding | None, lower: str) -> bool:
    """A word the law's binding excludes is in the message: the binder would refuse the
    law for the student's own words, so it refuses the read of them too."""
    return binding is not None and any(
        word_pattern(word).search(lower) for word in binding.excludes
    )


def _plain_symbol(symbol: str) -> str:
    return symbol.replace("\\", "").replace("{", "").replace("}", "") or "x"


def _is_angle(variable: VariableSpec) -> bool:
    return (variable.dimensionless and "theta" in variable.symbol) or variable.name.startswith(
        "angle"
    )


def _spelling(table: UnitTable, expression: str) -> str | None:
    """A spelling of ``expression`` the table reads: the exact one, else one of its dimension."""
    wanted = dimension_of(expression)
    nearest = None
    for spellings in (table.symbols, table.words):
        for spelling, written in spellings.items():
            if written == expression:
                return spelling
            if nearest is None and dimension_of(written) == wanted:
                nearest = spelling
    return nearest


_QUOTED_NUMBER = re.compile(r"(?<![\w.,])-?(?:\d+(?:[.,]\d+)?|[.,]\d+)")


def _ascii_digits(text: str) -> str:
    return "".join(
        str(unicodedata.digit(char)) if char.isdigit() and not char.isascii() else char
        for char in text
    )


def _quoted_unit(stated: Stated, table: UnitTable, message: str = "") -> str | None:
    """The unit the message writes right after the value its quote states, as a Pint
    expression; None when it writes none the table reads (or not in this script). The
    message is read past the quote, so a quote of the number alone ("300" of "300 cm")
    still has its unit checked."""
    quote = _ascii_digits(stated.quote)
    text = _ascii_digits(message)
    start = text.find(quote) if quote and text else -1
    if start == -1:
        text, start = quote, 0
    for number in _QUOTED_NUMBER.finditer(quote):
        try:
            seen = float(number.group(0).replace(",", "."))
        except ValueError:
            continue
        if math.isclose(seen, stated.value, rel_tol=1e-9, abs_tol=1e-12):
            found = table.at(text, start + number.end())
            return None if found is None else found[1]
    return None


def _same_scale(first: str, second: str) -> bool:
    one, two = unit_dimension(first), unit_dimension(second)
    if one is None or two is None:
        return False
    return (
        one[0] == two[0]
        and math.isclose(one[1], two[1], rel_tol=1e-9)
        and math.isclose(one[2], two[2], abs_tol=1e-9)
    )


def written(
    stated: Stated, variable: VariableSpec, table: UnitTable, message: str = ""
) -> tuple[float, str] | None:
    """The value and a unit spelling the table reads, for one stated value; None when
    the unit is not one of the input's kind, or not the unit its quote writes ("8 cm"
    read as 8 m)."""
    unit = stated.unit.strip()
    if _is_angle(variable):
        if unit in _DEGREES or (not unit and abs(stated.value) > 2 * math.pi):
            return stated.value, "°"
        if unit in _RADIANS:
            return math.degrees(stated.value), "°"
        return (stated.value, "°") if not unit else None
    if variable.dimensionless:
        return (stated.value, "") if not unit else None
    if variable.dimension is None:
        return None
    expression = table.expression(unit) if unit else None
    if expression is None:
        expression = unit
    quoted = _quoted_unit(stated, table, message) if stated.quote else None
    if quoted is not None and not (expression and _same_scale(quoted, expression)):
        return None
    reading = unit_dimension(expression) if expression else None
    wanted = unit_dimension(variable.dimension)
    if reading is None or wanted is None or reading[0] != wanted[0] or reading[0] == ANGLE:
        return None
    if table.expression(unit) is not None:
        return stated.value, unit
    # A unit Pint reads that the table does not spell: write it in the input's own unit.
    si = stated.value * reading[1] + reading[2]
    spelling = _spelling(table, variable.dimension)
    if spelling is None:
        return None
    return (si - wanted[2]) / wanted[1], spelling


def renderings(
    spec: FormulaSpec, values: Mapping[str, tuple[float, str]], *, about: str = ""
) -> Iterator[str]:
    """English questions stating ``values`` and asking for the law's result, plainest
    first. ``about`` names what the question is about ("of HCl")."""
    binding = spec.binding
    if binding is None:
        return
    variables = {variable.name: variable for variable in spec.variables}
    asks = binding.asks[0]
    # "how far" asks by itself; "range" is asked for.
    ask = (
        f"{asks[0].upper()}{asks[1:]}{about}?"
        if asks.split()[0] in _QUESTION_WORDS
        else f"What is the {asks}{about}?"
    )
    # The situation a law needs and the numbers cannot show ("pulley", "half-life").
    situations = [f" {cue}" for cue in binding.cues[:1]] or [""]

    def stated(label: str, name: str) -> str:
        number, unit = values[name]
        return f"{label} {_number(number)}{'' if unit in ('', '°') else ' '}{unit}".rstrip()

    def by_words(name: str) -> str:
        words = variables[name].words
        return words[0] if words else name.replace("_", " ")

    def by_symbol(name: str) -> str:
        return f"{_plain_symbol(variables[name].symbol)} ="

    names = [variable.name for variable in spec.variables if variable.name in values]
    for label in (by_words, by_symbol):
        givens = ", ".join(stated(label(name), name) for name in names)
        for situation in situations:
            yield f"{ask[:-1]}{situation}? Given: {givens}."
            yield f"In this{situation} problem, {givens}. {ask}"


def _number(value: float) -> str:
    return f"{value:.12g}"


def same_values(
    bound: Mapping[str, float],
    values: Mapping[str, tuple[float, str]],
    table: UnitTable,
    spec: FormulaSpec,
) -> bool:
    """The binder filled every rendered value as written: its SI value, or for an angle
    or a number, the number itself (or in radians). Inputs the law fills in its own order
    (the heavier Atwood mass first) match as a set."""
    by_name = {variable.name: variable for variable in spec.variables}
    binding = spec.binding
    pooled = set(binding.descending) | set(binding.interchangeable) if binding else set()
    for name, (number, unit) in values.items():
        names = sorted(pooled & set(values)) if name in pooled else [name]
        if any(other not in bound for other in names):
            return False
        if not any(_fills(bound[other], number, unit, table, by_name[name]) for other in names):
            return False
    return True


def _fills(got: float, number: float, unit: str, table: UnitTable, variable: VariableSpec) -> bool:
    """``got`` is ``number`` in ``unit`` as the binder keeps it."""
    if unit in ("", "°"):
        candidates: tuple[float, ...] = (number, math.radians(number))
    else:
        reading = unit_dimension(table.expression(unit) or unit)
        if reading is None or variable.dimension is None:
            return False
        si = number * reading[1] + reading[2]
        wanted = unit_dimension(variable.dimension)
        # The binder keeps a value as written and its unit beside it, or in SI.
        candidates = (number, si, si if wanted is None else (si - wanted[2]) / wanted[1])
    return any(math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-12) for want in candidates)
