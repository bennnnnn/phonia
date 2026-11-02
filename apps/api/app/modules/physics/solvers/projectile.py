"""Projectile solvers: 2D motion at an angle.

x(t) = v0 cos(theta) t, y(t) = v0 sin(theta) t - g t^2 / 2,
range R = v0^2 sin(2 theta) / g, peak height H = v0^2 sin^2(theta) / (2g).
"""

from __future__ import annotations

import math

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.motion_scenes import projectile_scene
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import gravity_of, params_in_si
from app.services.solving import SolveServiceError


def _shown_degrees(radians: float) -> str:
    """Degree label for a launch angle that was supplied in degrees."""
    deg = math.degrees(radians)
    tenths = round(deg, 1)
    if abs(tenths - round(tenths)) < 1e-9:
        return f"{round(tenths):.0f}"
    return f"{tenths:.1f}"


def _projectile_max_height_substitution(intent: PhysicsIntent) -> str:
    """Peak height with the launch angle in degrees, not the SI radian."""
    from app.modules.physics.display import latex_given

    params = intent.physics_params or {}
    rise = (
        rf"\frac{{{latex_given(params['v0'])}^2 "
        rf"\sin^2({latex_given(params['angle'])}^\circ)}}"
        rf"{{2 \cdot {latex_given(params['g'])}}}"
    )
    # An unstated launch height is no "0 +" in the working: the rise is the answer.
    if "h0" not in params:
        return rf"H_{{max}} = {rise}"
    return rf"H_{{max}} = {latex_given(params['h0'])} + {rise}"


def solve_projectile(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    g = gravity_of(p)
    v0 = p["v0"]
    # No default. The extractor's `range` initializer was one half of the bug
    # this fixes; leaving the other half here would keep an opless intent
    # answering with a distance instead of failing where it can be seen.
    op = intent.physics_op or ""
    h0 = p.get("h0", 0.0)

    if op == "launch_angle":
        # The one op whose unknown is the angle, so it is answered before the
        # angle is read: R = v0² sin(2θ)/g inverted. Two angles give the same
        # range, θ and 90° - θ, and both are answers; at the maximum range
        # they coincide at 45°.
        if v0 <= 0:
            raise SolveServiceError("launch speed must be positive")
        r_target = p["d"]
        ratio = r_target * g / (v0 * v0)
        if not -1.0 <= ratio <= 1.0:
            raise SolveServiceError("that range is out of reach at this speed")
        deg_val = math.degrees(0.5 * math.asin(ratio))
        steep = 90.0 - deg_val
        angles = (deg_val,) if math.isclose(deg_val, steep) else (deg_val, steep)
        shown = r" \text{ or } ".join(rf"{angle:.2f}^\circ" for angle in angles)
        return PhysicsResult(
            answer=(
                rf"\theta = \tfrac{{1}}{{2}} \arcsin\!\left(\frac{{Rg}}{{v_0^2}}\right) = "
                rf"\tfrac{{1}}{{2}} \arcsin\!\left(\frac{{{r_target:g} \cdot {g:g}}}"
                rf"{{{latex_num(v0, square=True)}}}\right) \approx {shown}"
            ),
            formulas=(
                r"\theta = \tfrac{1}{2} \arcsin\!\left(\frac{Rg}{v_0^2}\right)",
                r"\theta' = 90^\circ - \theta",
            ),
            substitutions=(
                rf"\theta = \tfrac{{1}}{{2}} \arcsin\!\left(\frac{{{r_target:g} \cdot {g:g}}}"
                rf"{{{latex_num(v0, square=True)}}}\right)",
            ),
            quantities=tuple(QuantityResult("", angle, "deg") for angle in angles),
            joiner=" or ",
        )

    theta = p["angle"]  # radians (converted by params_in_si)

    if h0 > 0:
        # y = h0 + v0 sinθ t - ½ g t² = 0 → ½ g t² - v0 sinθ t - h0 = 0
        a = 0.5 * g
        b = -v0 * math.sin(theta)
        c = -h0
        disc = b * b - 4 * a * c
        if disc < 0:
            raise SolveServiceError("projectile has no positive flight time")
        t_flight = (-b + math.sqrt(disc)) / (2 * a)
    else:
        t_flight = 2 * v0 * math.sin(theta) / g
    if t_flight <= 0:
        raise SolveServiceError("projectile has no positive flight time")

    if op == "range":
        if h0 > 0:
            r_val = v0 * math.cos(theta) * t_flight
        else:
            r_val = v0**2 * math.sin(2 * theta) / g
        deg = math.degrees(theta)
        v0_sq = latex_num(v0, square=True)
        if h0 <= 0:
            answer_latex = (
                rf"R = \frac{{v_0^2 \sin(2\theta)}}{{g}} = "
                rf"\frac{{{v0_sq} \cdot \sin({deg:.1f}^\circ \cdot 2)}}{{{g:g}}} "
                rf"\approx {r_val:.2f} \text{{ m}}"
            )
            formulas = (r"R = \frac{v_0^2 \sin(2\theta)}{g}",)
            substitutions = (rf"R = \frac{{{v0_sq} \cdot \sin({deg:.1f}^\circ \cdot 2)}}{{{g:g}}}",)
        else:
            from app.modules.physics.display import latex_given

            answer_latex = rf"R = v_0 \cos(\theta)\, t \approx {r_val:.2f} \text{{ m}}"
            formulas = (r"R = v_0 \cos(\theta)\, t",)
            # The flight time as worked (0.403863 s): at two places, 0.4 s, it no longer gave R.
            time = latex_given(t_flight)
            substitutions = (rf"R = {v0:g}\cos({_shown_degrees(theta)}^\circ)\cdot {time}",)
        quantity = QuantityResult("", r_val, "m")
    elif op == "max_height":
        h_val = h0 + v0**2 * math.sin(theta) ** 2 / (2 * g)
        answer_latex = (
            rf"H = h_0 + \frac{{v_0^2 \sin^2(\theta)}}{{2g}} = "
            rf"{h_val:.2f} \text{{ m}}"
        )
        quantity = QuantityResult("", h_val, "m")
        formulas = (
            (r"H = h_0 + \frac{v_0^2 \sin^2(\theta)}{2g}",)
            if "h0" in (intent.physics_params or {})
            else (r"H = \frac{v_0^2 \sin^2(\theta)}{2g}",)
        )
        substitutions = (_projectile_max_height_substitution(intent),)
    elif op == "time_of_flight":
        # t_flight is already in hand — both branches above compute it to build
        # the trajectory, whatever the question asked for.
        if h0 <= 0:
            answer_latex = (
                rf"t = \frac{{2 v_0 \sin(\theta)}}{{g}} = "
                rf"\frac{{2 \cdot {v0:g} \cdot \sin({math.degrees(theta):.1f}^\circ)}}{{{g:g}}} "
                rf"\approx {t_flight:.2f} \text{{ s}}"
            )
            formulas = (r"t = \frac{2 v_0 \sin(\theta)}{g}",)
            substitutions = (
                rf"t_{{flight}} = \frac{{2 \cdot {v0:g} \cdot "
                rf"\sin({math.degrees(theta):.1f}^\circ)}}{{{g:g}}}",
            )
        else:
            answer_latex = (
                rf"\tfrac{{1}}{{2}} g t^2 - v_0 \sin(\theta) t - h_0 = 0 "
                rf"\Rightarrow t \approx {t_flight:.2f} \text{{ s}}"
            )
            formulas = (r"\tfrac{1}{2} g t^2 - v_0 \sin(\theta) t - h_0 = 0 \Rightarrow t",)
            substitutions = (
                rf"\tfrac{{1}}{{2}} \cdot {g:g} t^2 - {v0:g}\sin({_shown_degrees(theta)}^\circ)"
                rf" t - {h0:g} = 0",
            )
        quantity = QuantityResult("", t_flight, "s")
    elif op == "impact_speed":
        v_x = v0 * math.cos(theta)
        v_y = v0 * math.sin(theta) - g * t_flight
        speed_val = math.hypot(v_x, v_y)
        answer_latex = (
            rf"v = \sqrt{{v_x^2 + v_y^2}} = "
            rf"\sqrt{{{v_x:.2f}^2 + ({v_y:.2f})^2}} "
            rf"\approx {speed_val:.2f} \text{{ m/s}}"
        )
        quantity = QuantityResult("", speed_val, "m/s")
        formulas = (r"v = \sqrt{v_x^2 + v_y^2}",)
        substitutions = (rf"v_{{impact}} = \sqrt{{{v_x:.2f}^2 + ({v_y:.2f})^2}}",)
    else:
        raise SolveServiceError(f"unsupported projectile op: {op}")

    # The solved path: (x(t), y(t)) from t = 0 to the landing.
    n_points = 100
    dt = t_flight / (n_points - 1)
    points: list[list[float]] = []
    for i in range(n_points):
        ti = i * dt
        xi = v0 * math.cos(theta) * ti
        yi = h0 + v0 * math.sin(theta) * ti - 0.5 * g * ti**2
        if yi < 0:
            yi = 0.0
        points.append([xi, float(yi)])

    # One picture: the arc with its range, height and launch angle on it. A
    # trajectory graph beside it plotted the same samples a second time.
    scene = projectile_scene(points, v0, theta, h0, t_flight)
    return PhysicsResult(
        answer=answer_latex,
        quantities=(quantity,),
        formulas=formulas,
        substitutions=substitutions,
        simulation_specs=[scene],
    )
