"""Distance, speed and time: d = vt and average speed, shown in the question's units."""

from __future__ import annotations

import math

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.services.solving import SolveServiceError
from app.services.times_sign import times

_RATE_OPERATIONS = {"average_speed", "rate_speed", "rate_distance", "rate_time"}


def _same_unit(left: str, right: str) -> bool:
    """One unit however it is spelled: "hours" is the "h" of "km/h"."""
    from app.modules.physics.givens import unit_expression

    return (unit_expression(left) or left) == (unit_expression(right) or right)


def _in_si(value: float, unit: str, si: str) -> tuple[float, str]:
    """The value in the SI unit ``si``; a unit Pint cannot read is refused."""
    from app.modules.physics.givens import unit_expression
    from app.services.units import get_unit_registry

    ureg = get_unit_registry()
    try:
        quantity = ureg.Quantity(value, unit_expression(unit) or unit)
        return float(quantity.to(ureg(unit_expression(si) or si)).magnitude), si
    except Exception as exc:
        raise SolveServiceError(f"cannot convert {unit} to {si}") from exc


def _rate_number(value: float) -> str:
    """Format a checked scalar without inventing presentation precision."""
    if not math.isfinite(value):
        raise SolveServiceError("rate result must be finite")
    return f"{value:.12g}"


def _rate_substitution(
    symbol: str, left: tuple[float, str], right: tuple[float, str], *, divide: bool
) -> str:
    """The plugged-in rate row, with the numbers the rate was worked from: the question's
    units when they agree, the SI ones it was converted to when they do not. The givens'
    conversions are shown from this row, so "5 km" at "25 m/s" reads 5 km = 5000 m first,
    then 5000 m over 25 m/s, never 5 km over 25 m/s (2026-11-01)."""
    from app.modules.physics.display import latex_given, latex_unit

    first = f"{latex_given(left[0])}{latex_unit(left[1])}"
    second = f"{latex_given(right[0])}{latex_unit(right[1])}"
    if divide:
        return rf"{symbol} = \frac{{{first}}}{{{second}}}"
    return f"{symbol} = {times(first, second)}"


def _result(
    formula: str, working: str, value: float, unit: str, substitution: str
) -> PhysicsResult:
    return PhysicsResult(
        answer=working,
        formulas=(formula,),
        quantities=(QuantityResult("", value, unit),),
        substitutions=(substitution,),
    )


def _speed(params: dict[str, float], units: dict[str, str]) -> PhysicsResult:
    """v = d/t in the question's own units: "km" over "hours" is km/h."""
    from app.modules.physics.display import plain_unit

    distance, duration = params.get("d"), params.get("t")
    distance_unit, time_unit = units.get("d"), units.get("t")
    if (
        distance is None
        or duration is None
        or distance_unit is None
        or time_unit is None
        or distance < 0
        or duration <= 0
    ):
        raise SolveServiceError("speed requires a non-negative distance and positive time")
    value = distance / duration
    answer_unit = f"{plain_unit(distance_unit)}/{plain_unit(time_unit)}"
    working = (
        rf"v = \frac{{d}}{{t}} = "
        rf"\frac{{{_rate_number(distance)}\,\mathrm{{{distance_unit}}}}}"
        rf"{{{_rate_number(duration)}\,\mathrm{{{time_unit}}}}} = "
        rf"{_rate_number(value)}\,\mathrm{{{answer_unit}}}"
    )
    substitution = _rate_substitution(
        "v", (distance, distance_unit), (duration, time_unit), divide=True
    )
    return _result(r"v = \frac{d}{t}", working, value, answer_unit, substitution)


def _distance(params: dict[str, float], units: dict[str, str]) -> PhysicsResult:
    """d = vt; a speed and a time on two clocks (54 km/h for 10 s) are worked in m/s and s."""
    speed, duration = params.get("v"), params.get("t")
    speed_unit, time_unit = units.get("v"), units.get("t")
    if (
        speed is None
        or duration is None
        or speed_unit is None
        or time_unit is None
        or speed < 0
        or duration < 0
        or "/" not in speed_unit
    ):
        raise SolveServiceError("distance requires a non-negative speed and time")
    distance_unit, speed_time_unit = speed_unit.split("/", 1)
    if not _same_unit(speed_time_unit, time_unit):
        speed, speed_unit = _in_si(speed, speed_unit, "m/s")
        duration, time_unit = _in_si(duration, time_unit, "s")
        distance_unit = "m"
    value = speed * duration
    working = (
        rf"d = vt = "
        rf"{_rate_number(speed)}\,\mathrm{{{speed_unit}}} \times "
        rf"{_rate_number(duration)}\,\mathrm{{{time_unit}}} = "
        rf"{_rate_number(value)}\,\mathrm{{{distance_unit}}}"
    )
    substitution = _rate_substitution("d", (speed, speed_unit), (duration, time_unit), divide=False)
    return _result(r"d = vt", working, value, distance_unit, substitution)


def _time(params: dict[str, float], units: dict[str, str]) -> PhysicsResult:
    """t = d/v; a distance and a speed on two rulers (3 km at 2 m/s) are worked in m and m/s."""
    distance, speed = params.get("d"), params.get("v")
    distance_unit, speed_unit = units.get("d"), units.get("v")
    if (
        distance is None
        or speed is None
        or distance_unit is None
        or speed_unit is None
        or distance < 0
        or speed <= 0
        or "/" not in speed_unit
    ):
        raise SolveServiceError("time requires a non-negative distance and positive speed")
    speed_distance_unit, answer_unit = speed_unit.split("/", 1)
    if not _same_unit(speed_distance_unit, distance_unit):
        distance, distance_unit = _in_si(distance, distance_unit, "m")
        speed, speed_unit = _in_si(speed, speed_unit, "m/s")
        answer_unit = "s"
    value = distance / speed
    working = (
        rf"t = \frac{{d}}{{v}} = "
        rf"\frac{{{_rate_number(distance)}\,\mathrm{{{distance_unit}}}}}"
        rf"{{{_rate_number(speed)}\,\mathrm{{{speed_unit}}}}} = "
        rf"{_rate_number(value)}\,\mathrm{{{answer_unit}}}"
    )
    substitution = _rate_substitution(
        "t", (distance, distance_unit), (speed, speed_unit), divide=True
    )
    return _result(r"t = \frac{d}{v}", working, value, answer_unit, substitution)


def _solve_distance_speed_time(intent: PhysicsIntent) -> PhysicsResult:
    """Solve one closed distance-speed-time request in its supplied units."""
    params = intent.physics_params or {}
    units = intent.physics_units or {}
    op = intent.physics_op
    if op in {"average_speed", "rate_speed"}:
        return _speed(params, units)
    if op == "rate_distance":
        return _distance(params, units)
    if op == "rate_time":
        return _time(params, units)
    raise SolveServiceError(f"unsupported rate operation: {op}")  # pragma: no cover
