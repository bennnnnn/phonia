"""Two stages from rest: speed up, then hold the speed or brake to a stop.

Each stage is worked on its own row, the way a student splits the trip, and the
total is the last row. Worked in SI.
"""

from __future__ import annotations

import math

from app.modules.physics.display import latex_given, latex_number, latex_unit
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError

TWO_STAGE_OPERATIONS = frozenset({"two_stage_distance", "two_stage_time"})


def _q(value: float, unit: str, *, given: bool = False) -> str:
    number = latex_given(value) if given else latex_number(value)
    return f"{number}{latex_unit(unit)}"


def solve_two_stage(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    stated = set(intent.physics_params or {})
    a1, t1, v = p.get("a1"), p.get("t1"), p.get("v_top")
    formulas: list[str] = []
    rows: list[str] = []
    # Stage one, from rest: any two of a₁, t₁ and v give the third.
    if v is None and a1 is not None and t1 is not None:
        v = a1 * t1
        formulas.append(r"v = a_1 t_1")
        rows.append(
            rf"v = {_q(a1, 'm/s^2', given=True)} \cdot {_q(t1, 's', given=True)} = {_q(v, 'm/s')}"
        )
    elif t1 is None and a1 is not None and v is not None:
        t1 = v / a1
        formulas.append(r"t_1 = \frac{v}{a_1}")
        rows.append(
            rf"t_1 = \frac{{{_q(v, 'm/s', given=True)}}}{{{_q(a1, 'm/s^2', given=True)}}}"
            rf" = {_q(t1, 's')}"
        )
    if v is None or t1 is None or v <= 0 or t1 <= 0:
        raise SolveServiceError("two-stage motion needs two of a₁, t₁ and v")
    v_text = _q(v, "m/s", given="v_top" in stated)
    t1_text = _q(t1, "s", given="t1" in stated)
    d1 = v * t1 / 2
    formulas.append(r"d_1 = \tfrac{1}{2} v t_1")
    rows.append(rf"d_1 = \tfrac{{1}}{{2}} \cdot {v_text} \cdot {t1_text} = {_q(d1, 'm')}")

    # Stage two.
    if "t_cruise" in p:
        t2 = p["t_cruise"]
        d2 = v * t2
        formulas.append(r"d_2 = v t_2")
        rows.append(rf"d_2 = {v_text} \cdot {_q(t2, 's', given=True)} = {_q(d2, 'm')}")
    elif "a_brake" in p:
        a2 = abs(p["a_brake"])
        if a2 <= 0:
            raise SolveServiceError("braking needs a deceleration")
        t2 = v / a2
        d2 = v * v / (2 * a2)
        formulas.append(r"d_2 = \frac{v^2}{2 a_2}")
        rows.append(
            rf"d_2 = \frac{{({v_text})^2}}{{2 \cdot {_q(a2, 'm/s^2', given=True)}}} = {_q(d2, 'm')}"
        )
        if intent.physics_op == "two_stage_time":
            formulas.append(r"t_2 = \frac{v}{a_2}")
            rows.append(
                rf"t_2 = \frac{{{v_text}}}{{{_q(a2, 'm/s^2', given=True)}}} = {_q(t2, 's')}"
            )
    elif "t_brake" in p:
        t2 = p["t_brake"]
        d2 = v * t2 / 2
        formulas.append(r"d_2 = \tfrac{1}{2} v t_2")
        t2_text = _q(t2, "s", given=True)
        rows.append(rf"d_2 = \tfrac{{1}}{{2}} \cdot {v_text} \cdot {t2_text} = {_q(d2, 'm')}")
    elif "d_total" in p:
        d_total = p["d_total"]
        d2 = d_total - d1
        if d2 < 0:
            # The distance ends before the top speed is reached: not a second stage.
            raise SolveServiceError("the stated distance ends during the first stage")
        t2 = d2 / v
        formulas.extend((r"d_2 = d - d_1", r"t_2 = \frac{d_2}{v}"))
        rows.extend(
            (
                rf"d_2 = {_q(d_total, 'm', given=True)} - {_q(d1, 'm')} = {_q(d2, 'm')}",
                rf"t_2 = \frac{{{_q(d2, 'm')}}}{{{v_text}}} = {_q(t2, 's')}",
            )
        )
    else:
        raise SolveServiceError("two-stage motion needs its second stage")
    if not all(math.isfinite(value) and value >= 0 for value in (d1, d2, t2)):
        raise SolveServiceError("two-stage motion is not finite")

    if intent.physics_op == "two_stage_time":
        total = t1 + t2
        formulas.append(r"t = t_1 + t_2")
        rows.append(rf"t = {t1_text} + {_q(t2, 's')} = {_q(total, 's')}")
        unit = "s"
    else:
        total = d1 + d2
        formulas.append(r"d = d_1 + d_2")
        rows.append(rf"d = {_q(d1, 'm')} + {_q(d2, 'm')} = {_q(total, 'm')}")
        unit = "m"
    return PhysicsResult(
        answer=rows[-1],
        formulas=tuple(formulas),
        substitutions=tuple(rows),
        quantities=(QuantityResult("", total, unit),),
    )
