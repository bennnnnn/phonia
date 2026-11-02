"""Solver-owned formula and substitution rows.

The direct reply reads these fields. A solver stores both rows itself, in the
catalog's letters; the rows leave here in the symbols the reply shows (``notation``).
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.modules.physics.catalog import CATALOG, matching_variant
from app.modules.physics.display import typeset_numbers
from app.modules.physics.notation import shown
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult
from app.services.solving import SolveServiceError
from app.services.times_sign import with_times

_DECIMAL_VALUE = re.compile(r"(?<![\d.])([+-]?\d+\.\d+)(?![\d.])")


def _visible_equation(equation: str) -> str:
    equation = _DECIMAL_VALUE.sub(lambda match: match.group(1).rstrip("0").rstrip("."), equation)
    # Every product the solver wrote (\cdot, a middle dot, *) prints \times (``times_sign``).
    return with_times(typeset_numbers(equation).replace("*", r" \cdot "))


def result_symbol_for(intent: PhysicsIntent) -> str | None:
    """The quantity the solver derived, read from the formula spec, as the reply shows it."""
    spec = CATALOG.get(intent.physics_op or "")
    if spec is None:
        return None
    params = intent.physics_params or {}
    variant = matching_variant(spec, params)
    if variant is not None and variant.result_symbol:
        return shown(variant.result_symbol, spec.id)
    if spec.solve_for:
        missing = [symbol for key, symbol in spec.solve_for if key not in params]
        if len(missing) == 1:
            return shown(missing[0], spec.id)
    return shown(spec.result_symbol, spec.id)


def attach_recorded_working(result: PhysicsResult, intent: PhysicsIntent) -> PhysicsResult:
    """Clean the formula and substitution rows the solver stored, in the shown symbols."""
    operation = intent.physics_op or "physics"
    if not result.formulas or not result.substitutions:
        raise SolveServiceError(f"{operation} did not store a formula and a substitution")
    return replace(
        result,
        formulas=tuple(shown(_visible_equation(item), operation) for item in result.formulas),
        substitutions=tuple(
            shown(_visible_equation(item), operation) for item in result.substitutions
        ),
    )
