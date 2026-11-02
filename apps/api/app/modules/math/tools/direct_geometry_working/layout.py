"""The shared Given / Required / Formula / Substitution layout of a geometry working."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping

from app.modules.math.schemas import GeometryRequest
from app.services.workout import Workout, formula_heading, math_line, render_workout, solve_for_line

# (what was asked, the verified figure's measures, the verified result) -> layout
Working = Callable[[GeometryRequest, Mapping[str, object], str], str | None]


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def display(value: float) -> str:
    """Keep significant decimals while never adding cosmetic trailing zeroes."""
    return format(value, ".12g")


def figure_unit(spec: Mapping[str, object]) -> str:
    unit = spec.get("unit")
    return unit if isinstance(unit, str) else "units"


def unit_tex(unit: object) -> str:
    text = unit if isinstance(unit, str) and unit else "units"
    safe = text.replace("\\", "").replace("{", "").replace("}", "")
    return rf"\mathrm{{{safe}}}"


def given(label: str, symbol: str, value: float, unit: str) -> str:
    return rf"{label}: ${symbol} = {display(value)}\,{unit_tex(unit)}$"


_LABELLED = re.compile(r"^(?P<label>[^:$]+):\s*\$(?P<tex>[^$]+)\$$")
_NAMED_FIND = re.compile(r"^(?P<name>[^($]+?)\s*\(\$(?P<tex>[^$]+)\$\)$")


def _labelled_line(line: str) -> str:
    """``Base: $b = 6$`` → ``$b = 6$ — base``: the value first, its name as the note."""
    match = _LABELLED.match(line.strip())
    if match is None:
        return line
    return math_line(match.group("tex"), match.group("label").strip().lower())


def _find_line(find: str) -> str:
    match = _NAMED_FIND.match(find.strip())
    if match is None:
        return find
    return math_line(match.group("tex"), match.group("name").strip().lower())


def section(
    givens: list[str],
    find: str,
    formula_name: str,
    formulas: list[str],
    substitutions: list[str],
    *,
    solved: str | None = None,
) -> str:
    """The shared workout layout; the caller's answer fence follows **Answer**.

    ``solved`` is the formula rearranged for the unknown (``l = \\frac{A}{w}``): a
    ``Solve for $l$`` line, then that formula, after the others.
    """
    formula_lines = [math_line(formula) for formula in formulas]
    if solved is not None:
        formula_lines += [solve_for_line(solved.split(" = ", 1)[0]), math_line(solved)]
    return render_workout(
        Workout(
            given=tuple(_labelled_line(line) for line in givens),
            find=(_find_line(find),),
            formula=tuple(formula_lines),
            # The formula's name heads it ("Circle area formula"), never a note on its line.
            formula_heading=formula_heading(formula_name),
            substitution=tuple(math_line(line) for line in substitutions),
        )
    )


def root_of_squares(name: str, first: float, second: float, result: str) -> str:
    """``c = √(3² + 4²) = √(9 + 16) = √25 = 5``: each square, their sum, then the root."""
    squares = (first * first, second * second)
    return (
        rf"{name} = \sqrt{{{display(first)}^2 + {display(second)}^2}}"
        rf" = \sqrt{{{display(squares[0])} + {display(squares[1])}}}"
        rf" = \sqrt{{{display(squares[0] + squares[1])}}} = {result}"
    )
