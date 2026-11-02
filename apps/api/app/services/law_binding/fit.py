"""Fill one catalog law from a question's stated values and words.

A subject's binder finds the laws whose ``Binding`` names what a question asks, then asks
this module to fill each one:

- every stated value fills one input of its dimension. Two inputs of one
  dimension are told apart by the word just before the value ("from", "to",
  "initial", "reaches") or just after it ("on the primary"), or filled in
  order (largest first where the law says so);
- a value the words mark as the result itself ("reaches 18 m/s" when the
  final speed is asked) means this is not the law;
- unstated inputs come from phrases ("from rest" is u = 0) or from the subject's
  settings (g, the named planet's mass);
- the filled inputs must be exactly a set the solver answers from.

Anything short of one way to fill the law declines: a value has no input, or an input
could take either of two values.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.services.law_binding.givens import Given, scan_givens
from app.services.law_binding.spec import Binding, FormulaSpec, VariableSpec
from app.services.law_binding.units import ANGLE, UnitTable, dimension_of, unit_dimension
from app.services.law_binding.words import (
    ask_strength,
    choose,
    implied_value,
    last_said,
    word_pattern,
    words_after,
    words_before,
)

_DIMENSIONLESS = "dimensionless"
_ANGULAR = "angular "
# "from 0 to 27 m/s": a bare number shares the unit of the value it runs to.
_RANGE_LINK = re.compile(r"\d\s*(?:to|-|\u2013|and|or)\s*", re.IGNORECASE)
# Only a conjunction between two values: they share the words before the first.
_LIST_LINK = re.compile(r"\s*(?:,|and|,\s*and)\s*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Subject:
    """What one subject brings to the binder."""

    units: UnitTable
    # The value an unstated input takes: (variable, text, lower text) -> value or None.
    fallback: Callable[[VariableSpec, str, str], float | None]
    # The unit an implied or fallback value is written in.
    unit_of: Callable[[VariableSpec], str]


@dataclass(frozen=True, slots=True)
class Question:
    """A question as the binder reads it."""

    text: str
    lower: str
    givens: tuple[Given, ...]
    # Dimensions the asked clause names, and the dimension of a unit it asks in.
    asked: frozenset[str]
    asked_in: str | None
    # Where the asked clause starts in ``lower``.
    asked_from: int


@dataclass(frozen=True, slots=True)
class Fit:
    spec: FormulaSpec
    params: dict[str, float]
    units: dict[str, str]
    strength: int


# "$0.15 per kWh" is a price. No law takes one, so it is not a value to
# account for: a question that asks the cost still declines on its ask.
_PRICE = re.compile(r"(?:[$€£¥]|\bcosts?|\bprice(?:\s+of)?|\bpays?|\bcharges)\s*$", re.IGNORECASE)


def read_givens(text: str, units: UnitTable) -> tuple[Given, ...]:
    """Stated values, a bare number taking the unit of the range it starts."""
    givens = [
        given
        for given in scan_givens(text, units)
        if given.unit or not _PRICE.search(text, 0, given.start)
    ]
    read: list[Given] = []
    for index, given in enumerate(givens):
        following = givens[index + 1] if index + 1 < len(givens) else None
        if (
            given.dimension is None
            and not given.unit
            and following is not None
            and following.dimension is not None
            and _RANGE_LINK.fullmatch(text, given.end - 1, following.start)
        ):
            reading = unit_dimension(units.expression(following.unit) or "")
            if reading is not None:
                dimension, scale, offset = reading
                si = given.value * scale + offset
                given = Given(given.start, given.end, given.value, following.unit, dimension, si)
        read.append(given)
    return tuple(read)


def _variable_kind(variable: VariableSpec) -> str | None:
    if variable.name.startswith("angle"):
        return ANGLE
    if variable.dimensionless:
        return _DIMENSIONLESS
    kind = dimension_of(variable.dimension or "")
    return _ANGULAR + kind if kind and _angular(variable.dimension or "") else kind


def _given_dimension(given: Given) -> str | None:
    if given.dimension is not None:
        return given.dimension
    return _DIMENSIONLESS if not given.unit else None


def _given_kind(given: Given, units: UnitTable) -> str | None:
    """The input kind a value can fill: its dimension, with angular rates apart.

    A frequency in Hz and an angular velocity in rad/s share a dimension, but
    50 Hz is not 50 rad/s: each fills only its own kind of input.
    """
    dimension = _given_dimension(given)
    if dimension is not None and _angular(units.expression(given.unit) or ""):
        return _ANGULAR + dimension
    return dimension


def _angular(expression: str) -> bool:
    return expression.startswith(("radian /", "revolution /"))


def _other_sense(question: Question, asks: tuple[str, ...], produced: set[str | None]) -> bool:
    """The asked word labels a value of another kind: "my weight is 70 kg".

    That question uses the word in its everyday sense (a mass), and the law's
    sense (a force) would answer something it did not ask.
    """
    lower = question.lower
    for given in question.givens:
        kind = _given_dimension(given)
        if kind is None or kind in produced:
            continue
        before = lower[max(0, given.start - 40) : given.start]
        # In the asked clause "of" is belonging, not a value: "find the
        # internal energy of 2 mol of gas" asks for the energy of the gas.
        links = r"(?:=|is|:|was)?" if given.start >= question.asked_from else r"(?:of|=|is|:|was)?"
        for phrase in asks:
            # "specific heat of 900 J/kg/K" names the capacity. The short ask
            # "heat" is the end of that label, not the heat the question asks for.
            # "to heat 1.5 kg of water" is the verb, and labels nothing.
            label = re.search(rf"(?<!specific )(?<!\bto ){re.escape(phrase)}\s*{links}\s*$", before)
            if label is None:
                continue
            # "the electric field 0.2 m from a charge" places the field; it
            # does not label it. Only a bare value can be read that way.
            if not label.group().rstrip().endswith(phrase) or not _PLACED.match(
                lower, value_end(lower, given)
            ):
                return True
    return False


# "the absolute pressure 50 m deep" places the pressure too.
_PLACED = re.compile(
    r"\s*(?:away\s+)?(?:from|above|below|beyond|behind|away|deep|down|under|underwater|beneath)\b"
)


def value_end(lower: str, given: Given) -> int:
    """Where a value's text ends: after its unit ("100 kPa"), not its number."""
    unit = given.unit.lower()
    for at in (given.end, given.end + 1):
        if unit and lower.startswith(unit, at):
            return at + len(unit)
    return given.end


def largest_first(
    params: dict[str, float], units: dict[str, str], names: tuple[str, ...], table: UnitTable
) -> None:
    """Refill a symmetric pair largest first: the heavier Atwood mass is m₁.

    Values are compared in SI and move with their units: 5 kg outweighs 3000 g.
    """
    present = [name for name in names if name in params]
    pairs = sorted(
        ((params[name], units[name]) for name in present),
        key=lambda pair: _in_si(pair[0], pair[1], table),
        reverse=True,
    )
    for name, (value, unit) in zip(present, pairs, strict=True):
        params[name] = value
        units[name] = unit


def _in_si(value: float, unit: str, table: UnitTable) -> float:
    reading = unit_dimension(table.expression(unit) or "") if unit else None
    return value if reading is None else value * reading[1] + reading[2]


def fit(spec: FormulaSpec, strength: int, question: Question, subject: Subject) -> Fit | None:
    """This law filled from the question, or None when it does not fit exactly one way."""
    binding = spec.binding
    if binding is None:
        return None
    produced = {dimension_of(unit) for unit in binding.result}
    asked, asked_in = question.asked, question.asked_in
    if (asked and not asked <= produced) or (asked_in is not None and asked_in not in produced):
        return None
    if _other_sense(question, binding.asks, produced):
        return None
    lower, givens = question.lower, question.givens
    variables = [variable for variable in spec.variables if variable.visible]
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    # What the words state comes first: a car that starts "from rest" has u = 0,
    # so its one stated speed is the final one. Hidden classifier inputs are
    # words too: "string" sets the mode factor of a resonance.
    for variable in spec.variables:
        implied = implied_value(variable, lower)
        if implied is not None:
            params[variable.name] = implied
            units[variable.name] = subject.unit_of(variable)
    listed = word_pattern("respectively").search(lower) is not None
    previous = 0
    earlier = ""
    for index, given in enumerate(givens):
        kind = _given_kind(given, subject.units)
        options = [
            variable
            for variable in variables
            if variable.name not in params and kind is not None and _variable_kind(variable) == kind
        ]
        if not options:
            return None
        before = words_before(lower, previous, given.start)
        # "at 100 kPa and 300 K": the words before a list name every value in it.
        if _LIST_LINK.fullmatch(before):
            before = earlier
        earlier = before
        following = givens[index + 1].start if index + 1 < len(givens) else len(lower)
        after = words_after(lower, given.end, following)
        choice = choose(
            options, before, after, binding, _given_dimension(given) in produced, listed=listed
        )
        if choice is None:
            return None
        negative = last_said(before, choice.negating) >= 0
        params[choice.name] = -given.value if negative else given.value
        units[choice.name] = given.unit
        previous = value_end(lower, given)
    largest_first(params, units, binding.descending, subject.units)
    for variable in variables:
        if variable.name in params:
            continue
        value = subject.fallback(variable, question.text, lower)
        if value is not None:
            params[variable.name] = value
            units[variable.name] = subject.unit_of(variable)
    if frozenset(params) not in binding.inputs:
        return None
    return Fit(spec, params, units, strength)


def named_strength(
    binding: Binding, clause: str, lower: str, units: UnitTable, *, cue_text: str | None = None
) -> int:
    """How strongly the asked clause names this law; 0 when its cues or excludes rule it out.

    The word checks run before any unit is read, so a question that names no law's ask
    costs a few regex searches. ``cue_text`` is ``lower`` with any phrase the subject
    reads a cue from added.
    """
    cues = lower if cue_text is None else cue_text
    if binding.cues and not any(word_pattern(cue).search(cues) for cue in binding.cues):
        return 0
    if any(word_pattern(word).search(lower) for word in binding.excludes):
        return 0
    return ask_strength(clause, binding.asks, binding.result, units)


def read_question(
    text: str,
    clause: str,
    units: UnitTable,
    *,
    max_givens: int,
    asked: frozenset[str] = frozenset(),
    asked_in: str | None = None,
) -> Question | None:
    """The question as the binder reads it, or None when it states too many values.

    A school question states a handful of values; a paste full of numbers is not one
    law's inputs.
    """
    givens = read_givens(text, units)
    if len(givens) > max_givens:
        return None
    lower = text.lower()
    return Question(
        text=text,
        lower=lower,
        givens=givens,
        asked=asked,
        asked_in=asked_in,
        asked_from=lower.rfind(clause.lower()),
    )


def only_strongest_fit[K](
    named: Iterable[tuple[K, FormulaSpec, int]], question: Question, subject: Subject
) -> tuple[K, Fit] | None:
    """The one law that fits most strongly, with the key it was named under.

    Two laws that fit equally strongly decline: the question does not say which it is.
    """
    fits = [
        (key, filled)
        for key, spec, strength in named
        if (filled := fit(spec, strength, question, subject)) is not None
    ]
    if not fits:
        return None
    strongest = max(filled.strength for _, filled in fits)
    top = [entry for entry in fits if entry[1].strength == strongest]
    return top[0] if len(top) == 1 else None
