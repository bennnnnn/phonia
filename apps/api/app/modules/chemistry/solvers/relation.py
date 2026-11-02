# ruff: noqa: RUF002 -- Beer-Lambert is spelled with an en dash below.
"""Solve ``product(left) = product(right)`` for the one unknown, and show the working.

The ideal gas law (PV = nRT), Boyle's, Charles's and the combined gas law, and Beer–Lambert
(A = εbc) are all the same shape: every variable appears once and the equation is a product on
each side. One table-free routine replaces four hand-written "if the unknown is X" ladders.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.modules.chemistry.solvers.display import const, inp
from app.services.solving import SolveServiceError


def _text(symbols: Sequence[str], render: dict[str, str]) -> str:
    return "".join(f"({render[symbol]})" for symbol in symbols)


def solve_paired(
    known: dict[str, float],
    unknown: str,
    left: Sequence[str],
    right: Sequence[str],
    constants: dict[str, float] | None = None,
) -> tuple[float, str, str]:
    """``(value, rearranged, substituted)`` for ``unknown`` in ``product(left) = product(right)``.

    ``known`` maps a symbol to its value, ``constants`` maps a symbol (``R``) to a physical
    constant. Every other symbol of the relation must be known.
    """
    constants = constants or {}
    if unknown in left:
        top, bottom = list(right), [symbol for symbol in left if symbol != unknown]
    elif unknown in right:
        top, bottom = list(left), [symbol for symbol in right if symbol != unknown]
    else:
        raise SolveServiceError(f"{unknown} is not a variable of this relation")
    values = {**known, **constants}
    if any(symbol not in values for symbol in (*top, *bottom)):
        raise SolveServiceError("every other variable of the relation must be known")
    numerator = math.prod(values[symbol] for symbol in top)
    denominator = math.prod(values[symbol] for symbol in bottom)
    if denominator == 0:
        raise SolveServiceError("the relation divides by zero")
    render = {symbol: inp(known[symbol]) for symbol in known}
    render.update({symbol: const(value) for symbol, value in constants.items()})
    symbolic = f"{unknown} = {''.join(top)}"
    numbers = f"{unknown} = {_text(top, render)}"
    if bottom:
        symbolic += f" / {bottom[0] if len(bottom) == 1 else f'({"".join(bottom)})'}"
        numbers += f" / {render[bottom[0]] if len(bottom) == 1 else f'[{_text(bottom, render)}]'}"
    return numerator / denominator, symbolic, numbers
