"""Average speed over two stretches, worked in the question's own units.

The average is the whole distance over the whole time, never the mean of the
speeds unless the two times are equal. A trip given in km and km/h is worked
in km, h and km/h, as a student writes it; mixed units fall back to m and m/s.
"""

from __future__ import annotations

from app.modules.physics.display import latex_given, latex_number, plain_unit
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.rates import _in_si, _same_unit
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.services.solving import SolveServiceError

_AVERAGE_SPEED_OPERATIONS = frozenset(
    {"average_speed_two_legs", "average_speed_equal_distances", "average_speed_equal_times"}
)


def _quantity(value: float, unit: str, *, given: bool = True) -> str:
    number = latex_given(value) if given else latex_number(value)
    return rf"{number}\,\mathrm{{{plain_unit(unit)}}}"


def _speeds(intent: PhysicsIntent) -> tuple[float, float, str]:
    """Both speeds in one unit: the stated one when they share it, else m/s."""
    params = intent.physics_params or {}
    units = intent.physics_units or {}
    v1, v2 = params.get("v1"), params.get("v2")
    u1, u2 = units.get("v1"), units.get("v2")
    if v1 is None or v2 is None or not u1 or not u2:
        raise SolveServiceError("average speed needs both speeds")
    if v1 <= 0 or v2 <= 0:
        raise SolveServiceError("both speeds must be positive")
    if _same_unit(u1, u2):
        return v1, v2, u1
    (v1, _), (v2, _) = _in_si(v1, u1, "m/s"), _in_si(v2, u2, "m/s")
    return v1, v2, "m/s"


def _two_legs(intent: PhysicsIntent) -> PhysicsResult:
    params = intent.physics_params or {}
    units = intent.physics_units or {}
    d1, d2 = params.get("d1"), params.get("d2")
    du1, du2 = units.get("d1"), units.get("d2")
    if d1 is None or d2 is None or not du1 or not du2:
        raise SolveServiceError("two legs need both distances")
    if d1 <= 0 or d2 <= 0:
        raise SolveServiceError("both distances must be positive")
    v1, v2, speed_unit = _speeds(intent)
    length_unit, _, time_unit = speed_unit.partition("/")
    if not time_unit or not (_same_unit(du1, length_unit) and _same_unit(du2, length_unit)):
        # 3 km at 2 m/s: the rulers differ, so work in m, s and m/s.
        (d1, _), (d2, _) = _in_si(d1, du1, "m"), _in_si(d2, du2, "m")
        if speed_unit != "m/s":
            (v1, _), (v2, _) = _in_si(v1, speed_unit, "m/s"), _in_si(v2, speed_unit, "m/s")
        speed_unit, length_unit, time_unit = "m/s", "m", "s"
    t1, t2 = d1 / v1, d2 / v2
    value = (d1 + d2) / (t1 + t2)
    # "for the 200 km trip": a stated total is the top line as the student
    # reads it, once it agrees with the two legs. One that does not is a
    # question at odds with itself, and gets no verified answer.
    distance = rf"{_quantity(d1, length_unit)} + {_quantity(d2, length_unit)}"
    total = params.get("d_total")
    if total is not None:
        total_unit = units.get("d_total") or ""
        if not _same_unit(total_unit, length_unit):
            total, total_unit = _in_si(total, total_unit, "m")
            if length_unit != "m":
                raise SolveServiceError("the trip's total is in another unit than its legs")
        if abs(total - (d1 + d2)) > 1e-6 * max(total, d1 + d2):
            raise SolveServiceError("the stated total is not the sum of the two legs")
        distance = _quantity(total, length_unit)
    formula = r"\bar{v} = \frac{d_1 + d_2}{t_1 + t_2}"
    rows = (
        rf"t_1 = \frac{{{_quantity(d1, length_unit)}}}{{{_quantity(v1, speed_unit)}}}"
        rf" = {_quantity(t1, time_unit, given=False)}",
        rf"t_2 = \frac{{{_quantity(d2, length_unit)}}}{{{_quantity(v2, speed_unit)}}}"
        rf" = {_quantity(t2, time_unit, given=False)}",
        rf"\bar{{v}} = \frac{{{distance}}}"
        rf"{{{_quantity(t1, time_unit, given=False)} + {_quantity(t2, time_unit, given=False)}}}",
    )
    return _result(formula, rows, value, speed_unit)


def _equal_distances(intent: PhysicsIntent) -> PhysicsResult:
    v1, v2, unit = _speeds(intent)
    value = 2 * v1 * v2 / (v1 + v2)
    formula = r"\bar{v} = \frac{2 v_1 v_2}{v_1 + v_2}"
    rows = (
        rf"\bar{{v}} = \frac{{2 \cdot {_quantity(v1, unit)} \cdot {_quantity(v2, unit)}}}"
        rf"{{{_quantity(v1, unit)} + {_quantity(v2, unit)}}}",
    )
    return _result(formula, rows, value, unit)


def _equal_times(intent: PhysicsIntent) -> PhysicsResult:
    v1, v2, unit = _speeds(intent)
    value = (v1 + v2) / 2
    formula = r"\bar{v} = \frac{v_1 + v_2}{2}"
    rows = (rf"\bar{{v}} = \frac{{{_quantity(v1, unit)} + {_quantity(v2, unit)}}}{{2}}",)
    return _result(formula, rows, value, unit)


def _result(formula: str, rows: tuple[str, ...], value: float, unit: str) -> PhysicsResult:
    answer = rf"{rows[-1]} = {_quantity(value, unit, given=False)}"
    return PhysicsResult(
        answer=answer,
        formulas=(formula,),
        substitutions=rows,
        quantities=(QuantityResult("", value, plain_unit(unit)),),
    )


def solve_average_speed(intent: PhysicsIntent) -> PhysicsResult:
    """One of the three average-speed laws, by operation."""
    op = intent.physics_op
    if op == "average_speed_two_legs":
        return _two_legs(intent)
    if op == "average_speed_equal_distances":
        return _equal_distances(intent)
    if op == "average_speed_equal_times":
        return _equal_times(intent)
    raise SolveServiceError(f"unsupported average speed operation: {op}")
