"""Substitution carried to the answer: the arithmetic a student still has to do, done.

A solver stores the substituted law (``a = \\frac{27.7778 - 0}{8}``) and stops. The
reply works it one layer at a time (``reduce_substitution``) and ends on the
verified answer itself, never on a number worked here:

    a = \\frac{27.7778 - 0}{8}
    a = \\frac{27.7778}{8}
    a = 3.47\\,\\mathrm{m/s²}

A row is matched to the answer by value, not by name: "a and T", "50 N at 53.1°" and
"H_max and R" each have a row per value, and ``|v|`` or ``f_s`` may name it. The middle
rows are shown only when they reach a verified value (or the SI value a conversion row
then turns into the shown unit). One row and one answer close on the answer even when
the row is past reading. A row the solver already worked (``E = 2000 \\cdot 10800`` then
``E = 2.16 \\times 10^{7} J``) is left as it is.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

from app.modules.physics.display import (
    ANSWER_FIGURES,
    is_conversion_row,
    is_value_row,
    latex_given,
    latex_unit,
    quantity_number,
)
from app.modules.physics.givens import unit_readings
from app.services.law_binding.reduction import Reduction, reduce_substitution
from app.services.school_rounding import round_figures
from app.services.units import get_unit_registry

# How a verified answer joins its values (solvers/chip.py render_chip_latex).
_JOINS = re.compile(r";\\quad |\\ \\text\{(?:and|or)\}\\ |,\\ ")
# "50 N\ \text{at 53.1°}": the angle is a value of its own.
_AT = re.compile(r"\\ \\text\{at (?P<at>[^}]*)\}")
# "459 Hz\ (\text{receding, …})": a note on the value, not a value.
_NOTE = re.compile(r"\\ \((?:\\text\{[^}]*\}|[^()]*)\)\s*$")
_LEADING_SYMBOL = re.compile(r"^[^=]+=\s*")
_NUMBER = re.compile(r"(?P<number>-?\d+(?:\.\d+)?)(?:\s*\\times\s*10\^\{(?P<power>-?\d+)\})?")
_ROW = re.compile(r"^(?P<lhs>[^=]+?)\s*=\s*(?P<rhs>[^=]+)$")


def answer_parts(latex_answer: str | None) -> list[tuple[str, float]]:
    """Each value of a verified answer as (LaTeX to close a row on, its number)."""
    parts: list[tuple[str, float]] = []
    for piece in _JOINS.split((latex_answer or "").strip()):
        at = _AT.search(piece)
        pieces = [_AT.sub("", piece), at.group("at")] if at else [piece]
        for value in pieces:
            shown = _NOTE.sub("", _LEADING_SYMBOL.sub("", value.strip())).strip()
            number = _NUMBER.match(shown)
            if number is None:
                continue
            amount = float(number.group("number"))
            if number.group("power"):
                amount *= 10.0 ** int(number.group("power"))
            parts.append((shown, amount))
    return parts


def _same(worked: float, verified: float) -> bool:
    """Equal to three figures, or within 0.1%: the working's constants are rounded as
    typed, so 7672.4 worked from them is the verified 7673, and 5542 is 5545."""
    return round_figures(worked, ANSWER_FIGURES) == round_figures(
        verified, ANSWER_FIGURES
    ) or math.isclose(worked, verified, rel_tol=1e-3)


# The SI unit a working value is in, found by the answer's unit's dimension.
_SI_UNITS = ("J", "N", "W", "Pa", "m", "s", "kg", "m/s", "m/s^2", "A", "V", "C", "F", "Hz", "K")
_UNIT = re.compile(r"\\mathrm\{(?P<unit>[^}]+)\}")
# "\frac{1}{R_p} = …": a law that gives the reciprocal of what is asked.
_RECIPROCAL = re.compile(r"\\frac\{1\}\{(?P<of>[^{}]+)\}")


def _in_si(part: str) -> tuple[str, float] | None:
    """(SI unit, how many of it one of the answer's unit is): an eV is 1.602e-19 J."""
    written = _UNIT.search(part)
    if written is None:
        return None
    ureg = get_unit_registry()
    for reading in unit_readings(written.group("unit").replace("²", "^2").replace("³", "^3")):
        found = _named_si(ureg, reading)
        if found is not None:
            return found
    return None


def _named_si(ureg: Any, reading: str) -> tuple[str, float] | None:
    try:
        unit = ureg(reading)
        si = next((si for si in _SI_UNITS if ureg(si).dimensionality == unit.dimensionality), None)
        return None if si is None else (si, float((1 * unit).to(si).magnitude))
    except Exception:
        return None


def _closing(lhs: str, reduction: Reduction | None, part: tuple[str, float]) -> list[str] | None:
    """The rows after the substitution that end on ``part``, or None when they do not reach it.

    The working's value is the answer; or its negative, when the answer is a size with a
    direction ("5000 N, opposing the motion"); or the answer in SI, when the answer is shown
    in another unit (photon energy in eV); or its reciprocal, for a law in 1/R or 1/f.
    """
    shown, verified = part
    if reduction is None:
        return None
    middle = list(reduction.rows)
    # A row for 1/R_p ends on R_p, even when the two are equal (two 2 Ω in parallel).
    reciprocal = _RECIPROCAL.fullmatch(lhs)
    if reciprocal is None and _same(reduction.value, verified):
        return [*middle, f"{lhs} = {shown}"]
    if reciprocal is None and reduction.value < 0 < verified and _same(-reduction.value, verified):
        return [*middle, f"{lhs} = -{shown}"]
    if reciprocal is not None and reduction.value and _same(1 / reduction.value, verified):
        value, of = latex_given(reduction.value), reciprocal.group("of")
        return [*middle, f"{lhs} = {value}", rf"{of} = \frac{{1}}{{{value}}}", f"{of} = {shown}"]
    si = _in_si(shown)
    if si is not None and si[1] != 1 and _same(reduction.value / si[1], verified):
        worked = f"{latex_given(reduction.value)}{latex_unit(si[0])}"
        return [*middle, f"{lhs} = {worked} = {shown}"]
    return None


def _worked_rows(rows: Sequence[str]) -> list[int]:
    """Rows that substitute into a law and stop: a left side, arithmetic, no value after."""
    found: list[int] = []
    for at, row in enumerate(rows):
        following = rows[at + 1] if at + 1 < len(rows) else None
        if is_conversion_row(row) or is_value_row(row) or _ROW.match(row) is None:
            continue
        if following is not None and is_value_row(following):
            continue
        found.append(at)
    return found


def carried_to_answer(rows: Sequence[str], latex_answer: str | None) -> list[str]:
    """The solver's rows, each substitution that gives a verified value worked down to it."""
    parts = answer_parts(latex_answer)
    worked = _worked_rows(rows)
    unused = list(parts)
    after: dict[int, list[str]] = {}
    for at in worked:
        match = _ROW.match(rows[at])
        if match is None:
            continue
        lhs, rhs = match.group("lhs").strip(), match.group("rhs").strip()
        following = rows[at + 1] if at + 1 < len(rows) else None
        conversion = following if following is not None and is_conversion_row(following) else None
        reduction = reduce_substitution(lhs, rhs, latex_given)
        if conversion is not None:
            target = quantity_number(conversion)
            if reduction is not None and target is not None and _same(reduction.value, target):
                after[at] = list(reduction.rows)
            continue
        for part in unused:
            closing = _closing(lhs, reduction, part)
            if closing is not None:
                unused.remove(part)
                after[at] = closing
                break
        else:
            if reduction is None and len(worked) == 1 and len(parts) == 1:
                # Past reading, but the one law gives the one answer (R_p, not 1/R_p).
                reciprocal = _RECIPROCAL.fullmatch(lhs)
                named = lhs if reciprocal is None else reciprocal.group("of")
                after[at] = [f"{named} = {parts[0][0]}"]
    out: list[str] = []
    for at, row in enumerate(rows):
        out.append(row)
        out.extend(after.get(at, []))
    return out
