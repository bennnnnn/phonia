"""Circular-motion solvers: centripetal force and acceleration, period and angular speed."""

from __future__ import annotations

import math

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import (
    PhysicsIntent,
    SimulationBlockSpec,
    SimulationBody,
    SimulationPlanet,
    SimulationTether,
)
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def _orbit_scene(
    r: float,
    *,
    planet: tuple[float, str | None] | None = None,
    arrow_labels: dict[str, str] | None = None,
    tether: bool = False,
    alt: str | None = None,
) -> SimulationBlockSpec:
    """One lap, sampled at a constant angular step.

    Every circular answer is a number about something going round, and going
    round is the one motion a still picture cannot show at all — which is why
    this kind drew nothing before P14 and why it is the first scene after
    projectiles. The index is the clock here as everywhere else: a constant
    angular step is a constant speed, which is what uniform circular motion is.

    ``planet`` (radius, name) draws what an orbit goes round, at true scale;
    ``tether`` the string a ball on a string turns on.
    """
    n_points = 96
    path = [
        [
            r * math.cos(2 * math.pi * i / (n_points - 1)),
            r * math.sin(2 * math.pi * i / (n_points - 1)),
        ]
        for i in range(n_points)
    ]
    margin = r * 1.35
    return SimulationBlockSpec(
        type="orbit",
        title="Orbit" if planet else "Circular Motion",
        title_key="satellite" if planet else "circular_motion",
        bodies=[SimulationBody(path=path, radius=r * (0.04 if planet else 0.08))],
        x_min=-margin,
        x_max=margin,
        y_min=-margin,
        y_max=margin,
        arrows=["velocity", "centripetal"],
        # The labels are keyed by the arrows listed above; the scene validates them.
        arrow_labels=arrow_labels or {},  # type: ignore[arg-type]
        centre=[0.0, 0.0],
        central_body=SimulationPlanet(radius=planet[0], label=planet[1]) if planet else None,
        tethers=[SimulationTether(anchor=[0.0, 0.0], body=0)] if tether else [],
        alt=alt,
    )


def _road_result(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult | None:
    """Banked curve, level curve, and the speed where the contact force is zero."""
    op = intent.physics_op or ""
    if op not in {"banked_speed", "banked_angle", "level_curve_speed", "contact_speed"}:
        return None
    radius = p.get("r", 0.0)
    gravity = p.get("g", 0.0)
    if radius <= 0 or gravity <= 0:
        raise SolveServiceError("radius and g must be positive")
    if op == "banked_speed":
        angle = p.get("angle", 0.0)
        if angle <= 0 or angle >= math.pi / 2:
            raise SolveServiceError("bank angle must be between 0 and 90 degrees")
        speed = math.sqrt(radius * gravity * math.tan(angle))
        formula = r"v=\sqrt{rg\tan\theta}"
        degrees = math.degrees(angle)
        plugged = rf"v=\sqrt{{{radius:g}\cdot {gravity:g}\cdot \tan {degrees:g}^\circ}}"
        return PhysicsResult(
            answer=formula,
            formulas=(formula,),
            substitutions=(plugged,),
            quantities=(QuantityResult("v", speed, "m/s"),),
            joiner="projectile",
        )
    if op == "banked_angle":
        speed = p.get("v", 0.0)
        if speed <= 0:
            raise SolveServiceError("speed must be positive")
        angle = math.atan(speed**2 / (radius * gravity))
        formula = r"\theta=\arctan\frac{v^{2}}{rg}"
        plugged = rf"\theta=\arctan\frac{{{speed:g}^{{2}}}}{{{radius:g}\cdot {gravity:g}}}"
        return PhysicsResult(
            answer=formula,
            formulas=(formula,),
            substitutions=(plugged,),
            quantities=(QuantityResult(r"\theta", math.degrees(angle), "deg"),),
            joiner="projectile",
        )
    if op == "level_curve_speed":
        mu = p.get("mu", 0.0)
        if mu <= 0:
            raise SolveServiceError("friction coefficient must be positive")
        speed = math.sqrt(mu * radius * gravity)
        formula = r"v=\sqrt{\mu rg}"
        plugged = rf"v=\sqrt{{{mu:g}\cdot {radius:g}\cdot {gravity:g}}}"
        return PhysicsResult(
            answer=formula,
            formulas=(formula,),
            substitutions=(plugged,),
            quantities=(QuantityResult("v", speed, "m/s"),),
            joiner="projectile",
        )
    speed = math.sqrt(radius * gravity)
    formula = r"v=\sqrt{rg}"
    plugged = rf"v=\sqrt{{{radius:g}\cdot {gravity:g}}}"
    return PhysicsResult(
        answer=formula,
        formulas=(formula,),
        substitutions=(plugged,),
        quantities=(QuantityResult("v", speed, "m/s"),),
        joiner="projectile",
    )


def solve_circular(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    road = _road_result(intent, p)
    if road is not None:
        return road
    op = intent.physics_op or "centripetal_acceleration"
    if op == "angular_velocity" and "rpm" in p:
        # params_in_si already turned revolutions per minute into rad/s.
        raw_rpm = (intent.physics_params or {})["rpm"]
        omega_val = p["rpm"]
        return PhysicsResult(
            answer=(
                rf"\omega = n\frac{{2\pi}}{{60}} = {raw_rpm:g}\cdot\frac{{2\pi}}{{60}} "
                rf"\approx {omega_val:.2f} \text{{ rad/s}}"
            ),
            formulas=(r"\omega = n\frac{2\pi}{60}",),
            substitutions=(rf"\omega = {raw_rpm:g}\cdot\frac{{2\pi}}{{60}}",),
            quantities=(QuantityResult("", omega_val, "rad/s"),),
        )
    if op == "angular_velocity" and "period" in p and "v" not in p:
        period = p["period"]
        if period <= 0:
            raise SolveServiceError("period must be positive")
        omega_val = 2 * math.pi / period
        return PhysicsResult(
            answer=(
                rf"\omega = \frac{{2\pi}}{{T}} = \frac{{2\pi}}{{{period:g}}} "
                rf"\approx {omega_val:.2f} \text{{ rad/s}}"
            ),
            formulas=(r"\omega = \frac{2\pi}{T}",),
            substitutions=(rf"\omega = \frac{{2\pi}}{{{period:g}}}",),
            quantities=(QuantityResult("", omega_val, "rad/s"),),
        )
    r = p["r"]
    omega = p.get("omega")
    v = p.get("v", abs(omega) * r if omega is not None else 0.0)
    if r <= 0:
        raise SolveServiceError("radius must be positive")

    shown_r = plain_number(r, GIVEN_FIGURES)
    shown_v = plain_number(abs(v))

    def scene_with(asked: str, value: str) -> list[SimulationBlockSpec]:
        labels = {"velocity": f"v = {shown_v} m/s", "centripetal": "toward the centre"}
        if asked:
            labels["centripetal"] = value
        return [
            _orbit_scene(
                r,
                arrow_labels=labels,
                alt=f"Something going round a circle of radius {shown_r} m at {shown_v} m/s.",
            )
        ]

    scene = scene_with("", "")

    if op == "orbital_period":
        if v == 0:
            raise SolveServiceError("period needs a nonzero speed")
        t_val = 2 * math.pi * r / abs(v)
        if omega is not None and "v" not in p:
            period_formula = r"T = \frac{2\pi}{\omega}"
            period_substitution = rf"T = \frac{{2\pi}}{{{abs(omega):g}}}"
            period_answer = (
                rf"T = \frac{{2\pi}}{{\omega}} = \frac{{2\pi}}{{{abs(omega):g}}} "
                rf"\approx {t_val:.2f} \text{{ s}}"
            )
        else:
            period_formula = r"T = \frac{2\pi r}{v}"
            period_substitution = rf"T = \frac{{2\pi \cdot {r:g}}}{{{abs(v):g}}}"
            period_answer = (
                rf"T = \frac{{2\pi r}}{{v}} = \frac{{2\pi \cdot {r:g}}}{{{abs(v):g}}} "
                rf"\approx {t_val:.2f} \text{{ s}}"
            )
        return PhysicsResult(
            answer=period_answer,
            formulas=(period_formula,),
            substitutions=(period_substitution,),
            quantities=(QuantityResult("", t_val, "s"),),
            simulation_specs=scene,
        )

    if op == "angular_velocity":
        if "v" not in p:
            raise SolveServiceError(
                "angular velocity needs a tangential speed and a radius, or rpm"
            )
        omega_val = abs(v) / r
        return PhysicsResult(
            answer=(
                rf"\omega = \frac{{v}}{{r}} = \frac{{{abs(v):g}}}{{{r:g}}} "
                rf"\approx {omega_val:.2f} \text{{ rad/s}}"
            ),
            formulas=(r"\omega = \frac{v}{r}",),
            substitutions=(rf"\omega = \frac{{{abs(v):g}}}{{{r:g}}}",),
            quantities=(QuantityResult("", omega_val, "rad/s"),),
            simulation_specs=scene,
        )

    a_c = v * v / r
    if op == "centripetal_acceleration":
        if omega is not None:
            law = r"a_c = \omega^2 r"
            plugged = rf"{latex_num(omega, square=True)} \cdot {r:g}"
        else:
            law = r"a_c = \frac{v^2}{r}"
            plugged = rf"\frac{{{latex_num(v, square=True)}}}{{{r:g}}}"
        return PhysicsResult(
            answer=rf"{law} = {plugged} \approx {a_c:.2f} \text{{ m/s}}^2",
            formulas=(law,),
            substitutions=(rf"a_c = {plugged}",),
            quantities=(QuantityResult("", a_c, "m/s^2"),),
            simulation_specs=scene_with("a", f"a = {plain_number(a_c)} m/s²"),
        )

    if op == "centripetal_force":
        if "m" not in p:
            raise SolveServiceError("centripetal force needs a mass")
        f_val = p["m"] * a_c
        if omega is not None:
            law = r"F_c = m\omega^2r"
            plugged = rf"{p['m']:g} \cdot {latex_num(omega, square=True)} \cdot {r:g}"
        else:
            law = r"F_c = \frac{m v^2}{r}"
            plugged = rf"\frac{{{p['m']:g} \cdot {latex_num(v, square=True)}}}{{{r:g}}}"
        return PhysicsResult(
            answer=rf"{law} = {plugged} \approx {f_val:.2f} \text{{ N}}",
            formulas=(law,),
            substitutions=(rf"F_c = {plugged}",),
            quantities=(QuantityResult("", f_val, "N"),),
            simulation_specs=scene_with("F", f"F = {plain_number(f_val)} N"),
        )

    raise SolveServiceError(f"unsupported circular op: {op}")
