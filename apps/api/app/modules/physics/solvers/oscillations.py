"""Oscillation solvers: F = kx, U = kx^2/2, T = 2 pi sqrt(m/k), and the pendulum's
T = 2 pi sqrt(L/g), which is the same oscillation and so lives here.
"""

from __future__ import annotations

import math

from app.modules.math.schemas import GraphBlockSpec
from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import (
    PhysicsIntent,
    SimulationAngle,
    SimulationBlockSpec,
    SimulationBody,
    SimulationTether,
)
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import gravity_of, params_in_si
from app.services.solving import SolveServiceError

_SAMPLES = 100


def _displacement_samples(t_period: float, amplitude: float) -> list[list[float]]:
    """Two periods of x(t) = A cos(2πt/T), uniform in time."""
    span = 2 * t_period
    dt = span / (_SAMPLES - 1)
    return [
        [round(i * dt, 4), round(amplitude * math.cos(2 * math.pi * (i * dt) / t_period), 4)]
        for i in range(_SAMPLES)
    ]


def _spring_scene(
    samples: list[list[float]], amplitude: float, *, stated: bool, period: float
) -> SimulationBlockSpec:
    """The mass walks the same displacement the graph plotted.

    The graph's y column is position. The scene uses that column as x and
    holds y, so a frame cannot sit somewhere the curve is not. The wall is
    one amplitude left of the leftmost sample: close enough to read as a
    spring, far enough that the coil never collapses onto the mass.

    An unstated amplitude is drawn at a display size, as the incline's slope
    is: the motion's shape is real, and no number is written on the swing.
    """
    xs = [point[1] for point in samples]
    radius = max(amplitude * 0.16, 0.02)
    wall = min(xs) - amplitude
    pad = amplitude * 0.45
    shown = plain_number(period)
    swing = f" {plain_number(amplitude, GIVEN_FIGURES)} m either side," if stated else ""
    return SimulationBlockSpec(
        type="spring",
        title_key="spring",
        bodies=[
            SimulationBody(
                path=[[x, round(radius, 4)] for x in xs],
                radius=radius,
                shape="box",
            )
        ],
        x_min=wall - pad,
        x_max=max(xs) + pad,
        y_min=0.0,
        y_max=max(amplitude, radius * 4),
        ground=True,
        anchor=[wall, round(radius, 4)],
        alt=f"A mass on a spring sliding{swing} back and forth every {shown} s.",
    )


def _pendulum_scene(
    length: float, period: float, *, length_given: bool = True
) -> SimulationBlockSpec:
    """A bob on its string, swinging through one period.

    The amplitude is a display choice (15°): the period of a small swing does
    not depend on it, and no number is written on the arc.
    """
    swing = math.radians(15)
    path = []
    for index in range(_SAMPLES):
        angle = swing * math.cos(2 * math.pi * index / (_SAMPLES - 1))
        path.append([round(length * math.sin(angle), 6), round(-length * math.cos(angle), 6)])
    reach = length * math.sin(swing)
    return SimulationBlockSpec(
        type="pendulum",
        title="Pendulum",
        title_key="pendulum",
        bodies=[SimulationBody(path=path, radius=length * 0.06)],
        tethers=[SimulationTether(anchor=[0.0, 0.0], body=0)],
        angles=[SimulationAngle(vertex=[0.0, 0.0], start_deg=-90.0, end_deg=-75.0, label="θ")],
        arrows=["velocity", "gravity"],
        arrow_labels={"velocity": "v", "gravity": "mg"},
        x_min=-reach * 2.4,
        x_max=reach * 2.4,
        y_min=-length * 1.2,
        y_max=length * 0.12,
        alt=(
            f"A {plain_number(length, GIVEN_FIGURES if length_given else 3)} m pendulum "
            "swinging back and forth "
            f"every {plain_number(period)} s."
        ),
    )


def _oscillation_curve(t_period: float, amplitude: float | None) -> GraphBlockSpec:
    """One period-and-a-bit of x(t) = A cos(2πt/T).

    The oscillation is the thing worth seeing, so hand P3's player a curve.
    Amplitude only scales the y-axis — the shape and the period are what the
    question is about — so when none is given the plot is normalised rather
    than invented.
    """
    a_plot = abs(amplitude) if amplitude else 1.0
    points = _displacement_samples(t_period, a_plot)
    span = points[-1][0]
    return GraphBlockSpec(
        type="trajectory",
        expr=f"x(t) = {a_plot:g}*cos(2*pi*t/{t_period:.4g})",
        variable="t",
        x_min=0.0,
        x_max=span,
        points=points,
        title="Displacement vs. Time",
        x_label="Time (s)",
        y_label="Displacement (m)" if amplitude else "Displacement (normalised)",
        trajectory_type="position_vs_time",
    )


def _motion(
    t_period: float, amplitude: float | None
) -> tuple[GraphBlockSpec, list[SimulationBlockSpec]]:
    """The displacement graph and the spring that makes it.

    A normalised plot uses A = 1 so the shape is visible; the scene then
    draws its swing at a display size with no number on it.
    """
    graph = _oscillation_curve(t_period, amplitude)
    stated = bool(amplitude)
    shown = abs(amplitude) if amplitude else 1.0
    return graph, [_spring_scene(graph.points, shown, stated=stated, period=t_period)]


def solve_spring(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or "spring_force"

    # A pendulum has a length, not a spring constant, so it is answered before
    # the k lookup below rather than after it.
    if op == "pendulum_period":
        length = p["L"]
        if length <= 0:
            raise SolveServiceError("pendulum length must be positive")
        g = gravity_of(p)
        if g <= 0:
            raise SolveServiceError("gravity must be positive")
        t_period = 2 * math.pi * math.sqrt(length / g)
        answer = (
            rf"T = 2\pi\sqrt{{\frac{{L}}{{g}}}} = 2\pi\sqrt{{\frac{{{length:g}}}{{{g:g}}}}} "
            rf"\approx {t_period:.2f} \text{{ s}}"
        )
        # The pendulum itself, never the spring `_motion` draws: a stated
        # amplitude does not turn a bob on a string into a mass on a spring.
        return PhysicsResult(
            answer=answer,
            formulas=(r"T = 2\pi\sqrt{\frac{L}{g}}",),
            substitutions=(rf"T = 2\pi\sqrt{{\frac{{{length:g}}}{{{g:g}}}}}",),
            quantities=(QuantityResult("", t_period, "s"),),
            simulation_specs=[_pendulum_scene(length, t_period)],
        )

    # Like the pendulum above, these need no spring constant, so they are
    # answered before the k lookup rather than after it.
    if op == "shm_frequency":
        if "period" in p:
            t_period = p["period"]
            if t_period <= 0:
                raise SolveServiceError("period must be positive")
            freq = 1 / t_period
            formula = r"f = \frac{1}{T}"
            substitution = rf"f = \frac{{1}}{{{t_period:g}}}"
            shown = (
                rf"f = \frac{{1}}{{T}} = \frac{{1}}{{{t_period:g}}} "
                rf"\approx {freq:.2f} \text{{ Hz}}"
            )
        else:
            mass = p["m"]
            spring_k = p["k"]
            if mass <= 0 or spring_k <= 0:
                raise SolveServiceError("mass and spring constant must be positive")
            freq = math.sqrt(spring_k / mass) / (2 * math.pi)
            t_period = 1 / freq
            formula = r"f = \frac{1}{2\pi}\sqrt{\frac{k}{m}}"
            substitution = rf"f = \frac{{1}}{{2\pi}}\sqrt{{\frac{{{spring_k:g}}}{{{mass:g}}}}}"
            shown = (
                rf"f = \frac{{1}}{{2\pi}}\sqrt{{\frac{{k}}{{m}}}} = "
                rf"\frac{{1}}{{2\pi}}\sqrt{{\frac{{{spring_k:g}}}{{{mass:g}}}}} "
                rf"\approx {freq:.2f} \text{{ Hz}}"
            )
        graph, scene = _motion(t_period, p.get("x"))
        return PhysicsResult(
            answer=shown,
            formulas=(formula,),
            substitutions=(substitution,),
            quantities=(QuantityResult("", freq, "Hz"),),
            graph_specs=[graph],
            simulation_specs=scene,
        )

    if op == "shm_max_speed":
        amplitude = p["x"]
        omega = p["omega"]
        if amplitude <= 0 or omega <= 0:
            raise SolveServiceError("amplitude and angular frequency must be positive")
        v_max = amplitude * omega
        graph, scene = _motion(2 * math.pi / omega, amplitude)
        return PhysicsResult(
            answer=(
                rf"v_{{max}} = A\omega = {amplitude:g} \cdot {omega:g} "
                rf"\approx {v_max:.2f} \text{{ m/s}}"
            ),
            formulas=(r"v_{max} = A\omega",),
            substitutions=(rf"v_{{max}} = {amplitude:g} \cdot {omega:g}",),
            quantities=(QuantityResult("", v_max, "m/s"),),
            graph_specs=[graph],
            simulation_specs=scene,
        )

    k = p["k"]
    if k <= 0:
        raise SolveServiceError("spring constant must be positive")

    if op == "spring_force":
        x = p["x"]
        f_val = k * abs(x)
        return PhysicsResult(
            answer=(rf"F = kx = {k:g} \cdot {abs(x):g} \approx {f_val:.2f} \text{{ N}}"),
            formulas=(r"F = kx",),
            substitutions=(rf"F = {k:g} \cdot {abs(x):g}",),
            quantities=(QuantityResult("", f_val, "N"),),
        )

    if op == "spring_energy":
        x = p["x"]
        u_val = 0.5 * k * x * x
        return PhysicsResult(
            answer=(
                rf"U = \tfrac{{1}}{{2}} k x^2 = 0.5 \cdot {k:g} \cdot "
                rf"{latex_num(x, square=True)} \approx {u_val:.2f} \text{{ J}}"
            ),
            formulas=(r"U = \tfrac{1}{2} k x^2",),
            substitutions=(rf"E_s = 0.5 \cdot {k:g} \cdot {latex_num(x, square=True)}",),
            quantities=(QuantityResult("", u_val, "J"),),
        )

    if op == "shm_period":
        m = p["m"]
        if m <= 0:
            raise SolveServiceError("mass must be positive")
        t_period = 2 * math.pi * math.sqrt(m / k)
        answer = (
            rf"T = 2\pi\sqrt{{\frac{{m}}{{k}}}} = 2\pi\sqrt{{\frac{{{m:g}}}{{{k:g}}}}} "
            rf"\approx {t_period:.2f} \text{{ s}}"
        )

        graph, scene = _motion(t_period, p.get("x"))
        return PhysicsResult(
            answer=answer,
            formulas=(r"T = 2\pi\sqrt{\frac{m}{k}}",),
            substitutions=(rf"T = 2\pi\sqrt{{\frac{{{m:g}}}{{{k:g}}}}}",),
            quantities=(QuantityResult("", t_period, "s"),),
            graph_specs=[graph],
            simulation_specs=scene,
        )

    raise SolveServiceError(f"unsupported spring op: {op}")
