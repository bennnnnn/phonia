"""Momentum solvers: p = mv, impulse J = F dt (or m dv), and 1D collisions.

Inelastic: v = (m1 v1 + m2 v2) / (m1 + m2).
Elastic: v1' = ((m1 - m2) v1 + 2 m2 v2) / (m1 + m2), and v2' by symmetry.
"""

from __future__ import annotations

import math

from app.modules.physics.display import GIVEN_FIGURES, latex_given, latex_number, plain_number
from app.modules.physics.schemas import PhysicsIntent, SimulationBlockSpec, SimulationBody
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def _collision_substitutions(intent: PhysicsIntent, *, elastic: bool) -> tuple[str, ...]:
    """Numeric collision rows. The reply reads these; it does not rebuild them."""
    params = params_in_si(intent)
    m1 = latex_given(params["m1"])
    m2 = latex_given(params["m2"])
    v1 = latex_given(params["v1"])
    v2 = latex_given(params["v2"])
    if elastic:
        return (
            rf"v_1' = \frac{{({m1}-{m2})\cdot {v1} + 2\cdot {m2}\cdot {v2}}}{{{m1}+{m2}}}",
            rf"v_2' = \frac{{({m2}-{m1})\cdot {v2} + 2\cdot {m1}\cdot {v1}}}{{{m1}+{m2}}}",
        )
    return (rf"v_f = \frac{{{m1}\cdot {v1} + {m2}\cdot {v2}}}{{{m1}+{m2}}}",)


def solve_momentum(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or "momentum"

    if op == "center_of_mass":
        total_mass = p["m1"] + p["m2"]
        if p["m1"] <= 0 or p["m2"] <= 0 or total_mass <= 0:
            raise SolveServiceError("center of mass needs positive masses")
        center = (p["m1"] * p["x1"] + p["m2"] * p["x2"]) / total_mass
        return PhysicsResult(
            answer=(
                r"x_{cm} = \frac{m_1x_1 + m_2x_2}{m_1 + m_2} = "
                rf"\frac{{{p['m1']:g} \cdot {p['x1']:g} + {p['m2']:g} \cdot {p['x2']:g}}}"
                rf"{{{p['m1']:g} + {p['m2']:g}}} \approx {center:.4g} \text{{ m}}"
            ),
            formulas=(r"x_{cm} = \frac{m_1x_1 + m_2x_2}{m_1 + m_2}",),
            substitutions=(
                rf"x_{{cm}} = \frac{{{p['m1']:g} \cdot {p['x1']:g} + {p['m2']:g} \cdot "
                rf"{p['x2']:g}}}{{{p['m1']:g} + {p['m2']:g}}}",
            ),
            quantities=(QuantityResult("", center, "m"),),
        )

    if op == "momentum":
        p_val = p["m"] * p["v"]
        return PhysicsResult(
            answer=(
                rf"p = m v = {p['m']:g} \cdot {p['v']:g} "
                rf"\approx {p_val:.2f} \text{{ kg}}\cdot\text{{m/s}}"
            ),
            formulas=(r"p = m v",),
            substitutions=(rf"p = {p['m']:g} \cdot {p['v']:g}",),
            quantities=(QuantityResult("", p_val, "kg*m/s"),),
        )

    if op == "impulse":
        v1 = p.get("v1", 0.0)
        if "F" in p and "dt" in p:
            v1 = 0.0
            j_val = p["F"] * p["dt"]
            plugged = rf"{p['F']:g} \cdot {p['dt']:g}"
            answer = rf"J = F \Delta t = {plugged} \approx {j_val:.2f} \text{{ N}}\cdot\text{{s}}"
            formula = r"J = F \Delta t"
            substitution = rf"J = {plugged}"
        else:
            # J = Delta p. Same quantity, same units — N*s and kg*m/s are equal.
            j_val = p["m"] * (p["v2"] - p["v1"])
            plugged = rf"{p['m']:g} \cdot ({latex_num(p['v2'])} - {latex_num(p['v1'])})"
            answer = rf"J = m \Delta v = {plugged} \approx {j_val:.2f} \text{{ N}}\cdot\text{{s}}"
            formula = r"J = m(v_2 - v_1)"
            substitution = rf"J = {plugged}"
        # Against a real initial motion, the size and whether it opposes it.
        # Without one (a force, or a start from rest) the sign is the direction.
        relative = v1 != 0.0
        return PhysicsResult(
            answer=answer,
            formulas=(formula,),
            substitutions=(substitution,),
            quantities=(
                QuantityResult(
                    "",
                    abs(j_val) if relative else j_val,
                    "N*s",
                    detail="opposite to the initial motion" if j_val * v1 < 0 else None,
                ),
            ),
        )

    if op == "final_velocity":
        m1, m2, v1, v2 = p["m1"], p["m2"], p["v1"], p["v2"]
        total = m1 + m2
        if total == 0:
            raise SolveServiceError("colliding masses sum to zero")
        # The extractor refuses an unstated collision type, so this flag is
        # always something the user actually wrote.
        quantities: tuple[QuantityResult, ...]
        formulas: tuple[str, ...]
        if p.get("elastic", 0.0) >= 0.5:
            u1 = ((m1 - m2) * v1 + 2 * m2 * v2) / total
            u2 = ((m2 - m1) * v2 + 2 * m1 * v1) / total
            answer = (
                r"\text{Elastic: } v_1' = \frac{(m_1-m_2)v_1 + 2 m_2 v_2}{m_1+m_2} "
                rf"\approx {u1:.2f} \text{{ m/s}}, \quad v_2' \approx {u2:.2f} \text{{ m/s}}"
            )
            quantities = (
                QuantityResult("", u1, "m/s"),
                QuantityResult("", u2, "m/s"),
            )
            substitutions = _collision_substitutions(intent, elastic=True)
            formulas = (
                r"\text{Elastic: } v_1' = \frac{(m_1-m_2)v_1 + 2 m_2 v_2}{m_1+m_2}",
                r"v_2' = \frac{(m_2-m_1)v_2 + 2 m_1 v_1}{m_1+m_2}",
            )
        else:
            u1 = u2 = (m1 * v1 + m2 * v2) / total
            answer = (
                r"\text{Perfectly inelastic: } v = \frac{m_1 v_1 + m_2 v_2}{m_1 + m_2} = "
                rf"\frac{{{m1:g} \cdot {v1:g} + {m2:g} \cdot {v2:g}}}{{{total:g}}} "
                rf"\approx {u1:.2f} \text{{ m/s}}"
            )
            quantities = (QuantityResult("", u1, "m/s"),)
            substitutions = _collision_substitutions(intent, elastic=False)
            formulas = (r"\text{Perfectly inelastic: } v = \frac{m_1 v_1 + m_2 v_2}{m_1 + m_2}",)
        return PhysicsResult(
            answer=answer,
            quantities=quantities,
            formulas=formulas,
            substitutions=substitutions,
            simulation_specs=[_collision_scene(m1, m2, v1, v2, u1, u2)],
        )

    if op == "collision_energy_lost":
        return _collision_energy_lost(intent, p)

    if op == "explosion_speed":
        return _explosion_speed(p)

    raise SolveServiceError(f"unsupported momentum op: {op}")


def _explosion_speed(p: dict[str, float]) -> PhysicsResult:
    """v₂ = m₁v₁/m₂, the pieces moving apart; a stated whole must be their sum."""
    m1, m2, v1 = p["m_moving"], p["m_other"], p["v_moving"]
    if m1 <= 0 or m2 <= 0 or v1 <= 0:
        raise SolveServiceError("an explosion needs two pieces and a speed")
    total = p.get("m_total")
    if total is not None and not math.isclose(total, m1 + m2, rel_tol=1e-6):
        raise SolveServiceError("the pieces do not add up to the whole")
    v2 = m1 * v1 / m2
    substitution = (
        rf"v_2 = \frac{{{latex_given(m1)}\cdot {latex_given(v1)}}}{{{latex_given(m2)}}}"
        rf" = {latex_number(v2)}"
    )
    first, second = plain_number(m1, GIVEN_FIGURES), plain_number(m2, GIVEN_FIGURES)
    return PhysicsResult(
        answer=substitution,
        formulas=(r"0 = m_1 v_1 - m_2 v_2", r"v_2 = \frac{m_1 v_1}{m_2}"),
        substitutions=(substitution,),
        quantities=(QuantityResult("", v2, "m/s"),),
        simulation_specs=[
            _collision_scene(
                m2,
                m1,
                0.0,
                0.0,
                -v2,
                v1,
                recoil=(
                    f"A body at rest bursts: the {first} kg piece flies off at "
                    f"{plain_number(v1)} m/s and the {second} kg piece the other way "
                    f"at {plain_number(v2)} m/s."
                ),
            )
        ],
    )


def _collision_energy_lost(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    """Kinetic energy before, less the stuck pair's after: ½m₁v₁² + ½m₂v₂² - ½(m₁+m₂)v_f²."""
    m1, m2, v1, v2 = p["m1"], p["m2"], p["v1"], p["v2"]
    total = m1 + m2
    if m1 <= 0 or m2 <= 0 or p.get("elastic", 0.0) >= 0.5:
        raise SolveServiceError("energy lost needs two masses that stick together")
    vf = (m1 * v1 + m2 * v2) / total
    before = 0.5 * m1 * v1 * v1 + 0.5 * m2 * v2 * v2
    after = 0.5 * total * vf * vf
    lost = before - after
    if not math.isfinite(lost) or lost < 0:
        raise SolveServiceError("energy lost is not a real loss")
    g1, g2, s1, s2 = (latex_given(value) for value in (m1, m2, v1, v2))
    substitutions = (
        rf"v_f = \frac{{{g1}\cdot {s1} + {g2}\cdot {s2}}}{{{g1}+{g2}}} = {latex_number(vf)}",
        rf"KE_i = \tfrac{{1}}{{2}}\cdot {g1}\cdot {latex_num(v1, square=True)} + "
        rf"\tfrac{{1}}{{2}}\cdot {g2}\cdot {latex_num(v2, square=True)} = {latex_number(before)}",
        rf"KE_f = \tfrac{{1}}{{2}}\cdot {latex_number(total)}\cdot "
        rf"{latex_num(vf, square=True)} = {latex_number(after)}",
        rf"\Delta KE = {latex_number(before)} - {latex_number(after)} = {latex_number(lost)}",
    )
    return PhysicsResult(
        answer=substitutions[-1],
        formulas=(
            r"v_f = \frac{m_1 v_1 + m_2 v_2}{m_1 + m_2}",
            r"KE_i = \tfrac{1}{2} m_1 v_1^2 + \tfrac{1}{2} m_2 v_2^2",
            r"KE_f = \tfrac{1}{2}(m_1 + m_2) v_f^2",
            r"\Delta KE = KE_i - KE_f",
        ),
        substitutions=substitutions,
        quantities=(QuantityResult("", lost, "J"),),
        simulation_specs=[_collision_scene(m1, m2, v1, v2, vf, vf)],
    )


def _collision_scene(
    m1: float,
    m2: float,
    v1: float,
    v2: float,
    u1: float,
    u2: float,
    *,
    recoil: str | None = None,
) -> SimulationBlockSpec:
    """Two bodies approaching, meeting, and leaving at their new speeds.

    The one thing a number genuinely cannot show. "1.00 m/s and 4.00 m/s" is
    the right answer and says nothing about which ball ends up ahead, whether
    either turns around, or that the pair keeps moving together when they
    stick — all of which the scene shows without a word.

    Contact is the midpoint of the clock, so the approach and the separation
    get equal screen time whatever the speeds. Radii come from the masses (as
    cube roots, since a ball's size goes with its volume), so the heavier body
    reads as the heavier one. ``recoil`` is the alt for two bodies pushing
    apart from rest, which is the same picture under another name.
    """
    r1 = 0.30 * (m1 ** (1 / 3))
    r2 = 0.30 * (m2 ** (1 / 3))
    gap = r1 + r2

    # Long enough for the fastest phase to travel a few body-widths, so a slow
    # body still visibly moves and a fast one does not leave the box.
    fastest = max(abs(v1), abs(v2), abs(u1), abs(u2))
    half = (4 * gap / fastest) if fastest > 0 else 1.0

    n_half = 40
    dt = half / n_half
    path1: list[list[float]] = []
    path2: list[list[float]] = []
    # Two bodies at rest have nothing to show before they push apart: a short
    # pause, then the whole clock on the separation.
    for i in range(-6 if recoil else -n_half, n_half + 1):
        t = i * dt
        if t <= 0:
            # Contact at t = 0 puts the two surfaces together: centres a
            # radius either side of the origin.
            x1, x2 = -r1 + v1 * t, r2 + v2 * t
        else:
            x1, x2 = -r1 + u1 * t, r2 + u2 * t
        path1.append([round(x1, 4), 0.0])
        path2.append([round(x2, 4), 0.0])

    xs = [x for x, _ in path1 + path2]
    margin = gap
    lo, hi = min(xs) - margin, max(xs) + margin
    # A flat track: the bodies only move along x, so the box is wide and short
    # rather than square. Both axes still share one scale, so the balls stay
    # round.
    half_height = max((hi - lo) * 0.18, gap * 1.2)
    return SimulationBlockSpec(
        type="collision",
        bodies=[
            SimulationBody(
                path=path1, radius=r1, label=f"{plain_number(m1, GIVEN_FIGURES)} kg", role="primary"
            ),
            SimulationBody(
                path=path2,
                radius=r2,
                label=f"{plain_number(m2, GIVEN_FIGURES)} kg",
                role="secondary",
            ),
        ],
        x_min=lo,
        x_max=hi,
        y_min=-half_height,
        y_max=half_height,
        arrows=["velocity"],
        arrow_labels={"velocity": "v"},
        title="Recoil" if recoil else "Collision",
        title_key="recoil" if recoil else "collision",
        alt=recoil or _collision_alt(m1, m2, v1, v2, u1, u2),
    )


def _collision_alt(m1: float, m2: float, v1: float, v2: float, u1: float, u2: float) -> str:
    first = f"{plain_number(m1, GIVEN_FIGURES)} kg"
    second = f"{plain_number(m2, GIVEN_FIGURES)} kg"

    def moving(speed: float) -> str:
        return "at rest" if speed == 0 else f"at {plain_number(abs(speed))} m/s"

    before = f"A {first} body {moving(v1)} meets a {second} body {moving(v2)}"
    if math.isclose(u1, u2):
        return f"{before}; they move off together at {plain_number(abs(u1))} m/s."
    return (
        f"{before}; afterwards the {first} body moves {moving(u1)} "
        f"and the {second} body {moving(u2)}."
    )
