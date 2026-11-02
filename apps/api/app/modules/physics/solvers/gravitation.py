"""Gravitation solvers: Newton's law, surface gravity, orbital and escape speed."""

from __future__ import annotations

import math

from app.modules.physics.bodies import body_name
from app.modules.physics.constants import BIG_G
from app.modules.physics.display import plain_number
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.circular import _orbit_scene
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_gravitation(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or ""

    if op == "gravitational_force":
        r = p["r"]
        if r <= 0:
            raise SolveServiceError("separation must be positive")
        f_val = BIG_G * p["m1"] * p["m2"] / (r * r)
        return PhysicsResult(
            answer=(
                rf"F = \frac{{G m_1 m_2}}{{r^2}} = \frac{{{BIG_G:.5g} \cdot {p['m1']:g} "
                rf"\cdot {p['m2']:g}}}{{{latex_num(r, square=True)}}} "
                rf"\approx {f_val:.4g} \text{{ N}}"
            ),
            formulas=(r"F = \frac{G m_1 m_2}{r^2}",),
            substitutions=(
                rf"F = \frac{{{BIG_G:.5g} \cdot {p['m1']:g} \cdot {p['m2']:g}}}"
                rf"{{{latex_num(r, square=True)}}}",
            ),
            quantities=(QuantityResult("", f_val, "N"),),
        )

    if op == "orbital_velocity":
        r = p["radius_body"] + p.get("altitude", 0.0)
        if r <= 0:
            raise SolveServiceError("orbital radius must be positive")
        v_val = math.sqrt(BIG_G * p["M"] / r)
        return PhysicsResult(
            answer=(
                rf"v = \sqrt{{\frac{{GM}}{{r}}}} = \sqrt{{\frac{{{BIG_G:.5g} \cdot "
                rf"{p['M']:.4g}}}{{{r:.4g}}}}} \approx {v_val:.2f} \text{{ m/s}}"
            ),
            formulas=(r"v = \sqrt{\frac{GM}{r}}",),
            substitutions=(rf"v = \sqrt{{\frac{{{BIG_G:.5g} \cdot {p['M']:.4g}}}{{{r:.4g}}}}}",),
            quantities=(QuantityResult("", v_val, "m/s"),),
            simulation_specs=[
                _orbit_scene(
                    r,
                    planet=(p["radius_body"], body_name(p["M"], p["radius_body"])),
                    arrow_labels={
                        "velocity": f"v = {plain_number(v_val)} m/s",
                        "centripetal": "gravity",
                    },
                    alt=_orbit_alt(p, r, v_val),
                )
            ],
        )

    if op == "escape_velocity":
        radius = p["radius_body"]
        if radius <= 0:
            raise SolveServiceError("radius must be positive")
        v_val = math.sqrt(2 * BIG_G * p["M"] / radius)
        return PhysicsResult(
            answer=(
                rf"v_e = \sqrt{{\frac{{2GM}}{{R}}}} = \sqrt{{\frac{{2 \cdot {BIG_G:.5g} "
                rf"\cdot {p['M']:.4g}}}{{{radius:.4g}}}}} \approx {v_val:.2f} \text{{ m/s}}"
            ),
            formulas=(r"v_e = \sqrt{\frac{2GM}{R}}",),
            substitutions=(
                rf"v_e = \sqrt{{\frac{{2 \cdot {BIG_G:.5g} \cdot {p['M']:.4g}}}{{{radius:.4g}}}}}",
            ),
            quantities=(QuantityResult("", v_val, "m/s"),),
        )

    if op == "surface_gravity":
        radius = p["radius_body"]
        if radius <= 0:
            raise SolveServiceError("radius must be positive")
        g_val = BIG_G * p["M"] / (radius * radius)
        return PhysicsResult(
            answer=(
                rf"g = \frac{{GM}}{{R^2}} = \frac{{{BIG_G:.5g} \cdot {p['M']:.4g}}}"
                rf"{{{latex_num(radius, square=True)}}} \approx {g_val:.2f} "
                rf"\text{{ m/s}}^2"
            ),
            formulas=(r"g = \frac{GM}{R^2}",),
            substitutions=(
                rf"g = \frac{{{BIG_G:.5g} \cdot {p['M']:.4g}}}"
                rf"{{{latex_num(radius, square=True)}}}",
            ),
            quantities=(QuantityResult("", g_val, "m/s^2"),),
        )

    raise SolveServiceError(f"unsupported gravitation op: {op}")


def _orbit_alt(p: dict[str, float], r: float, speed: float) -> str:
    name = body_name(p["M"], p["radius_body"]) or "the planet"
    height = p.get("altitude", 0.0)
    where = f"{plain_number(height / 1000)} km above {name}" if height else f"round {name}"
    return f"A satellite {where}, moving at {plain_number(speed)} m/s."
