"""Checks on a solved result against its question: the asked quantity and the asked unit."""

from __future__ import annotations

import math
import re
from dataclasses import replace

from app.modules.physics.ask import result_dimension, result_reading
from app.modules.physics.display import plain_number
from app.modules.physics.givens import unit_dimension, unit_expression
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solver import PhysicsResult
from app.modules.physics.solvers.results import QuantityResult


def _in_the_asked_unit(intent: PhysicsIntent, result: PhysicsResult) -> PhysicsResult:
    """Each result of the asked unit's kind, shown in that unit ("in kWh")."""
    expression = unit_expression(intent.asked_unit) if intent.asked_unit else None
    target = unit_dimension(expression) if expression else None
    if target is None or intent.asked_unit is None:
        return result
    quantities: list[QuantityResult] = []
    # The unit each kept result was solved in, to tell a restatement from a twin.
    solved_in: list[str] = []
    for item in result.quantities:
        reading = result_reading(item.unit)
        if reading is None or reading[0] != target[0]:
            quantities.append(item)
            solved_in.append(item.unit)
            continue
        si = item.value * reading[1] + reading[2]
        # A note that only restated the value in this unit ("2.48 eV") is now the value.
        restated = item.detail is not None and re.fullmatch(
            rf"\s*-?[\d.]+(?:[eE][-+]?\d+)?\s*{re.escape(intent.asked_unit)}\s*", item.detail
        )
        shown = replace(
            item,
            value=(si - target[2]) / target[1],
            unit=intent.asked_unit,
            detail=None if restated else item.detail,
        )
        # One result given in two units ("J (eV)") is one result once both are
        # in eV. Two results that only share a value (45° components) stay two.
        if not any(
            unit != item.unit
            and other.symbol == shown.symbol
            and other.detail == shown.detail
            and other.unit == shown.unit
            and math.isclose(other.value, shown.value)
            for other, unit in zip(quantities, solved_in, strict=True)
        ):
            quantities.append(shown)
            solved_in.append(item.unit)
    return replace(result, quantities=tuple(quantities))


# A gas stated in litres or atmospheres is a chemistry class's question, and its answer reads
# in those units too: 49.2 L, not 0.0492 m³. A gas stated in m³ or Pa keeps SI.
_CHEMISTRY_GAS = frozenset({"atm", "mmhg", "torr", "l", "ml", "liter", "liters", "litre", "litres"})
_SI_GAS = frozenset({"m^3", "m³", "pa", "kpa", "mpa", "cm^3", "cm³"})
_CHEMISTRY_RESULTS = {"m^3": "L", "m³": "L", "Pa": "atm"}


def _in_context_units(intent: PhysicsIntent, result: PhysicsResult) -> PhysicsResult:
    """A volume or pressure left in SI, shown in L or atm when the givens are chemistry's."""
    if intent.asked_unit is not None:
        return result
    result = _per_gram_of_givens(intent, _per_time_of_givens(intent, result))
    result = _kwh_of_givens(intent, result)
    written = {unit.lower() for unit in (intent.physics_units or {}).values()}
    if not written & _CHEMISTRY_GAS or written & _SI_GAS:
        return result
    for unit in {
        _CHEMISTRY_RESULTS[item.unit]
        for item in result.quantities
        if item.unit in _CHEMISTRY_RESULTS
    }:
        target = intent.model_copy(update={"asked_unit": unit})
        converted = _in_the_asked_unit(target, result)
        result = replace(
            result,
            quantities=tuple(
                new
                if old.unit in _CHEMISTRY_RESULTS and _CHEMISTRY_RESULTS[old.unit] == unit
                else old
                for old, new in zip(result.quantities, converted.quantities, strict=True)
            ),
        )
    return result


# A rate from a half-life in years is per year: 1.21e-4 1/yr, not 3.83e-12 1/s. The per-time
# unit a rate takes from the time its givens share, by Pint expression, so every
# spelling the unit table reads ("hrs", "hours", "h") gives one answer unit.
_SHORT_TIME = {"year": "yr", "day": "day", "hour": "h", "minute": "min"}
_TIME = "[time]^1"


_SPECIFIC_HEAT = "J/kg/K"
_PER_GRAM_SPECIFIC_HEAT = "J/(g·°C)"


def _per_gram_of_givens(intent: PhysicsIntent, result: PhysicsResult) -> PhysicsResult:
    """A specific heat in J/(g·°C) when every mass is in grams and a temperature in °C.

    That is how a chemistry class writes both the data and the answer: 0.558 J/(g·°C), not
    558 J/(kg·K).
    """
    if not any(item.unit == _SPECIFIC_HEAT for item in result.quantities):
        return result
    expressions = [unit_expression(unit) for unit in (intent.physics_units or {}).values()]
    masses = [
        expression
        for expression in expressions
        if (reading := unit_dimension(expression or "")) and reading[0] == "[mass]^1"
    ]
    if not masses or set(masses) != {"gram"} or "degC" not in expressions:
        return result
    target = intent.model_copy(update={"asked_unit": _PER_GRAM_SPECIFIC_HEAT})
    converted = _in_the_asked_unit(target, result)
    return replace(
        result,
        quantities=tuple(
            new if old.unit == _SPECIFIC_HEAT else old
            for old, new in zip(result.quantities, converted.quantities, strict=True)
        ),
    )


def _per_time_of_givens(intent: PhysicsIntent, result: PhysicsResult) -> PhysicsResult:
    """A per-second result, per the one time unit every time given shares."""
    if intent.asked_unit is not None:
        return result
    spellings = {
        unit
        for unit in (intent.physics_units or {}).values()
        if (reading := unit_dimension(unit_expression(unit) or "")) and reading[0] == _TIME
    }
    short = {_SHORT_TIME.get(unit_expression(unit) or "") for unit in spellings}
    if len(spellings) == 0 or len(short) != 1 or None in short:
        return result
    unit = short.pop()
    reading = unit_dimension(unit_expression(next(iter(spellings))) or "")
    if unit is None or reading is None:
        return result
    return replace(
        result,
        quantities=tuple(
            replace(item, value=item.value * reading[1], unit=f"1/{unit}")
            if item.unit == "1/s"
            else item
            for item in result.quantities
        ),
    )


_POWER = "[length]^2 * [mass]^1 * [time]^-3"
_HOURS = {"hour", "day"}


def _kwh_of_givens(intent: PhysicsIntent, result: PhysicsResult) -> PhysicsResult:
    """An energy from a power and a time in hours or days, also in kWh as a bill writes it.

    100 W for 5 hours a day for 30 days is 5.4e7 J (15 kWh): the joules a
    physics class works in, and the kilowatt-hours the meter counts.
    """
    if not any(item.unit == "J" for item in result.quantities):
        return result
    readings = [
        (unit_expression(unit) or "", unit_dimension(unit_expression(unit) or ""))
        for unit in (intent.physics_units or {}).values()
    ]
    has_power = any(reading and reading[0] == _POWER for _, reading in readings)
    in_hours = any(
        reading and reading[0] == _TIME and expression in _HOURS for expression, reading in readings
    )
    if not (has_power and in_hours):
        return result
    target = intent.model_copy(update={"asked_unit": "kWh"})
    converted = _in_the_asked_unit(target, result)
    return replace(
        result,
        quantities=tuple(
            replace(old, detail=f"{plain_number(new.value)} kWh", detail_style="paren")
            if old.unit == "J" and new.unit == "kWh" and old.detail is None
            else old
            for old, new in zip(result.quantities, converted.quantities, strict=True)
        ),
    )


def _answers_the_question(intent: PhysicsIntent, result: PhysicsResult) -> bool:
    """Every quantity the question asked for is among the results.

    A solver may answer more (an Atwood pair gives acceleration and tension),
    never something else. A result unit that cannot be read leaves the decision
    to the solver.
    """
    if not intent.asked:
        return True
    produced = [result_dimension(item.unit) for item in result.quantities]
    if not produced or None in produced:
        return True
    return set(intent.asked) <= set(produced)
