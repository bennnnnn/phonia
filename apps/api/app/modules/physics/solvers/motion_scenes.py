"""Scenes for motion under gravity: a projectile's arc and a vertical fall.

One picture per question. The arc carries its range and height as measure
lines and its launch angle as an arc, so the trajectory graph it used to sit
beside said nothing the scene does not; a fall carries the ledge it leaves and
the height it drops. Every coordinate is a sample of the solved motion, so the
ball is never somewhere the answer says it is not. A question about a fall's
speed also gets its v-t line, a different view of it (`fall_speed_pictures`).
"""

from __future__ import annotations

import math

from app.modules.math.schemas import GraphBlockSpec
from app.modules.physics.display import given_number as _given
from app.modules.physics.display import plain_number
from app.modules.physics.schemas import (
    SimulationAngle,
    SimulationBlockSpec,
    SimulationBody,
    SimulationSolid,
    SimulationVector,
)
from app.modules.physics.schemas.simulation import ArrowKind

_SAMPLES = 60
_STROBE = 7
_ARROW_LABELS: dict[ArrowKind, str] = {"velocity": "v", "gravity": "mg"}


def projectile_scene(
    points: list[list[float]], v0: float, theta: float, h0: float, t_flight: float
) -> SimulationBlockSpec:
    """The arc from launch to landing, with R, H, θ and any ledge it leaves."""
    peak = max(point[1] for point in points)
    span = points[-1][0]
    size = max(span, peak, h0) or 1.0
    radius = size * 0.025
    gap = size * 0.07
    # The ball rests on the ground rather than half sunk in it: its centre
    # rides one radius above the solved path.
    path = [[x, y + radius] for x, y in points]
    solids: list[SimulationSolid] = []
    vectors = [
        SimulationVector(
            anchor=[0.0, -gap],
            dx=span or radius,
            dy=0.0,
            label=f"R = {plain_number(span)} m",
            role="measure",
        )
    ]
    x_min = -gap
    if h0 > 0:
        # The table or cliff it leaves: without it the ball starts in mid-air.
        ledge = min(max(0.25 * size, 3 * radius), 0.6 * size)
        solids.append(SimulationSolid(rect=[-ledge, 0.0, 0.0, h0]))
        vectors.append(
            SimulationVector(
                anchor=[-ledge - gap, 0.0],
                dx=0.0,
                dy=h0,
                label=f"h = {_given(h0)} m",
                role="measure",
            )
        )
        # Room left of the line for its "h = 1.2 m": without it the label
        # has nowhere to go but across the table.
        x_min = -ledge - gap - 0.3 * (_projectile_x_max(span, peak, radius) + ledge + gap)
    if theta > 1e-9 and peak > h0 + radius:
        apex = max(points, key=lambda point: point[1])
        vectors.append(
            SimulationVector(
                anchor=[apex[0], 0.0],
                dx=0.0,
                dy=peak,
                label=f"H = {plain_number(peak)} m",
                role="measure",
            )
        )
    degrees = math.degrees(theta)
    angles = (
        [
            SimulationAngle(
                vertex=[0.0, h0 + radius],
                start_deg=0.0,
                end_deg=degrees,
                label=f"{_given(degrees)}°",
            )
        ]
        if degrees >= 1.0
        else []
    )
    if h0 > 0 and degrees < 1.0:
        alt = (
            f"A ball leaves a {_given(h0)} m ledge at {_given(v0)} m/s and lands "
            f"{plain_number(span)} m out after {plain_number(t_flight)} s."
        )
    else:
        alt = (
            f"A ball launched at {_given(v0)} m/s at {_given(degrees)}° rises "
            f"{plain_number(peak)} m and lands {plain_number(span)} m away after "
            f"{plain_number(t_flight)} s."
        )
    return SimulationBlockSpec(
        type="projectile_motion",
        title="Projectile",
        title_key="projectile",
        bodies=[SimulationBody(path=path, radius=radius)],
        solids=solids,
        vectors=vectors,
        angles=angles,
        x_min=x_min,
        x_max=_projectile_x_max(span, peak, radius),
        y_min=-2 * gap,
        y_max=max(peak * 1.2, span * 0.25) + 2 * radius,
        arrows=["velocity", "gravity"],
        arrow_labels=_ARROW_LABELS,
        strobe=_STROBE,
        ground=True,
        alt=alt,
    )


def _projectile_x_max(span: float, peak: float, radius: float) -> float:
    return max(span * 1.08, peak * 0.25, radius * 4)


def vertical_scene(
    h0: float, v0: float, g: float, t_end: float, *, ground: bool, height_given: bool = True
) -> SimulationBlockSpec | None:
    """A drop or an upward throw on one vertical line, to the instant asked about.

    ``ground`` is known when the question gives the height or the motion ends
    on it; a fall from an unstated height ("its speed after 4 s") has none.
    ``height_given`` is False when the height is the answer, so it is written
    to the answer's figures rather than as stated.
    """
    shown_h = _given(h0) if height_given else plain_number(h0)
    if t_end <= 0 or g <= 0:
        return None
    heights = [h0 + v0 * t - 0.5 * g * t * t for t in _times(t_end)]
    if ground:
        heights = [max(height, 0.0) for height in heights]
    top, bottom = max(heights), min(heights)
    if top - bottom <= 0:
        return None
    base = 0.0 if ground else bottom
    size = top - base
    radius = size * 0.04
    gap = size * 0.08
    path = [[0.0, height - base + radius] for height in heights]
    solids: list[SimulationSolid] = []
    vectors: list[SimulationVector] = []
    x_min = -size * 0.3
    if h0 > 0 and ground:
        ledge = size * 0.3
        # The ball falls beside the ledge, not down its face: 1.5 radii of air, about
        # 10 px on the phone, where half a radius read as the ball touching the edge.
        solids.append(SimulationSolid(rect=[-ledge, 0.0, -2.5 * radius, h0]))
        vectors.append(
            SimulationVector(
                anchor=[-ledge - gap, 0.0],
                dx=0.0,
                dy=h0,
                label=f"h = {shown_h} m",
                role="measure",
            )
        )
        x_min = -ledge - 2 * gap
    if v0 > 0 and top > h0 + radius:
        rise = top - h0
        vectors.append(
            SimulationVector(
                anchor=[size * 0.18, h0 - base + radius],
                dx=0.0,
                dy=rise,
                label=f"{plain_number(rise)} m",
                role="measure",
            )
        )
    if v0 > 0:
        alt = f"A ball thrown straight up at {_given(v0)} m/s rises {plain_number(top - h0)} m."
    elif h0 > 0 and heights[-1] <= 1e-9 * h0:
        # Solved to land, it lands: 125 - 4.905 * 5.048² leaves 1e-14, not 0.
        alt = f"A ball dropped from {shown_h} m reaches the ground after {plain_number(t_end)} s."
    else:
        alt = f"A ball falling from rest for {_given(t_end)} s, speeding up as it goes."
    return SimulationBlockSpec(
        type="projectile_motion",
        title="Free Fall",
        title_key="free_fall",
        bodies=[SimulationBody(path=path, radius=radius)],
        solids=solids,
        vectors=vectors,
        x_min=x_min,
        x_max=size * 0.45,
        y_min=-gap if ground else 0.0,
        y_max=size * 1.1 + 2 * radius,
        arrows=["velocity", "gravity"],
        arrow_labels=_ARROW_LABELS,
        strobe=_STROBE,
        ground=ground,
        alt=alt,
    )


def fall_scenes(
    h0: float, v0: float, g: float, t_end: float, *, ground: bool
) -> list[SimulationBlockSpec]:
    """One picture: the drop or the throw itself, with the ledge and the height on it.

    A height-time curve beside it plotted the same samples again. None when
    neither a height nor a launch speed was given: the ball would never leave
    the ground, which reads as "it never moved".
    """
    scene = None if h0 <= 0 and v0 == 0 else vertical_scene(h0, v0, g, t_end, ground=ground)
    return [scene] if scene is not None else []


def fall_speed_pictures(
    h0: float, v0: float, g: float, t_end: float, *, speed: bool, ground: bool
) -> tuple[list[SimulationBlockSpec], list[GraphBlockSpec]]:
    """A "how fast after 1 s" ask gets v(t), not h(t), beside the fall itself.

    Plotting height against a question about speed answers a different question
    than the one asked, and `velocity_vs_time` has been declared on both sides of
    the wire — and emitted by nothing — since the type was introduced.
    """
    # No h0/v0 guard here: v(t) = v0 - g*t is a real line even for a drop
    # from an unstated height, which is exactly the case h(t) cannot plot.
    # Only a zero-length window is degenerate.
    if t_end <= 0:
        return [], []
    # The fall itself, to the instant asked about; the v-t line beside it
    # is a different view (its slope is g), not the same path twice.
    fall = vertical_scene(h0, v0, g, t_end, ground=ground)
    return ([fall] if fall is not None else []), [_velocity_time_graph(v0, g, t_end, speed)]


def _velocity_time_graph(v0: float, g: float, t_end: float, speed: bool) -> GraphBlockSpec:
    n_points = 100
    # End on the instant this answer is about. A later sample is a
    # different velocity than the one just computed.
    t_max = t_end
    dt = t_max / (n_points - 1)
    v_points: list[list[float]] = []
    for i in range(n_points):
        ti = i * dt
        vi = v0 - g * ti
        if speed:
            vi = abs(vi)
        v_points.append([round(ti, 4), round(float(vi), 4)])
    return GraphBlockSpec(
        type="trajectory",
        expr=(f"v(t) = |{v0:g} - {g:g}*t|" if speed else f"v(t) = {v0:g} - {g:g}*t"),
        variable="t",
        x_min=0.0,
        x_max=t_max,
        points=v_points,
        title="Speed vs. Time" if speed else "Velocity vs. Time",
        x_label="Time (s)",
        y_label="Speed (m/s)" if speed else "Velocity (m/s)",
        trajectory_type="velocity_vs_time",
    )


def _times(t_end: float) -> list[float]:
    return [t_end * index / (_SAMPLES - 1) for index in range(_SAMPLES)]
