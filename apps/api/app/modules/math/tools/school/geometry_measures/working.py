"""The worked layout a solver returns, and the number spellings its rows use."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class _Solved:
    given: tuple[str, ...]
    find: tuple[str, ...]
    formula: tuple[str, ...]
    substitution: tuple[str, ...]
    answer: str


def _n(value: float) -> str:
    return f"{value:g}" if abs(value) >= 1e-4 or value == 0 else f"{value:.4g}"


def _approx(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    return _n(rounded) if rounded == round(value, 10) else f"{value:.{places}f}"


def _unit(unit: str | None, power: int = 1) -> str:
    if not unit:
        return ""
    return rf"\ \mathrm{{{unit}}}" + (f"^{{{power}}}" if power > 1 else "")


def _degrees(value: float) -> str:
    return rf"{_approx(value, 1) if not float(value).is_integer() else _n(value)}^\circ"


def _surd_answer(square: float, unit: str | None) -> str:
    """``\\sqrt{12} = 2\\sqrt{3} \\approx 3.46`` or a whole number."""
    root = math.sqrt(square)
    if abs(root - round(root)) < 1e-9:
        return f"{round(root)}{_unit(unit)}"
    if float(square).is_integer():
        whole, inside = 1, int(square)
        factor = 2
        while factor * factor <= inside:
            while inside % (factor * factor) == 0:
                inside //= factor * factor
                whole *= factor
            factor += 1
        exact = rf"\sqrt{{{inside}}}" if whole == 1 else rf"{whole}\sqrt{{{inside}}}"
        return rf"{exact} \approx {_approx(root)}{_unit(unit)}"
    return rf"\approx {_approx(root)}{_unit(unit)}"
