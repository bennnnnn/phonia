"""Friction and inclined-plane solvers: N = mg cos(theta), f = mu N,
a = g (sin(theta) - mu cos(theta)).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import (
    PhysicsIntent,
    SimulationAngle,
    SimulationBlockSpec,
    SimulationBody,
    SimulationVector,
)
from app.modules.physics.schemas.simulation import ArrowKind
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import gravity_of, params_in_si
from app.services.solving import SolveServiceError


@dataclass(frozen=True)
class _Incline:
    """What every friction operation reads: the givens in SI, g, mu, the angle and N."""

    p: dict[str, float]
    g: float
    mu: float
    theta: float
    deg: float
    normal: float
    m: float


def solve_friction(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or "friction_force"
    g = gravity_of(p)
    mu = p.get("mu", 0.0)
    theta = p.get("angle", 0.0)  # radians
    if g <= 0:
        raise SolveServiceError("gravity must be positive")
    if mu < 0:
        raise SolveServiceError("coefficient of friction cannot be negative")
    if not -math.pi / 2 < theta < math.pi / 2:
        raise SolveServiceError("incline angle must be between -90 and 90 degrees")

    deg = math.degrees(theta)
    # Mass cancels out of the incline acceleration, so it is optional there and
    # only these two branches require it.
    if op in ("normal_force", "friction_force") and "m" not in p:
        raise SolveServiceError(f"{op} needs a mass")
    normal = p.get("m", 0.0) * g * math.cos(theta)
    m = p.get("m", 0.0)

    solve = _FRICTION_OPS.get(op)
    if solve is None:
        raise SolveServiceError(f"unsupported friction op: {op}")
    return solve(_Incline(p, g, mu, theta, deg, normal, m))


def _incline_sliding(s: _Incline) -> PhysicsResult:
    p, g, theta, deg, m = s.p, s.g, s.theta, s.deg, s.m
    mu_s = p.get("mu_s")
    if mu_s is None:
        raise SolveServiceError("a static-friction coefficient is required")
    if mu_s < 0:
        raise SolveServiceError("static-friction coefficient cannot be negative")
    if "m" in p and m <= 0:
        raise SolveServiceError("mass must be positive")

    downhill_ratio = math.sin(theta)
    static_ratio = mu_s * math.cos(theta)
    slides = downhill_ratio - static_ratio > 1e-12
    decision = "Yes, it starts sliding." if slides else "No, it stays at rest."
    formulas = (
        r"F_{g,\parallel}=mg\sin\theta",
        r"f_{s,\max}=\mu_sN=\mu_smg\cos\theta",
        r"\text{It starts sliding if }F_{g,\parallel}>f_{s,\max}",
    )
    if "m" in p:
        downhill = m * g * downhill_ratio
        maximum_static = m * g * static_ratio
        substitutions = (
            rf"F_{{g,\parallel}}={m:g}\cdot{g:g}\cdot\sin({deg:g}^\circ)"
            rf"\approx {downhill:.2f}\,\text{{N}}",
            rf"f_{{s,\max}}={mu_s:g}\cdot{m:g}\cdot{g:g}"
            rf"\cdot\cos({deg:g}^\circ)\approx {maximum_static:.2f}\,\text{{N}}",
            (
                rf"{downhill:.2f}\,\text{{N}} > {maximum_static:.2f}\,\text{{N}}"
                if slides
                else rf"{downhill:.2f}\,\text{{N}} \le {maximum_static:.2f}\,\text{{N}}"
            ),
        )
    else:
        substitutions = (
            rf"\sin({deg:g}^\circ)\approx {downhill_ratio:.4f}",
            rf"{mu_s:g}\cos({deg:g}^\circ)\approx {static_ratio:.4f}",
            (
                rf"{downhill_ratio:.4f} > {static_ratio:.4f}"
                if slides
                else rf"{downhill_ratio:.4f} \le {static_ratio:.4f}"
            ),
        )
    return PhysicsResult(
        answer=decision,
        answer_value=decision,
        answer_latex=rf"\text{{{decision}}}",
        formulas=formulas,
        substitutions=substitutions,
    )


def _normal_force(s: _Incline) -> PhysicsResult:
    p, g, mu, theta, deg, normal, m = s.p, s.g, s.mu, s.theta, s.deg, s.normal, s.m
    if theta == 0:
        plugged = rf"{m:g} \cdot {g:g}"
        answer = rf"N = m g = {plugged} \approx {normal:.2f} \text{{ N}}"
        formula = r"N = m g"
    else:
        plugged = rf"{m:g} \cdot {g:g} \cdot \cos({deg:g}^\circ)"
        answer = rf"N = m g \cos\theta = {plugged} \approx {normal:.2f} \text{{ N}}"
        formula = r"N = m g \cos\theta"
    return PhysicsResult(
        answer=answer,
        formulas=(formula,),
        substitutions=(rf"N = {plugged}",),
        quantities=(QuantityResult("", normal, "N"),),
        simulation_specs=incline_scene(
            deg, mu=mu, held=bool(p.get("static_equilibrium")), mass=m, g=g
        )
        or _floor_scene(m, g, asked="normal"),
    )


def _friction_force(s: _Incline) -> PhysicsResult:
    p, g, mu, theta, deg, normal, m = s.p, s.g, s.mu, s.theta, s.deg, s.normal, s.m
    f_val = mu * normal
    if p.get("static_equilibrium"):
        f_val = m * g * abs(math.sin(theta))
        # A stated coefficient bounds what static friction can hold; with
        # none stated, the block resting there is the statement that it can.
        if "mu" in p and f_val > mu * normal + 1e-12:
            raise SolveServiceError("static friction cannot hold the stated equilibrium")
        return PhysicsResult(
            answer=rf"f_s = mg|\sin\theta| = {f_val:g} \text{{ N}}",
            formulas=(r"f_s = mg|\sin\theta|", r"f_s \le \mu_s N"),
            substitutions=(rf"f_s = {m:g}\cdot {g:g}\cdot |\sin({deg:g}^\circ)|",),
            quantities=(QuantityResult("", f_val, "N"),),
            simulation_specs=incline_scene(deg, mu=mu, held=f_val > 0, mass=m, g=g),
        )
    answer = rf"f = \mu N = {mu:g} \cdot {normal:.2f} \approx {f_val:.2f} \text{{ N}}"
    return PhysicsResult(
        answer=answer,
        formulas=(r"f = \mu N",),
        substitutions=(rf"f = {mu:g} \cdot {normal:.2f}",),
        quantities=(QuantityResult("", f_val, "N"),),
        simulation_specs=incline_scene(
            deg, mu=mu, uphill=p.get("motion_sign") == -1, mass=m or None, g=g
        )
        or _floor_scene(m, g, friction=f_val, asked="friction"),
    )


def _incline_acceleration(s: _Incline) -> PhysicsResult:
    p, g, mu, theta, deg, m = s.p, s.g, s.mu, s.theta, s.deg, s.m
    motion = p.get("motion_sign", 0.0)
    if motion not in {-1.0, 0.0, 1.0}:
        raise SolveServiceError("unsupported incline motion direction")
    if p.get("static_equilibrium"):
        if abs(math.tan(theta)) > mu:
            raise SolveServiceError("static friction cannot hold the stated equilibrium")
        a_val = 0.0
    else:
        a_val = g * (math.sin(theta) - (-1 if motion < 0 else 1) * mu * math.cos(theta))
    if (a_val <= 0 and motion == 0) or p.get("static_equilibrium"):
        # tan(theta) <= mu: static friction holds it. Reporting a negative
        # acceleration would describe the block sliding *up* the slope on
        # its own, which is not what the equation means here.
        return PhysicsResult(
            answer=(
                rf"\tan({deg:g}^\circ) \le \mu = {mu:g}, "
                r"\text{so friction holds the block: } a = 0 \text{ m/s}^2"
            ),
            formulas=(
                rf"\tan({deg:g}^\circ) \le \mu = {mu:g}, "
                r"\text{so friction holds the block: } a",
            ),
            substitutions=(r"a = 0 \text{ m/s}^2",),
            quantities=(QuantityResult("a", 0.0, "m/s^2"),),
            # a = 0 is the answer, so the block stays put and the diagram
            # is the free body that explains why.
            simulation_specs=incline_scene(deg, mu=mu, mass=m or None, g=g),
        )
    sign = "+" if motion < 0 else "-"
    formula = rf"a = g(\sin\theta {sign} \mu\cos\theta)"
    substituted = rf"a = {g:g}(\sin({deg:g}^\circ) {sign} {mu:g}\cos({deg:g}^\circ))"
    answer = (
        formula + " = " + substituted.split(" = ", 1)[1] + " "
        rf"\approx {a_val:.2f} \text{{ m/s}}^2"
    )
    return PhysicsResult(
        answer=answer,
        formulas=(formula + (r"\quad\text{(downhill positive)}" if motion else ""),),
        substitutions=(substituted,),
        quantities=(QuantityResult("", a_val, "m/s^2"),),
        # Initial rest is a supplied initial condition, not current
        # equilibrium. Other moving bodies have no stated initial speed.
        simulation_specs=incline_scene(
            deg,
            mu=mu,
            # Sliding down, it speeds up at a whatever speed it started
            # with, so the drawing starts it from rest; sliding up, it
            # slows, and a block shown starting from rest would go down.
            accel=a_val if motion >= 0 or p.get("released_from_rest") else None,
            uphill=motion < 0,
            mass=m or None,
            g=g,
        ),
    )


def _friction_coefficient(s: _Incline) -> PhysicsResult:
    theta, deg = s.theta, s.deg
    mu_val = math.tan(theta)
    return PhysicsResult(
        answer=(rf"\mu = \tan(\theta) = \tan({deg:.1f}^\circ) \approx {mu_val:.2f}"),
        formulas=(r"\mu = \tan(\theta)",),
        substitutions=(rf"\mu = \tan({deg:.1f}^\circ)",),
        quantities=(QuantityResult("", mu_val, ""),),
        simulation_specs=incline_scene(deg, mu=mu_val, asked="angle"),
    )


def _minimum_force(s: _Incline) -> PhysicsResult:
    g, mu, m = s.g, s.mu, s.m
    f_val = mu * m * g
    return PhysicsResult(
        answer=(
            rf"F_{{min}} = \mu m g = {mu:g} \cdot {m:g} \cdot {g:g} "
            rf"\approx {f_val:.2f} \text{{ N}}"
        ),
        formulas=(r"F_{min} = \mu m g",),
        substitutions=(rf"F_{{min}} = {mu:g} \cdot {m:g} \cdot {g:g}",),
        quantities=(QuantityResult("", f_val, "N"),),
        simulation_specs=_floor_scene(m, g, friction=f_val, applied=f_val, asked="applied")
        if m > 0
        else [],
    )


_FRICTION_OPS: dict[str, Callable[[_Incline], PhysicsResult]] = {
    "incline_sliding": _incline_sliding,
    "normal_force": _normal_force,
    "friction_force": _friction_force,
    "incline_acceleration": _incline_acceleration,
    "friction_coefficient": _friction_coefficient,
    "minimum_force": _minimum_force,
}


# The slope's own length is never stated, so it is a display choice and the
# scene is drawn at a fixed one. The same reasoning as the SHM curve's
# normalised amplitude: what the question is about is the *shape* of the
# motion — a block that starts slow and speeds up — and that shape is real
# whatever the slope measures. Inventing a number for the answer would be a
# different thing entirely.
_INCLINE_LENGTH = 6.0


def incline_scene(
    deg: float,
    *,
    mu: float,
    accel: float | None = None,
    uphill: bool = False,
    held: bool = False,
    mass: float | None = None,
    g: float | None = None,
    asked: str | None = None,
    along: float | None = None,
) -> list[SimulationBlockSpec]:
    """A block on a slope with its weight, normal and friction arrows.

    Mostly a *diagram*: a free-body picture is what an incline question wants,
    and for two of the three ops the block is not moving at all. The arrows
    carry their values when the mass is known, and the slope its angle.
    ``along`` is the weight's component down the slope, drawn when asked.

    A flat surface is `_floor_scene`'s.
    """
    if deg == 0:
        return []
    theta = math.radians(abs(deg))
    # Descending left to right, which fixes what "down the slope" means for
    # both the path and the arrows.
    down_x, down_y = math.cos(theta), -math.sin(theta)
    top_x, top_y = 0.0, _INCLINE_LENGTH * math.sin(theta)
    size = _INCLINE_LENGTH * 0.06
    # The box sits on the slope: its centre is half a side off the surface.
    lift_x, lift_y = math.sin(theta) * size, math.cos(theta) * size

    n_points = 60
    if accel is not None and accel > 0:
        # s = ½at², sampled uniformly in *time*, so the block visibly
        # accelerates rather than sliding at a constant rate. The duration is
        # the one that covers the drawn slope, so the block arrives at the
        # bottom exactly as the animation ends.
        duration = math.sqrt(2 * _INCLINE_LENGTH / accel)
        dt = duration / (n_points - 1)
        distances = [0.5 * accel * (i * dt) ** 2 for i in range(n_points)]
    else:
        # Held by friction, or an op with no acceleration to show: the block
        # stays where it is and the arrows are the whole picture.
        distances = [0.0] * n_points

    start = 0.12 * _INCLINE_LENGTH
    path = [
        [
            round(top_x + (start + s) * down_x + lift_x, 4),
            round(top_y + (start + s) * down_y + lift_y, 4),
        ]
        for s in distances
    ]
    arrows: list[ArrowKind] = ["gravity", "normal"]
    # Static friction holds a resting block whether or not μ was stated.
    if (mu > 0 or held) and not uphill:
        arrows.append("friction")

    labels: dict[ArrowKind, str] = {"gravity": "mg", "normal": "N", "friction": "f"}
    if mass and g:
        weight = mass * g
        normal = weight * math.cos(theta)
        labels["gravity"] = f"mg = {plain_number(weight)} N"
        labels["normal"] = f"N = {plain_number(normal)} N"
        if held:
            labels["friction"] = f"f = {plain_number(weight * math.sin(theta))} N"
        elif mu > 0:
            labels["friction"] = f"f = {plain_number(mu * normal)} N"
    foot = _INCLINE_LENGTH * math.cos(theta)
    margin = _INCLINE_LENGTH * 0.18
    shown = f"{plain_number(abs(deg), GIVEN_FIGURES)}°"
    return [
        SimulationBlockSpec(
            type="incline",
            title="Inclined Plane",
            title_key="incline",
            bodies=[
                SimulationBody(
                    path=path,
                    radius=size,
                    shape="box",
                    label=f"{plain_number(mass, GIVEN_FIGURES)} kg" if mass else None,
                )
            ],
            x_min=-margin,
            x_max=foot + margin,
            y_min=-margin,
            y_max=top_y + margin,
            ground=True,
            arrows=arrows,
            arrow_labels={name: labels[name] for name in arrows},
            angles=[
                SimulationAngle(
                    vertex=[foot, 0.0],
                    start_deg=180.0 - abs(deg),
                    end_deg=180.0,
                    label=shown,
                    role="result" if asked == "angle" else "given",
                )
            ],
            vectors=[SimulationVector(anchor=path[0], dx=down_x, dy=down_y)]
            if uphill and mu > 0
            else [
                SimulationVector(
                    anchor=[0.0, 0.0],
                    dx=down_x,
                    dy=down_y,
                    label=f"mg sin θ = {plain_number(along)} N",
                    role="result",
                    body=0,
                )
            ]
            if along is not None
            else [],
            # The angle arrived here through radians, so 30 comes back as
            # 29.999999999999996 and would ship in the fence JSON that way.
            incline_deg=round(abs(deg), 4),
            alt=_incline_alt(shown, mass, accel, held, along=along, friction="friction" in arrows),
        )
    ]


def _incline_alt(
    shown: str,
    mass: float | None,
    accel: float | None,
    held: bool,
    *,
    along: float | None = None,
    friction: bool = True,
) -> str:
    block = f"A {plain_number(mass, GIVEN_FIGURES)} kg block" if mass else "A block"
    if along is not None:
        return (
            f"{block} on a {shown} slope; its weight pulls it down the slope "
            f"with {plain_number(along)} N."
        )
    if accel:
        return f"{block} sliding down a {shown} slope at {plain_number(accel)} m/s²."
    if held:
        return f"{block} held at rest on a {shown} slope by friction."
    if not friction:
        return f"{block} on a {shown} slope, with its weight and the normal force."
    return f"{block} on a {shown} slope, with its weight, the normal force and friction."


def _floor_scene(
    mass: float,
    g: float,
    *,
    friction: float | None = None,
    applied: float | None = None,
    asked: str,
) -> list[SimulationBlockSpec]:
    """A box on a floor: weight, normal, friction against the push, and the push.

    Each arrow carries its size, so a 100 N push against 49 N of friction is
    visibly the longer; the asked one is the highlighted result.
    """
    weight = mass * g
    size = 0.5
    centre = [0.0, size]
    vectors = [
        SimulationVector(
            anchor=[0.0, 0.0],
            dx=0.0,
            dy=-weight,
            label=f"W = {plain_number(weight)} N",
            body=0,
        ),
        SimulationVector(
            anchor=[0.0, 0.0],
            dx=0.0,
            dy=weight,
            label=f"N = {plain_number(weight)} N",
            role="result" if asked == "normal" else "force",
            body=0,
        ),
    ]
    if friction:
        vectors.append(
            SimulationVector(
                anchor=[-size, -size * 0.6],
                dx=-friction,
                dy=0.0,
                label=f"f = {plain_number(friction)} N",
                role="result" if asked == "friction" else "force",
                body=0,
            )
        )
    if applied:
        vectors.append(
            SimulationVector(
                anchor=[size, 0.0],
                dx=applied,
                dy=0.0,
                label=f"F = {plain_number(applied)} N",
                role="result" if asked == "applied" else "force",
                body=0,
            )
        )
    box = f"{plain_number(mass, GIVEN_FIGURES)} kg"
    pieces = [f"weight {plain_number(weight)} N"]
    if friction:
        pieces.append(f"friction {plain_number(friction)} N")
    if applied:
        pieces.append(f"a push of {plain_number(applied)} N")
    return [
        SimulationBlockSpec(
            type="free_body",
            title="Free-Body Diagram",
            title_key="free_body",
            bodies=[SimulationBody(path=[centre, centre], radius=size, shape="box", label=box)],
            vectors=vectors,
            ground=True,
            x_min=-3.0,
            x_max=3.0,
            y_min=-0.5,
            y_max=3.0,
            alt=f"A {box} box on a floor: " + ", ".join(pieces) + ".",
        )
    ]
