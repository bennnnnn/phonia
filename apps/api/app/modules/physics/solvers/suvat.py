"""SUVAT solvers: motion under any constant acceleration.

v = u + at, s = ut + at^2/2, v^2 = u^2 + 2as, s = (u + v)t/2,
s = vt - at^2/2.

Each equation omits one variable, so the givens choose the equation
rather than the wording choosing it: the same "read the question from its
givens" shape Ohm's law uses, and the reason four sets of phrasing rules were
not needed.
"""

from __future__ import annotations

import math

from app.modules.math.schemas import GraphBlockSpec
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.arithmetic import latex_num, quadratic_roots
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def _suvat_velocity(p: dict[str, float]) -> tuple[float, str, str, str]:
    u, a, t, d = p.get("u"), p.get("a"), p.get("t"), p.get("d")
    if u is not None and a is not None and t is not None:
        plugged = rf"{u:g} + {latex_num(a)} \cdot {t:g}"
        return u + a * t, rf"v = u + at = {plugged}", r"v = u + at", rf"v = {plugged}"
    if u is not None and a is not None and d is not None:
        square = u * u + 2 * a * d
        if square < 0:
            raise SolveServiceError("no real final velocity: the body stops before that distance")
        plugged = rf"\sqrt{{{latex_num(u, square=True)} + 2 \cdot {latex_num(a)} \cdot {d:g}}}"
        return (
            math.sqrt(square),
            rf"v = \sqrt{{u^2 + 2as}} = {plugged}",
            r"v = \sqrt{u^2 + 2as}",
            rf"v = {plugged}",
        )
    if u is not None and d is not None and t is not None:
        if t == 0:
            raise SolveServiceError("time must be non-zero")
        plugged = rf"\frac{{2 \cdot {d:g}}}{{{t:g}}} - {u:g}"
        return (
            2 * d / t - u,
            rf"s = \tfrac{{1}}{{2}}(u + v)t \Rightarrow v = \frac{{2s}}{{t}} - u = {plugged}",
            r"v = \frac{2s}{t} - u",
            rf"v = {plugged}",
        )
    raise SolveServiceError("not enough givens for a final velocity")


def _suvat_distance(p: dict[str, float]) -> tuple[float, str, str, str]:
    u, v, a, t = p.get("u"), p.get("v"), p.get("a"), p.get("t")
    if p.get("distance_path", 1.0):
        initial, final = u, v
        if initial is not None and a is not None and t is not None:
            final = initial + a * t
        elif final is not None and a is not None and t is not None:
            initial = final - a * t
        if initial is not None and final is not None and initial * final < 0:
            acceleration = a if a is not None else (final - initial) / t if t else None
            if acceleration is None or acceleration == 0:
                raise SolveServiceError("reversal needs a nonzero acceleration")
            distance = (initial * initial + final * final) / (2 * abs(acceleration))
            formula = r"s = \int_0^t |u+a\tau|\,d\tau = \frac{u^2+v^2}{2|a|}"
            substitution = (
                rf"s = \frac{{{latex_num(initial, square=True)} + "
                rf"{latex_num(final, square=True)}}}{{2\cdot {abs(acceleration):g}}}"
            )
            return (
                distance,
                formula + " = " + substitution.split(" = ", 1)[1],
                formula,
                substitution,
            )
    if u is not None and a is not None and t is not None:
        plugged = rf"{u:g} \cdot {t:g} + 0.5 \cdot {latex_num(a)} \cdot {latex_num(t, square=True)}"
        return (
            u * t + 0.5 * a * t * t,
            rf"s = ut + \tfrac{{1}}{{2}}at^2 = {plugged}",
            r"s = ut + \tfrac{1}{2}at^2",
            rf"s = {plugged}",
        )
    if u is not None and v is not None and a is not None:
        if a == 0:
            raise SolveServiceError("acceleration must be non-zero to find a distance this way")
        plugged = (
            rf"\frac{{{latex_num(v, square=True)} - {latex_num(u, square=True)}}}"
            rf"{{2 \cdot {latex_num(a)}}}"
        )
        return (
            (v * v - u * u) / (2 * a),
            rf"v^2 = u^2 + 2as \Rightarrow s = \frac{{v^2 - u^2}}{{2a}} = {plugged}",
            r"s = \frac{v^2 - u^2}{2a}",
            rf"s = {plugged}",
        )
    if u is not None and v is not None and t is not None:
        plugged = rf"0.5 \cdot ({u:g} + {v:g}) \cdot {t:g}"
        return (
            0.5 * (u + v) * t,
            rf"s = \tfrac{{1}}{{2}}(u + v)t = {plugged}",
            r"s = \tfrac{1}{2}(u + v)t",
            rf"s = {plugged}",
        )
    # s = vt - (1/2)at^2 is the same constant-acceleration law with u eliminated.
    # Opposite signs mean the body reversed, so the expression is the
    # displacement and not the distance traveled.
    if v is not None and a is not None and t is not None:
        initial = v - a * t
        if initial * v < 0 and p.get("distance_path", 1.0):
            raise SolveServiceError(
                "the body reverses direction, so this is not the distance traveled"
            )
        plugged = rf"{v:g} \cdot {t:g} - 0.5 \cdot {latex_num(a)} \cdot {latex_num(t, square=True)}"
        return (
            v * t - 0.5 * a * t * t,
            rf"s = vt - \tfrac{{1}}{{2}}at^2 = {plugged}",
            r"s = vt - \tfrac{1}{2}at^2",
            rf"s = {plugged}",
        )
    raise SolveServiceError("not enough givens for a distance")


def _suvat_time(p: dict[str, float]) -> tuple[float, str, str, str]:
    u, v, a, d = p.get("u"), p.get("v"), p.get("a"), p.get("d")
    if u is not None and v is not None and a is not None:
        if a == 0:
            raise SolveServiceError("acceleration must be non-zero to find a time this way")
        plugged = rf"\frac{{{v:g} - {u:g}}}{{{latex_num(a)}}}"
        return (
            (v - u) / a,
            rf"v = u + at \Rightarrow t = \frac{{v - u}}{{a}} = {plugged}",
            r"t = \frac{v - u}{a}",
            rf"t = {plugged}",
        )
    if u is not None and a is not None and d is not None:
        # ½at² + ut - s = 0; the earliest non-negative root is the physical one.
        candidates = [root for root in quadratic_roots(0.5 * a, u, -d) if root >= 0]
        if not candidates:
            raise SolveServiceError("the body never reaches that distance")
        return (
            candidates[0],
            rf"s = ut + \tfrac{{1}}{{2}}at^2 \Rightarrow 0.5 \cdot {latex_num(a)} t^2 + "
            rf"{u:g}t = {d:g}",
            r"\tfrac{1}{2}at^2 + ut - s = 0",
            rf"\tfrac{{1}}{{2}} \cdot {latex_num(a)} t^2 + {latex_num(u)} t - {d:g} = 0",
        )
    if u is not None and v is not None and d is not None:
        if u + v == 0:
            raise SolveServiceError("average velocity is zero, so no time follows")
        plugged = rf"\frac{{2 \cdot {d:g}}}{{{u:g} + {v:g}}}"
        return (
            2 * d / (u + v),
            rf"s = \tfrac{{1}}{{2}}(u + v)t \Rightarrow t = \frac{{2s}}{{u + v}} = {plugged}",
            r"t = \frac{2s}{u + v}",
            rf"t = {plugged}",
        )
    raise SolveServiceError("not enough givens for a time")


def _suvat_acceleration(p: dict[str, float]) -> tuple[float, str, str, str]:
    u, v, t, d = p.get("u"), p.get("v"), p.get("t"), p.get("d")
    if u is not None and v is not None and t is not None:
        if t == 0:
            raise SolveServiceError("time must be non-zero")
        plugged = rf"\frac{{{v:g} - {u:g}}}{{{t:g}}}"
        return (
            (v - u) / t,
            rf"v = u + at \Rightarrow a = \frac{{v - u}}{{t}} = {plugged}",
            r"a = \frac{v - u}{t}",
            rf"a = {plugged}",
        )
    if u is not None and v is not None and d is not None:
        if d == 0:
            raise SolveServiceError("distance must be non-zero")
        plugged = (
            rf"\frac{{{latex_num(v, square=True)} - {latex_num(u, square=True)}}}"
            rf"{{2 \cdot {d:g}}}"
        )
        return (
            (v * v - u * u) / (2 * d),
            rf"v^2 = u^2 + 2as \Rightarrow a = \frac{{v^2 - u^2}}{{2s}} = {plugged}",
            r"a = \frac{v^2 - u^2}{2s}",
            rf"a = {plugged}",
        )
    if u is not None and t is not None and d is not None:
        if t == 0:
            raise SolveServiceError("time must be non-zero")
        plugged = rf"\frac{{2({d:g} - {u:g} \cdot {t:g})}}{{{latex_num(t, square=True)}}}"
        return (
            2 * (d - u * t) / (t * t),
            rf"s = ut + \tfrac{{1}}{{2}}at^2 \Rightarrow a = \frac{{2(s - ut)}}{{t^2}} = {plugged}",
            r"a = \frac{2(s - ut)}{t^2}",
            rf"a = {plugged}",
        )
    raise SolveServiceError("not enough givens for an acceleration")


_SUVAT_OPS = {
    "suvat_velocity": (_suvat_velocity, "m/s"),
    "suvat_distance": (_suvat_distance, "m"),
    "suvat_time": (_suvat_time, "s"),
    "suvat_acceleration": (_suvat_acceleration, "m/s^2"),
}


def _suvat_graph(op: str, p: dict[str, float], solved: dict[str, float]) -> list[GraphBlockSpec]:
    """A plot of the quantity the question actually asked for.

    Every op used to get the same velocity-against-time line, on the reasoning
    that its slope *is* the acceleration. That is true and it was still wrong:
    "how far does a car go in 5 s" was answered 37.50 m under a chart climbing
    to 15 m/s. The 37.50 is the area under that line — a real relationship, and
    not the one on screen, with nothing saying so. Worse, two different
    questions about the same journey drew byte-identical charts, which reads as
    a duplication bug rather than a wrong axis.

    So a distance question gets distance against time, and the curve bends the
    way s = ut + ½at² bends. Needs u, a and a span; without all three there is
    nothing honest to draw.
    """
    known = {**p, **solved}
    u, a, t_end = known.get("u"), known.get("a"), known.get("t")
    # s = vt - (1/2)at^2 states the final speed instead of u. The curve still
    # needs the starting speed, and v = u + at recovers it.
    final_speed = known.get("v")
    if u is None and final_speed is not None and a is not None and t_end is not None:
        u = final_speed - a * t_end
    if u is None or a is None or t_end is None or t_end <= 0:
        return []

    # Solving *for* a time plots whichever variable the givens carry to its
    # target: a stated final velocity makes it a velocity question, a stated
    # distance a distance one.
    wants_distance = op == "suvat_distance" or (op == "suvat_time" and "d" in known)

    n_points = 60
    dt = t_end / (n_points - 1)
    if wants_distance:
        path_distance = bool(p.get("distance_path", 1.0))
        stop = -u / a if a else -1.0

        def position(time: float) -> float:
            displacement = u * time + 0.5 * a * time**2
            if path_distance and 0 < stop < time:
                turning = u * stop + 0.5 * a * stop**2
                return abs(turning) + abs(displacement - turning)
            return abs(displacement) if path_distance else displacement

        points = [[i * dt, position(i * dt)] for i in range(n_points)]
        spec = GraphBlockSpec(
            type="trajectory",
            expr=f"s(t) = integral(abs({u:g}+{a:g}*t),t)"
            if path_distance
            else f"s(t) = {u:g}*t + {0.5 * a:g}*t^2",
            variable="t",
            x_min=0.0,
            x_max=t_end,
            points=points,
            title="Distance vs. Time" if path_distance else "Displacement vs. Time",
            x_label="Time (s)",
            y_label="Distance (m)" if path_distance else "Displacement (m)",
            trajectory_type="position_vs_time",
        )
    else:
        points = [[round(i * dt, 4), round(u + a * (i * dt), 4)] for i in range(n_points)]
        spec = GraphBlockSpec(
            type="trajectory",
            expr=f"v(t) = {u:g} + {a:g}*t",
            variable="t",
            x_min=0.0,
            x_max=t_end,
            points=points,
            title="Velocity vs. Time",
            x_label="Time (s)",
            y_label="Velocity (m/s)",
            trajectory_type="velocity_vs_time",
        )
    return [spec]


def solve_suvat(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or "suvat_velocity"
    entry = _SUVAT_OPS.get(op)
    if entry is None:
        raise SolveServiceError(f"unsupported suvat op: {op}")
    compute, unit = entry

    if p.get("t", 0.0) < 0:
        raise SolveServiceError("elapsed time cannot be negative")
    if all(name in p for name in ("u", "v", "a")) and p["a"] and (p["v"] - p["u"]) / p["a"] < 0:
        raise SolveServiceError("the stated velocities require a negative elapsed time")
    if all(name in p for name in ("u", "v", "a", "t")) and not math.isclose(
        p["v"],
        p["u"] + p["a"] * p["t"],
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise SolveServiceError("the stated motion is inconsistent")

    value, workings, formula, substitution = compute(p)
    if not math.isfinite(value):
        raise SolveServiceError("suvat solution is not finite")
    # A negative time or distance means the givens describe no real motion —
    # better refused than reported, since the arithmetic looks fine either way.
    if op == "suvat_distance" and p.get("distance_path", 1.0) and value < 0:
        formula = "s = |" + formula.split(" = ", 1)[1] + "|"
        substitution = "s = |" + substitution.split(" = ", 1)[1] + "|"
        workings = substitution
        value = abs(value)
    if (
        op == "suvat_time" or (op == "suvat_distance" and p.get("distance_path", 1.0))
    ) and value < 0:
        raise SolveServiceError(f"negative {op.removeprefix('suvat_')} from these givens")

    solved = {
        "suvat_velocity": "v",
        "suvat_distance": "d",
        "suvat_time": "t",
        "suvat_acceleration": "a",
    }.get(op)
    if "d" in p:
        known = {**p, **({solved: value} if solved else {})}
        initial, final, acceleration, duration = (known.get(name) for name in ("u", "v", "a", "t"))
        if duration is None and initial is not None and final is not None and acceleration:
            duration = (final - initial) / acceleration
        if (
            duration is not None
            and initial is not None
            and final is None
            and acceleration is not None
        ):
            final = initial + acceleration * duration
        if initial is not None and final is not None and duration is not None:
            implied = 0.5 * (initial + final) * duration
            if p.get("distance_path", 1.0):
                implied = abs(implied)
                if initial * final < 0 and initial != final:
                    implied = (initial**2 + final**2) * duration / (2 * abs(final - initial))
            if duration < 0 or not math.isclose(implied, p["d"], rel_tol=1e-8, abs_tol=1e-8):
                raise SolveServiceError("the motion does not cover the stated distance")
    graphs = _suvat_graph(op, p, {solved: value} if solved else {})
    return PhysicsResult(
        answer=rf"{workings} \approx {value:.2f} \text{{ {unit} }}",
        formulas=(formula,),
        substitutions=(substitution,),
        quantities=(QuantityResult("", value, unit),),
        graph_specs=graphs,
    )
