"""Force solvers: F = ma, rope tension, resultant and resolved forces, and the Atwood machine."""

from __future__ import annotations

import math
from collections.abc import Callable

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import PhysicsIntent, SimulationVector
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.force_scenes import (
    _atwood_scene,
    _vector_sum_scene,
    free_body_scene,
)
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import gravity_of, params_in_si
from app.services.solving import SolveServiceError


def solve_force(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op
    # Rope and vector shapes by name; anything else is the F/m/a triangle.
    solver = _OPERATIONS.get(op or "")
    if solver is not None:
        return solver(intent, p)
    return _newton_second_law(intent, p)


# A rope's tension is not m*a, which is exactly the confusion P2 refused
# rather than let ship.
def _tension(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    m = p["m"]
    if m <= 0:
        raise SolveServiceError("mass must be positive")
    g = gravity_of(p)
    a = p.get("a", 0.0)
    if a <= -g:
        raise SolveServiceError("the rope goes slack at or beyond free fall")
    t_val = m * (g + a)
    return PhysicsResult(
        answer=(
            rf"T = m(g + a) = {m:g}({g:g} + {latex_num(a)}) "
            rf"\approx {t_val:.2f} \text{{ N}}"
        ),
        formulas=(r"T = m(g + a)",),
        substitutions=(rf"T = {m:g}({g:g} + {latex_num(a)})",),
        quantities=(QuantityResult("", t_val, "N"),),
        # Two arrows and a mass is the whole of this problem, and seeing
        # them is what makes T = m(g + a) rather than m*a obvious: the rope
        # carries the weight *and* the acceleration.
        simulation_specs=free_body_scene(
            [
                SimulationVector(
                    anchor=[0.0, 0.0],
                    dx=0.0,
                    dy=t_val or 1.0,
                    label=f"T = {plain_number(t_val)} N",
                    role="result",
                ),
                SimulationVector(
                    anchor=[0.0, 0.0],
                    dx=0.0,
                    dy=-(m * g),
                    label=f"W = {plain_number(m * g)} N",
                ),
            ],
            label=f"{plain_number(m, GIVEN_FIGURES)} kg",
            alt=(
                f"A {plain_number(m, GIVEN_FIGURES)} kg mass on a rope: the tension "
                f"{plain_number(t_val)} N pulls up against its {plain_number(m * g)} N weight."
            ),
        ),
    )


def _resultant_force(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    f1, f2 = p["F1"], p["F2"]
    phi = p["angle"]  # radians (converted by params_in_si)
    # The general parallelogram law. At phi = 90 degrees the cosine term
    # drops out and it reduces to Pythagoras, so the perpendicular case
    # needs no separate branch.
    r_val = math.sqrt(f1 * f1 + f2 * f2 + 2 * f1 * f2 * math.cos(phi))
    theta = math.degrees(math.atan2(f2 * math.sin(phi), f1 + f2 * math.cos(phi)))
    return PhysicsResult(
        answer=(
            rf"R = \sqrt{{F_1^2 + F_2^2 + 2F_1F_2\cos\phi}} = "
            rf"\sqrt{{{latex_num(f1, square=True)} + {latex_num(f2, square=True)} + "
            rf"2 \cdot {f1:g} \cdot {f2:g}\cos({math.degrees(phi):g}^\circ)}} "
            rf"\approx {r_val:.2f} \text{{ N}}, \quad "
            rf"\theta = \arctan\frac{{F_2\sin\phi}}{{F_1 + F_2\cos\phi}} "
            rf"= \arctan\frac{{{f2:g}\sin({math.degrees(phi):g}^\circ)}}"
            rf"{{{f1:g} + {f2:g}\cos({math.degrees(phi):g}^\circ)}} "
            rf"\approx {theta:.2f}^\circ"
        ),
        formulas=(
            r"R = \sqrt{F_1^2 + F_2^2 + 2F_1F_2\cos\phi}",
            r"\theta = \arctan\frac{F_2\sin\phi}{F_1 + F_2\cos\phi}",
        ),
        substitutions=(
            rf"R = \sqrt{{{latex_num(f1, square=True)} + {latex_num(f2, square=True)} + 2 "
            rf"\cdot {f1:g} \cdot {f2:g}\cos({math.degrees(phi):g}^\circ)}}",
            rf"\theta = \arctan\frac{{{f2:g}\sin({math.degrees(phi):g}^\circ)}}{{{f1:g} + "
            rf"{f2:g}\cos({math.degrees(phi):g}^\circ)}}",
        ),
        quantities=(
            QuantityResult(
                "",
                r_val,
                "N",
                detail=f"{theta:.2f}°",
                detail_style="at",
            ),
        ),
        simulation_specs=_vector_sum_scene(
            [
                SimulationVector(
                    anchor=[0.0, 0.0],
                    dx=f1,
                    dy=0.0,
                    label=f"{plain_number(f1, GIVEN_FIGURES)} N",
                ),
                SimulationVector(
                    anchor=[0.0, 0.0],
                    dx=f2 * math.cos(phi),
                    dy=f2 * math.sin(phi),
                    label=f"{plain_number(f2, GIVEN_FIGURES)} N",
                ),
            ],
            SimulationVector(
                anchor=[0.0, 0.0],
                dx=r_val * math.cos(math.radians(theta)),
                dy=r_val * math.sin(math.radians(theta)),
                label=f"{plain_number(r_val)} N",
                role="result",
            ),
            alt=(
                f"Forces of {plain_number(f1, GIVEN_FIGURES)} N and "
                f"{plain_number(f2, GIVEN_FIGURES)} N add to {plain_number(r_val)} N "
                f"at {plain_number(theta)}°."
            ),
        ),
    )


def _resolve_force(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    f = p["F"]
    theta = p["angle"]  # radians
    fx = f * math.cos(theta)
    fy = f * math.sin(theta)
    return PhysicsResult(
        answer=(
            rf"F_x = F\cos\theta = {f:g}\cos({math.degrees(theta):g}^\circ) "
            rf"\approx {fx:.2f} \text{{ N}}, \quad "
            rf"F_y = F\sin\theta = {f:g}\sin({math.degrees(theta):g}^\circ) "
            rf"\approx {fy:.2f} \text{{ N}}"
        ),
        formulas=(r"F_x = F\cos\theta", r"F_y = F\sin\theta"),
        substitutions=(
            rf"F_x = {f:g}\cos({math.degrees(theta):g}^\circ)",
            rf"F_y = {f:g}\sin({math.degrees(theta):g}^\circ)",
        ),
        quantities=(
            QuantityResult("", fx, "N", detail="horizontally", detail_style="suffix"),
            QuantityResult("", fy, "N", detail="vertically", detail_style="suffix"),
        ),
        simulation_specs=_vector_sum_scene(
            [
                SimulationVector(anchor=[0.0, 0.0], dx=fx, dy=0.0, label=f"{plain_number(fx)} N"),
                SimulationVector(anchor=[fx, 0.0], dx=0.0, dy=fy, label=f"{plain_number(fy)} N"),
            ],
            SimulationVector(
                anchor=[0.0, 0.0],
                dx=fx,
                dy=fy,
                label=f"{plain_number(f, GIVEN_FIGURES)} N",
                role="result",
            ),
            alt=(
                f"A {plain_number(f, GIVEN_FIGURES)} N force split into "
                f"{plain_number(fx)} N across and {plain_number(fy)} N up."
            ),
        ),
    )


def _atwood(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    m1, m2 = sorted((p["m1"], p["m2"]), reverse=True)
    if m1 <= 0 or m2 <= 0:
        raise SolveServiceError("masses must be positive")
    g = gravity_of(p)
    a_val = (m1 - m2) * g / (m1 + m2)
    t_val = 2 * m1 * m2 * g / (m1 + m2)
    return PhysicsResult(
        answer=(
            rf"a = \frac{{(m_1 - m_2)g}}{{m_1 + m_2}} = "
            rf"\frac{{({m1:g} - {m2:g}) \cdot {g:g}}}{{{m1:g} + {m2:g}}} "
            rf"\approx {a_val:.2f} \text{{ m/s}}^2, \quad "
            rf"T = \frac{{2 m_1 m_2 g}}{{m_1 + m_2}} = "
            rf"\frac{{2 \cdot {m1:g} \cdot {m2:g} \cdot {g:g}}}{{{m1:g} + {m2:g}}} "
            rf"\approx {t_val:.2f} \text{{ N}}"
        ),
        formulas=(r"a = \frac{(m_1 - m_2)g}{m_1 + m_2}", r"T = \frac{2 m_1 m_2 g}{m_1 + m_2}"),
        substitutions=(
            rf"a = \frac{{({m1:g} - {m2:g}) \cdot {g:g}}}{{{m1:g} + {m2:g}}}",
            rf"T = \frac{{2 \cdot {m1:g} \cdot {m2:g} \cdot {g:g}}}{{{m1:g} + {m2:g}}}",
        ),
        quantities=(
            QuantityResult("", a_val, "m/s^2"),
            QuantityResult("", t_val, "N"),
        ),
        simulation_specs=_atwood_scene(m1, m2, a_val, t_val),
    )


def _table_pulley(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    """A block m₁ on a frictionless table pulled over a pulley by a hanging m₂."""
    m1, m2 = p["m1"], p["m2"]
    if m1 <= 0 or m2 <= 0:
        raise SolveServiceError("masses must be positive")
    g = gravity_of(p)
    a_val = m2 * g / (m1 + m2)
    t_val = m1 * a_val
    a_row = rf"a = \frac{{{m2:g} \cdot {g:g}}}{{{m1:g} + {m2:g}}}"
    t_row = rf"T = {m1:g} \cdot \frac{{{m2:g} \cdot {g:g}}}{{{m1:g} + {m2:g}}}"
    return PhysicsResult(
        answer=(
            rf"a = \frac{{m_2 g}}{{m_1 + m_2}} = {a_row.split(' = ', 1)[1]} "
            rf"\approx {a_val:.2f} \text{{ m/s}}^2, \quad "
            rf"T = m_1 a = {t_row.split(' = ', 1)[1]} \approx {t_val:.2f} \text{{ N}}"
        ),
        formulas=(r"a = \frac{m_2 g}{m_1 + m_2}", r"T = m_1 a"),
        substitutions=(a_row, t_row),
        quantities=(
            QuantityResult("", a_val, "m/s^2"),
            QuantityResult("", t_val, "N"),
        ),
    )


def _newton_second_law(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if "F" in p and "m" in p and "a" not in p:
        a_val = p["F"] / p["m"]
        plugged = rf"\frac{{{p['F']:g}}}{{{p['m']:g}}}"
        answer_latex = rf"a = \frac{{F}}{{m}} = {plugged} \approx {a_val:.2f} \text{{ m/s}}^2"
        formula = r"a = \frac{F}{m}"
        substitution = rf"a = {plugged}"
        quantity = QuantityResult("", a_val, "m/s^2")
    elif "F" in p and "a" in p and "m" not in p:
        m_val = p["F"] / p["a"]
        plugged = rf"\frac{{{p['F']:g}}}{{{p['a']:g}}}"
        answer_latex = rf"m = \frac{{F}}{{a}} = {plugged} \approx {m_val:.2f} \text{{ kg}}"
        formula = r"m = \frac{F}{a}"
        substitution = rf"m = {plugged}"
        quantity = QuantityResult("", m_val, "kg")
    elif "m" in p and "a" in p and "F" not in p:
        f_val = p["m"] * p["a"]
        plugged = rf"{p['m']:g} \cdot {p['a']:g}"
        answer_latex = rf"F = m \cdot a = {plugged} \approx {f_val:.2f} \text{{ N}}"
        formula = r"F = m \cdot a"
        substitution = rf"F = {plugged}"
        quantity = QuantityResult("", f_val, "N")
    else:
        raise SolveServiceError("force solve needs exactly two of F, m, a")

    # F = ma is a push and the motion it produces, drawn the same way round.
    # Both point right by convention — the question states no direction, and
    # inventing opposing ones would say the block is being decelerated. The
    # acceleration is a `motion` arrow: drawn like a force, it would teach
    # that ma is one more force on the block.
    force = p.get("F", p.get("m", 0.0) * p.get("a", 0.0))
    accel = p.get("a", p.get("F", 0.0) / p["m"] if p.get("m") else 0.0)
    scene = free_body_scene(
        [
            SimulationVector(
                anchor=[0.0, 0.0],
                dx=1.0,
                dy=0.0,
                label=f"F = {plain_number(force)} N",
                role="result" if "F" not in p else "force",
            ),
            SimulationVector(
                anchor=[0.0, -0.9],
                dx=1.0,
                dy=0.0,
                label=f"a = {plain_number(accel)} m/s²",
                role="motion",
            ),
        ],
        label=f"{plain_number(p['m'], GIVEN_FIGURES)} kg" if "m" in p else None,
        alt=(
            f"A net force of {plain_number(force)} N gives an acceleration of "
            f"{plain_number(accel)} m/s² in the same direction."
        ),
        shape="box",
    )
    return PhysicsResult(
        answer=answer_latex,
        formulas=(formula,),
        substitutions=(substitution,),
        quantities=(quantity,),
        simulation_specs=scene,
    )


_OPERATIONS: dict[str, Callable[[PhysicsIntent, dict[str, float]], PhysicsResult]] = {
    "tension": _tension,
    "resultant_force": _resultant_force,
    "resolve_force": _resolve_force,
    "atwood": _atwood,
    "table_pulley": _table_pulley,
}
