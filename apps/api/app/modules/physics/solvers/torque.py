"""Torque solvers: torque, the net torque, a lever arm and the balance of moments."""

from __future__ import annotations

import math
from collections.abc import Callable

from app.modules.physics.display import given_number as _given
from app.modules.physics.display import plain_number
from app.modules.physics.schemas import (
    PhysicsIntent,
    SimulationAngle,
    SimulationBlockSpec,
    SimulationVector,
)
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def _lever_scene(
    loads: list[tuple[float, float, str, bool]],
    *,
    alt: str | None = None,
    angles: list[SimulationAngle] | None = None,
) -> list[SimulationBlockSpec]:
    """A beam on a wedge with a labelled force hanging at each arm.

    The see-saw is how this topic is taught and the one picture that makes
    "written order is not ownership" — the pairing bug P9 found — obvious at a
    glance: the arm each force actually has is drawn where it is, so a diagram
    reading 2 m under the wrong force would be visible rather than silent.

    Each load is (signed distance from the pivot, magnitude, label, is_answer).
    A negative distance is the left arm. The arrows carry the magnitudes, so a
    120 N load out-reaches a 30 N one; the renderer sets the longest's length.
    """
    if not loads:
        return []
    reach = max(abs(d) for d, *_ in loads) * 1.25 or 1.0
    # Arrows hang below the beam, so the box needs room under it as well as a
    # little air above.
    depth = reach * 0.55
    return [
        SimulationBlockSpec(
            type="lever",
            title="Moments",
            title_key="moments",
            alt=alt,
            angles=angles or [],
            beam=[-reach, 0.0, reach, 0.0],
            pivot=[0.0, 0.0],
            vectors=[
                SimulationVector(
                    anchor=[distance, 0.0],
                    dx=0.0,
                    dy=-abs(magnitude) or -1.0,
                    label=label,
                    role="result" if is_answer else "force",
                )
                for distance, magnitude, label, is_answer in loads
            ],
            x_min=-reach * 1.15,
            x_max=reach * 1.15,
            y_min=-depth,
            y_max=depth,
        )
    ]


def solve_torque(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or "torque"

    solve = _TORQUE_OPS.get(op)
    if solve is None:
        raise SolveServiceError(f"unsupported torque op: {op}")
    return solve(p)


def _moment_balance(p: dict[str, float]) -> PhysicsResult:
    if "d2" in p and "F2" not in p:
        f1, d1, d2 = p["F1"], p["d1"], p["d2"]
        if d2 == 0:
            raise SolveServiceError("balancing arm must be nonzero")
        f2 = f1 * d1 / d2
        return PhysicsResult(
            answer=(
                r"F_1 d_1 = F_2 d_2 \Rightarrow F_2 = \frac{F_1 d_1}{d_2}"
                rf" = \frac{{{f1:g} \cdot {d1:g}}}{{{d2:g}}} "
                rf"\approx {f2:.2f} \text{{ N}}"
            ),
            formulas=(r"F_2 = \frac{F_1 d_1}{d_2}",),
            substitutions=(rf"F_2 = \frac{{{f1:g} \cdot {d1:g}}}{{{d2:g}}}",),
            quantities=(QuantityResult("", f2, "N"),),
            simulation_specs=_lever_scene(
                [
                    (-d1, f1, f"{_given(f1)} N at {_given(d1)} m", False),
                    (d2, f2, f"{plain_number(f2)} N at {_given(d2)} m", True),
                ],
                alt=(
                    f"A beam balanced on a pivot: {_given(f1)} N at {_given(d1)} m on one "
                    f"side, {plain_number(f2)} N at {_given(d2)} m on the other."
                ),
            ),
        )
    uses_masses = "m1" in p and "m2" in p
    f1, d1, f2 = (p["m1"], p["d1"], p["m2"]) if uses_masses else (p["F1"], p["d1"], p["F2"])
    if f2 == 0:
        raise SolveServiceError("balancing force must be nonzero")
    d2 = f1 * d1 / f2
    balance_formula = (
        r"m_1 g d_1 = m_2 g d_2 \Rightarrow d_2 = \frac{m_1 d_1}{m_2}"
        if uses_masses
        else r"F_1 d_1 = F_2 d_2 \Rightarrow d_2 = \frac{F_1 d_1}{F_2}"
    )
    formula = r"d_2 = \frac{m_1 d_1}{m_2}" if uses_masses else r"d_2 = \frac{F_1 d_1}{F_2}"
    substitution = rf"d_2 = \frac{{{f1:g} \cdot {d1:g}}}{{{f2:g}}}"
    unit = "kg" if uses_masses else "N"
    return PhysicsResult(
        answer=(
            rf"{balance_formula} = \frac{{{f1:g} \cdot {d1:g}}}{{{f2:g}}} "
            rf"\approx {d2:.2f} \text{{ m}}"
        ),
        formulas=(formula,),
        substitutions=(substitution,),
        quantities=(QuantityResult("", d2, "m"),),
        # The known load on the left, the one whose arm was the question on
        # the right, so the answer is the arm you can see.
        simulation_specs=_lever_scene(
            [
                (-d1, f1, f"{_given(f1)} {unit} at {_given(d1)} m", False),
                (d2, f2, f"{_given(f2)} {unit} at {plain_number(d2)} m", True),
            ],
            alt=(
                f"A beam balanced on a pivot: {_given(f1)} {unit} at {_given(d1)} m on "
                f"one side, {_given(f2)} {unit} at {plain_number(d2)} m on the other."
            ),
        ),
    )


def _lever_arm(p: dict[str, float]) -> PhysicsResult:
    force = p["F"]
    if force == 0:
        raise SolveServiceError("force must be nonzero to find a lever arm")
    distance = p["tau"] / force
    return PhysicsResult(
        answer=(
            r"\tau = Fd \Rightarrow d = \frac{\tau}{F} = "
            rf"\frac{{{p['tau']:g}}}{{{force:g}}} \approx {distance:.2f} \text{{ m}}"
        ),
        formulas=(r"d = \frac{\tau}{F}",),
        substitutions=(rf"d = \frac{{{p['tau']:g}}}{{{force:g}}}",),
        quantities=(QuantityResult("", distance, "m"),),
        simulation_specs=_lever_scene(
            [(distance, force, f"{_given(force)} N at {plain_number(distance)} m", True)],
            alt=f"A {_given(force)} N force {plain_number(distance)} m from the pivot.",
        ),
    )


def _net_torque(p: dict[str, float]) -> PhysicsResult:
    torques = [value for key, value in p.items() if key.startswith("tau")]
    if len(torques) < 2:
        raise SolveServiceError("net torque needs at least two torques")
    net = sum(torques)
    net_direction = "counterclockwise" if net > 0 else "clockwise" if net < 0 else "balanced"
    terms = " + ".join(f"({value:g})" for value in torques)
    return PhysicsResult(
        answer=(
            rf"\tau_{{net}} = \sum \tau = {terms} \approx {net:.2f} "
            r"\text{ N}\cdot\text{m}"
        ),
        formulas=(r"\tau_{net} = \sum \tau",),
        substitutions=(rf"\tau_{{net}} = {terms}",),
        quantities=(
            QuantityResult(
                "",
                abs(net),
                "N*m",
                detail=net_direction,
            ),
        ),
    )


def _torque(p: dict[str, float]) -> PhysicsResult:
    f, d = p["F"], p["d"]
    theta = p.get("angle")
    if theta is None:
        tau = f * d
        formula = r"\tau = F d"
        substitution = rf"\tau = {f:g} \cdot {d:g}"
        answer = (
            rf"\tau = F d = {f:g} \cdot {d:g} "
            rf"\approx {tau:.2f} \text{{ N}}\cdot\text{{m}}"
        )
        # Square on: straight down, which is what F d assumes.
        direction = (0.0, -1.0)
    else:
        tau = f * d * math.sin(theta)
        deg = math.degrees(theta)
        formula = r"\tau = F d \sin\theta"
        substitution = rf"\tau = {f:g} \cdot {d:g} \cdot \sin({deg:g}^\circ)"
        answer = (
            rf"\tau = F d \sin\theta = {f:g} \cdot {d:g} \cdot \sin({deg:g}^\circ) "
            rf"\approx {tau:.2f} \text{{ N}}\cdot\text{{m}}"
        )
        # Drawn at the angle it was given, so the sin theta in the formula
        # is the thing on screen rather than a factor to take on trust.
        direction = (math.cos(theta), -math.sin(theta))
    # The force is given, not asked: the torque is the answer, and it is
    # not an arrow on the beam.
    # The torque is the answer: a curved arrow round the pivot, turning
    # the way the force turns the beam (a downward push on the right arm
    # is clockwise).
    clockwise = (direction[1] < 0) == (d > 0)
    sweep = (60.0, -30.0) if clockwise else (120.0, 210.0)
    scene = _lever_scene(
        [(d, f, f"{_given(f)} N at {_given(d)} m", False)],
        alt=(
            f"A {_given(f)} N force {_given(d)} m from the pivot turns it "
            f"{'clockwise' if clockwise else 'anticlockwise'} with a torque of "
            f"{plain_number(tau)} N·m."
        ),
        angles=[
            SimulationAngle(
                vertex=[0.0, 0.0],
                start_deg=sweep[0],
                end_deg=sweep[1],
                label=f"τ = {plain_number(tau)} N·m",
                arrow=True,
                role="result",
            )
        ],
    )
    if scene:
        scene[0].vectors[0].dx = direction[0] * abs(f)
        scene[0].vectors[0].dy = direction[1] * abs(f)
    return PhysicsResult(
        answer=answer,
        formulas=(formula,),
        substitutions=(substitution,),
        quantities=(QuantityResult("", tau, "N*m"),),
        simulation_specs=scene,
    )


_TORQUE_OPS: dict[str, Callable[[dict[str, float]], PhysicsResult]] = {
    "moment_balance": _moment_balance,
    "lever_arm": _lever_arm,
    "net_torque": _net_torque,
    "torque": _torque,
}
