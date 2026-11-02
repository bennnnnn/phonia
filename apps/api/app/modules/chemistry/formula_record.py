"""The row of a chemistry law that is one line of arithmetic.

``formula_laws`` and ``stated_laws`` both build their rows with ``_law``, and ``formula_laws``
merges the two tables, so the record lives in neither.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FormulaLaw:
    op: str
    kind: str
    law_name: str
    formula: str
    find: str
    # The answer's symbol and unit: "m" in "g".
    result: str
    unit: str
    expression: str
    # Each given: parameter, label as printed, unit as printed. A label, the result and a
    # substitution row may name the intent's "{formula}" and "{target}".
    given: tuple[tuple[str, str, str], ...]
    # Substitution rows: "{name}" is a given's value as typed with its unit ("0.500 L"), and
    # "{name.value}" the bare number, for a row written in numbers alone. A constant the
    # expression names is written the same way: "{R_J}" is "8.3145 J/(mol·K)".
    substitution: tuple[str, ...]
    # Givens that may be negative (an enthalpy); every other one must be positive.
    signed: frozenset[str] = frozenset()
    # Givens that may be zero (an empty solute) but not negative.
    non_negative: frozenset[str] = frozenset()
    # (value, ceiling): the value may not exceed the ceiling.
    not_above: tuple[tuple[str, str], ...] = ()


def _law(
    op: str,
    kind: str,
    law_name: str,
    formula: str,
    find: str,
    result: tuple[str, str],
    expression: str,
    given: tuple[tuple[str, str, str], ...],
    *substitution: str,
    signed: frozenset[str] = frozenset(),
    non_negative: frozenset[str] = frozenset(),
    not_above: tuple[tuple[str, str], ...] = (),
) -> FormulaLaw:
    return FormulaLaw(
        op,
        kind,
        law_name,
        formula,
        find,
        *result,
        expression,
        given,
        substitution,
        signed,
        non_negative,
        not_above,
    )
