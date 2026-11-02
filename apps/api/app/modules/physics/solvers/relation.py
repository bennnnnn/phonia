"""Solve an expression operation: one catalog law, evaluated for its givens.

The catalog states the law and, for each set of givens, the arithmetic that
answers it (``u = v - at`` for v, a and t). This solver evaluates that
arithmetic in SI and prints the formula and the substitution from the same
expression, so the working is the computation.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.modules.physics.display import conversion_row, si_symbol
from app.modules.physics.expression import evaluate, to_latex
from app.modules.physics.givens import unit_dimension, unit_expression
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult, solved
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError

if TYPE_CHECKING:
    from app.services.law_binding.spec import FormulaSpec


def solve_expression(intent: PhysicsIntent) -> PhysicsResult:
    from app.modules.physics.catalog import CATALOG, matching_variant

    spec = CATALOG.get(intent.physics_op or "")
    if spec is None or spec.expression is None or spec.binding is None:
        raise SolveServiceError(f"{intent.physics_op} is not an expression operation")
    params = params_in_si(intent)
    variant = matching_variant(spec, params)
    expression = spec.expression
    symbol = spec.result_symbol
    if variant is not None:
        expression = variant.expression or expression
        symbol = variant.result_symbol or symbol
    try:
        value = evaluate(expression, params)
        holds = all(evaluate(condition, params) > 0 for condition in spec.binding.requires)
    except (KeyError, ValueError, OverflowError) as exc:
        raise SolveServiceError(f"{spec.id} has no real answer for these givens") from exc
    if not holds:
        raise SolveServiceError(f"{spec.id} does not hold for these givens")
    if not math.isfinite(value):
        raise SolveServiceError(f"{spec.id} answer is not finite")
    detail = None
    if spec.binding.negative_detail and value < 0:
        value = abs(value)
        detail = spec.binding.negative_detail
    elif spec.binding.nonnegative and value < 0:
        raise SolveServiceError(f"{spec.id} gives a negative {symbol} for these givens")
    if spec.binding.at_most is not None and value > spec.binding.at_most:
        raise SolveServiceError(f"{spec.id} gives {symbol} above {spec.binding.at_most:g}")
    symbols = {variable.name: variable.symbol for variable in spec.variables}
    formula = f"{symbol} = {to_latex(expression, symbols)}"
    substitution = f"{symbol} = {to_latex(expression, symbols, params)}"
    difference = _stated_temperature_change(intent, params) if spec.id == "heat_energy" else None
    result_unit = spec.binding.result[0]
    unit = spec.binding.shown_unit or (
        "" if result_unit == "dimensionless" else si_symbol(result_unit)
    )
    # A law that prints an SI-sized unit of its own ("photons/s", "Bq") is not
    # answered in a like given's unit: a photon rate is not the hertz of a
    # frequency given beside it.
    own = unit_dimension(unit_expression(unit) or "") if spec.binding.shown_unit else None
    own_unit = own is not None and own[1] == 1.0 and own[2] == 0.0
    shown = None if own_unit else _in_the_givens_unit(spec, intent, result_unit, value)
    if shown is None or shown[1] == unit or math.isclose(shown[0], value):
        # No step to show: the same unit, or only its spelling ("J/kg°C" for J/(kg·K)).
        rows: tuple[str, ...] = (substitution,)
    else:
        # The arithmetic is in SI; the step to the givens' unit is part of the working.
        rows = (substitution, conversion_row(symbol, (value, unit), shown))
    return solved(
        QuantityResult("", *(shown or (value, unit)), detail=detail),
        answer=substitution,
        formulas=((difference, formula) if difference else (formula,)),
        substitutions=rows,
    )


def _stated_temperature_change(intent: PhysicsIntent, params: dict[str, float]) -> str | None:
    """The ΔT row when a question gave two readings: ``80 - 20 = 60``."""
    if "temp_initial" not in params or "temp_final" not in params:
        return None
    change = params["temp_final"] - params["temp_initial"]
    raw = intent.physics_params or {}
    units = intent.physics_units or {}
    # Readings in one unit of kelvin's size (°C or K) subtract as written; a
    # Fahrenheit difference is not the kelvins the substitution uses.
    reading = unit_dimension(unit_expression(units.get("temp_initial", "")) or "")
    same_scale = (
        units.get("temp_initial") == units.get("temp_final")
        and reading is not None
        and math.isclose(reading[1], 1.0)
    )
    first = raw["temp_initial"] if same_scale else params["temp_initial"]
    second = raw["temp_final"] if same_scale else params["temp_final"]
    return rf"\Delta T = T_2 - T_1 = {second:g} - {first:g} = {change:g}"


def _in_the_givens_unit(
    spec: FormulaSpec, intent: PhysicsIntent, result_unit: str, value: float
) -> tuple[float, str] | None:
    """The result in the one unit its like givens share: 4 µF and 6 µF give µF.

    A textbook answers two capacitances in µF in µF, and a radius in cm with a
    focal length in cm. Givens of the result's kind in different units, or
    none, leave the answer in SI. Temperatures in °C give a temperature in
    °C, and a change of temperature stays a change: a rise of 10 K is a rise of 10 °C.
    """
    target = unit_dimension(result_unit)
    if target is None:
        return None
    units = intent.physics_units or {}
    alike = {
        variable.name: units[variable.name]
        for variable in spec.variables
        if variable.dimension is not None
        and variable.name in units
        and (kind := unit_dimension(variable.dimension)) is not None
        and kind[0] == target[0]
    }
    if len(set(alike.values())) != 1:
        return None
    unit = next(iter(alike.values()))
    expression = unit_expression(unit)
    reading = unit_dimension(expression) if expression else None
    if reading is None or reading[0] != target[0]:
        return None
    difference = any(name.startswith("delta_") for name in alike)
    offset = 0.0 if difference else reading[2]
    return (value - offset) / reading[1], unit
