# ruff: noqa: RUF002 -- textbook formulas use a proper minus sign.
"""How the chemistry solvers write a number, a given and the verified answer."""

from __future__ import annotations

import math

import app.modules.chemistry.sig_figs as sig_figs
from app.modules.chemistry.solvers.types import (
    INPUT_FIGURES,
    ChemistryResult,
    format_constant,
    format_molar_mass,
    format_number,
)
from app.services.school_rounding import round_places
from app.services.units import CELSIUS_OFFSET_K


def verified(
    title: str,
    given: tuple[str, ...] | list[str],
    find: str,
    formula_name: str,
    formula: str,
    substitution: tuple[str, ...] | list[str],
    answer: str,
    value: str,
    *,
    verbatim: bool = False,
) -> ChemistryResult:
    return ChemistryResult(
        title,
        tuple(given),
        find,
        formula_name,
        formula,
        tuple(substitution),
        answer,
        value,
        verbatim=verbatim,
    )


def fixed(value: float, places: int) -> str:
    """A value to fixed decimal places, rounded half up, never a negative zero (−0.00).

    A sum keeps the fewest places of its terms.
    """
    if not math.isfinite(value):
        return str(value)
    text = f"{round_places(value, places):.{places}f}"
    return text.removeprefix("-") if float(text) == 0 else text


def num(value: float) -> str:
    """A computed value, to the significant figures the question's data carry."""
    written = sig_figs.current()
    if written is not None and written.additive and written.decimals is not None:
        return fixed(value, written.decimals)
    if written is not None and written.figures is not None:
        return format_number(value, significant=written.figures, keep_zeros=True)
    return format_number(value)


def mean(value: float) -> str:
    """A weighted mean of the givens (an average atomic mass), as ``sig_figs`` sets it.

    Its figures, but never more decimal places than ``decimals``; with neither, the mean of
    exact values, written without padding zeros (10.8).
    """
    written = sig_figs.current()
    if written is None or written.figures is None:
        return format_number(value)
    text = format_number(value, significant=written.figures, keep_zeros=True)
    if written.decimals is not None and sig_figs.decimals_of(text) > written.decimals:
        return fixed(value, written.decimals)
    return text


def table_num(value: float) -> str:
    """A value from the element table alone, such as a formula's percent composition.

    No measured given limits it, so it has four figures, and its trailing zeros are figures
    too: N in NH4NO3 is 35.00%, not 35%. A question that measured something uses ``num``.
    """
    written = sig_figs.current()
    if written is not None and written.figures is not None:
        return num(value)
    return format_number(value, keep_zeros=True)


def p_value(value: float) -> str:
    """A pH, pOH or pK: a logarithm, so its precision is decimal places (pH 3.49)."""
    written = sig_figs.current()
    if written is not None and written.decimals is not None:
        return fixed(value, written.decimals)
    return num(value)


def inp(value: float) -> str:
    """A value the user supplied, echoed as typed (1.10 V) or, if derived, unrounded (273.15 K)."""
    written = sig_figs.current()
    typed = None if written is None else written.written.get(repr(value))
    if typed is not None:
        return sig_figs.as_written(typed)
    return format_number(value, significant=INPUT_FIGURES)


def with_unit(value: str, unit: str) -> str:
    """A number and its unit as a substitution writes them: "0.500 L", "40.0%", "2" bare."""
    if not unit:
        return value
    return f"{value}{unit}" if unit == "%" else f"{value} {unit}"


def qty(value: float, unit: str) -> str:
    """A given with its unit, as typed: "36 g", "0.500 L"."""
    return with_unit(inp(value), unit)


def _typed_literal(value: float) -> str | None:
    written = sig_figs.current()
    return None if written is None else written.converted.get(repr(value))


def used(value: float) -> str:
    """A given as the arithmetic uses it.

    Typed in the solver's unit, it is echoed as typed. Converted, it keeps what was typed:
    a Celsius reading its decimal places (25 °C is 298 K), and a unit change its figures
    (500 mL is 0.500 L) without rounding away the conversion's own digits (1 h is 3600 s).
    """
    literal = _typed_literal(value)
    if literal is None:
        return inp(value)
    if math.isclose(value - float(literal), CELSIUS_OFFSET_K, abs_tol=1e-9):
        # The offset is exact, so the working shows the kelvin it adds: 37 °C is 310.15 K.
        return f"{value:.{max(sig_figs.decimals_of(literal), 2)}f}"
    return converted(value, literal)


# A unit change whose result has at most this many significant digits terminated (1 h is
# 3600 s, 10 kcal is 41.84 kJ). One that repeats (700 mmHg is 0.92105… atm) fills all twelve.
_EXACT_DIGITS = 6


def converted(value: float, literal: str) -> str:
    """A value a unit change made from a typed literal: 500 mL is 0.500 L, 1 h is 3600 s.

    It keeps the literal's figures. An exact conversion also keeps its own digits (3600, not
    4 × 10^3); a repeating one has none to keep, so 700 mmHg is 0.921 atm.
    """
    digits = f"{abs(value):.12g}".split("e")[0].replace(".", "").strip("0")
    exact = len(digits) if len(digits) <= _EXACT_DIGITS else 0
    figures = max(sig_figs.figures_of(literal), exact, 1)
    return format_number(value, significant=figures, keep_zeros=True)


def converted_from(value: float, typed: float) -> str:
    """``converted`` for a solver's own unit change, from the typed value it started from."""
    written = sig_figs.current()
    literal = None if written is None else written.written.get(repr(typed))
    return converted(value, literal or inp(typed))


def typed_unit(value: float, sizes: tuple[tuple[str, float], ...]) -> str | None:
    """The unit a converted given was typed in, from the factor its literal was scaled by.

    ``sizes`` pairs each unit a reader converts from with its size in the unit the solver
    uses: ``("kcal/mol", 4.184)`` for kJ/mol. None when no listed unit explains the factor.
    """
    literal = _typed_literal(value)
    if literal is None or float(literal) == 0:
        return None
    factor = value / float(literal)
    return next((unit for unit, size in sizes if math.isclose(factor, size, rel_tol=1e-9)), None)


def given_row(symbol: str, value: float, unit: str, typed_unit: str | None) -> str:
    """A given as typed and, when an extractor converted it, as used: "t = 1 h = 3600 s".

    ``typed_unit`` is the unit a converted value was typed in (``typed_unit()`` reads it from
    the conversion, and °C is the one offset). Unknown, the row shows only the value used:
    never an equality between a typed number and a unit it was not typed in.
    """
    literal = _typed_literal(value)
    if literal is None or typed_unit is None:
        return f"{symbol} = {with_unit(used(value), unit)}"
    typed = with_unit(sig_figs.as_written(literal), typed_unit)
    return f"{symbol} = {typed} = {with_unit(used(value), unit)}"


def const(value: float) -> str:
    """A physical constant, one figure more precise than an answer."""
    return format_constant(value)


def molar_mass_text(value: float) -> str:
    """A molar mass that is the answer, to two decimals by convention (98.07 g/mol)."""
    return format_molar_mass(value)


def molar_mass_working(value: float) -> str:
    """A molar mass inside a calculation, to the element table's precision (18.015).

    Two decimals there would not reproduce the answer: 4 / 2.02 × 18.02 is 35.68 g, while
    4 g of H2 makes 35.74 g of water.
    """
    return f"{value:.3f}"


def atomic_mass(value: float) -> str:
    """A tabulated atomic mass exactly as the table gives it (1.008, 15.999, 196.967)."""
    return format_number(value, significant=6)
