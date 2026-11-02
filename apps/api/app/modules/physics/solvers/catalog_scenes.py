"""Pictures for catalog laws that are solved as arithmetic.

A law the catalog writes as an expression has no solver of its own to draw
it, so its picture is looked up here by operation, from the question's values
in SI and the solved one. Each builder is the same one the school solver for
that situation uses: a string's tension is the circular-motion scene with its
string, a dropped stone the fall scene, a recoil the collision scene run from
rest. An operation not listed has nothing to point at and gets no picture.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.modules.physics.bodies import body_name
from app.modules.physics.constants import SPEED_OF_LIGHT
from app.modules.physics.display import given_number as _given
from app.modules.physics.display import plain_number
from app.modules.physics.schemas import (
    CircuitNode,
    CircuitSource,
    CircuitSpec,
    PhysicsIntent,
    SimulationBlockSpec,
    SimulationVector,
)
from app.modules.physics.solvers.circular import _orbit_scene
from app.modules.physics.solvers.energy import height_scene
from app.modules.physics.solvers.force_scenes import free_body_scene
from app.modules.physics.solvers.friction import _floor_scene, incline_scene
from app.modules.physics.solvers.momentum import _collision_scene
from app.modules.physics.solvers.motion_scenes import vertical_scene
from app.modules.physics.solvers.optics_scenes import interface_scene, lens_scene
from app.modules.physics.solvers.oscillations import (
    _displacement_samples,
    _pendulum_scene,
    _spring_scene,
)
from app.modules.physics.solvers.wave_scenes import travelling_scene

Scenes = list[SimulationBlockSpec]


def _kg(value: float) -> str:
    return f"{_given(value)} kg"


# --- forces ----------------------------------------------------------------------


def _opposing(p: dict[str, float], value: float, *, net: bool) -> Scenes:
    """Two forces pulling a box opposite ways, and what is left over."""
    forward, back = p["F_forward"], p["F_back"]
    total = forward - back
    vectors = [
        SimulationVector(anchor=[0.0, 0.0], dx=forward, dy=0.0, label=f"{_given(forward)} N"),
        SimulationVector(anchor=[0.0, 0.0], dx=-back, dy=0.0, label=f"{_given(back)} N"),
    ]
    if total:
        shown = (
            f"ΣF = {plain_number(abs(total))} N" if net else f"a = {plain_number(abs(value))} m/s²"
        )
        vectors.append(
            SimulationVector(
                anchor=[0.0, -0.9],
                dx=total,
                dy=0.0,
                label=shown,
                role="result" if net else "motion",
            )
        )
    leftover = f"a net {plain_number(abs(total))} N toward the larger" if total else "no net force"
    return free_body_scene(
        vectors,
        label=_kg(p["m"]) if "m" in p else None,
        shape="box",
        alt=f"Forces of {_given(forward)} N and {_given(back)} N pull opposite ways: {leftover}.",
    )


def _pushed_box(force: float, *, mass: float, motion: str, alt: str) -> Scenes:
    """F = ma's picture: a push and the motion it gives, the same way round."""
    return free_body_scene(
        [
            SimulationVector(anchor=[0.0, 0.0], dx=1.0, dy=0.0, label=f"F = {_given(force)} N"),
            SimulationVector(anchor=[0.0, -0.9], dx=1.0, dy=0.0, label=motion, role="motion"),
        ],
        label=_kg(mass),
        shape="box",
        alt=alt,
    )


def _mass_from_force(p: dict[str, float], value: float) -> Scenes:
    return _pushed_box(
        p["F"],
        mass=value,
        motion=f"a = {_given(p['accel'])} m/s²",
        alt=(
            f"A {_given(p['F'])} N push gives a {plain_number(value)} kg box "
            f"{_given(p['accel'])} m/s²."
        ),
    )


def _speed_from_net_force(p: dict[str, float], value: float) -> Scenes:
    return _pushed_box(
        p["F"],
        mass=p["m"],
        motion=f"v = {plain_number(value)} m/s",
        alt=(
            f"A {_given(p['F'])} N push on a {_kg(p['m'])} box for {_given(p['t'])} s "
            f"brings it to {plain_number(value)} m/s."
        ),
    )


def _terminal_drag(p: dict[str, float], value: float) -> Scenes:
    """Drag up, weight down, equal: steady speed is a balance."""
    shown = f"{plain_number(value)} N"
    return free_body_scene(
        [
            SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0, label=f"W = {shown}"),
            SimulationVector(
                anchor=[0.0, 0.0], dx=0.0, dy=1.0, label=f"D = {shown}", role="result"
            ),
        ],
        label=_kg(p["m"]),
        alt=(
            f"A {_kg(p['m'])} body falling at a steady speed: air resistance of "
            f"{plain_number(value)} N balances its weight."
        ),
    )


def _applied_friction(p: dict[str, float], value: float) -> Scenes:
    m, g = p["m"], p["g"]
    return _floor_scene(m, g, friction=p["mu"] * m * g, applied=p["F"], asked="")


def _weight_along_slope(p: dict[str, float], value: float) -> Scenes:
    return incline_scene(
        math.degrees(p["angle"]),
        mu=0.0,
        mass=p["m"],
        g=p["g"],
        along=value,
    )


# --- motion ----------------------------------------------------------------------


def _drop_speed(p: dict[str, float], value: float) -> Scenes:
    """A straight drop, only when the words say it is one: the speed is path-free."""
    if not p.get("free_fall"):
        return []
    h, g = p["h"], p["g"]
    scene = vertical_scene(h, 0.0, g, math.sqrt(2 * h / g), ground=True)
    return [scene] if scene else []


def _drop_height(p: dict[str, float], value: float) -> Scenes:
    scene = vertical_scene(value, 0.0, p["g"], p["t"], ground=True, height_given=False)
    return [scene] if scene else []


def _fall_after(p: dict[str, float], value: float) -> Scenes:
    scene = vertical_scene(0.0, 0.0, p["g"], p["t"], ground=False)
    return [scene] if scene else []


def _circle_string(p: dict[str, float], value: float) -> Scenes:
    m, v, r = p["m"], p["v"], p["r"]
    return [
        _orbit_scene(
            r,
            tether=True,
            arrow_labels={
                "velocity": f"v = {_given(v)} m/s",
                "centripetal": f"T = {plain_number(value)} N",
            },
            alt=(
                f"A {_kg(m)} ball on a {_given(r)} m string going round at {_given(v)} m/s; "
                f"the string pulls it inward with {plain_number(value)} N."
            ),
        )
    ]


def _kepler_altitude(p: dict[str, float], value: float) -> Scenes:
    radius, height = p["radius_body"], p["altitude"]
    r = radius + height
    speed = 2 * math.pi * r / value
    name = body_name(p["M"], radius)
    return [
        _orbit_scene(
            r,
            planet=(radius, name),
            # The pull is labelled so the arrow toward the planet's centre is
            # read as gravity, and the planet's name moves clear of it.
            arrow_labels={"velocity": f"v = {plain_number(speed)} m/s", "centripetal": "gravity"},
            alt=(
                f"A satellite {plain_number(height / 1000)} km above {name or 'the planet'} "
                f"goes round once every {plain_number(value / 60)} minutes."
            ),
        )
    ]


def _pendulum_length(p: dict[str, float], value: float) -> Scenes:
    return [_pendulum_scene(value, p["period"], length_given=False)]


def _spring_compression(p: dict[str, float], value: float) -> Scenes:
    period = 2 * math.pi * math.sqrt(p["m"] / p["k"])
    scene = _spring_scene(_displacement_samples(period, value), value, stated=True, period=period)
    return [
        scene.model_copy(
            update={
                "alt": (
                    f"A {_kg(p['m'])} cart at {_given(p['v'])} m/s squeezes the spring "
                    f"{plain_number(value)} m before it pushes back."
                )
            }
        )
    ]


# --- momentum --------------------------------------------------------------------


def _apart(heavy: float, light: float, slow: float, fast: float, alt: str) -> Scenes:
    """Two bodies at rest pushing apart: the heavier one left, the lighter right."""
    return [_collision_scene(heavy, light, 0.0, 0.0, -slow, fast, recoil=alt)]


def _recoil(p: dict[str, float], value: float) -> Scenes:
    gun, shot, v = p["m_gun"], p["m_shot"], p["v"]
    return _apart(
        gun,
        shot,
        value,
        v,
        f"A {_kg(gun)} launcher fires a {_kg(shot)} shot forward at {_given(v)} m/s "
        f"and recoils at {plain_number(value)} m/s.",
    )


def _push_off(first: float, second: float, v_first: float, v_second: float) -> Scenes:
    return _apart(
        first,
        second,
        v_first,
        v_second,
        f"A {_kg(first)} body and a {_kg(second)} body push apart from rest: "
        f"{plain_number(v_first)} m/s one way and {plain_number(v_second)} m/s the other.",
    )


def _push_off_second(p: dict[str, float], value: float) -> Scenes:
    return _push_off(p["m_first"], p["m_second"], p["v_first"], value)


def _push_off_first(p: dict[str, float], value: float) -> Scenes:
    return _push_off(p["m_first"], p["m_second"], value, p["v_second"])


# --- energy ----------------------------------------------------------------------


def _work_against_gravity(p: dict[str, float], value: float) -> Scenes:
    return height_scene(p["m"], p["g"], p["h"])


# --- circuits, optics and waves --------------------------------------------------


def _current_from_power(p: dict[str, float], value: float) -> Scenes:
    power, voltage = p["power"], p["V"]
    return [
        SimulationBlockSpec(
            type="circuit",
            title="Circuit",
            title_key="circuit",
            circuit=CircuitSpec(
                source=CircuitSource(label=f"{_given(voltage)} V"),
                load=CircuitNode(part="resistor", label=f"P = {_given(power)} W"),
                current=f"I = {plain_number(value)} A",
            ),
            alt=(
                f"A {_given(power)} W appliance on {_given(voltage)} V "
                f"draws {plain_number(value)} A."
            ),
        )
    ]


def _snell(p: dict[str, float], value: float) -> Scenes:
    incidence = math.degrees(p["angle"])
    if p.get("from_surface"):
        incidence = 90.0 - incidence
    n1, n2 = p["n1"], p["n2"]
    return interface_scene(
        incidence,
        value,
        (_medium(n1), _medium(n2)),
        asked="refracted",
        alt=(
            f"Light meets the boundary {plain_number(incidence)}° from the normal and bends "
            f"to {plain_number(value)}° passing from {_material(n1)} into {_material(n2)}."
        ),
    )


def _critical_angle(p: dict[str, float], value: float) -> Scenes:
    n = p["n1"]
    return interface_scene(
        value,
        90.0,
        (_medium(n), "air"),
        asked="incident",
        alt=(
            f"Light inside a material of index {_given(n)} meets the surface at "
            f"{plain_number(value)}° and skims along it."
        ),
    )


def _medium(n: float) -> str:
    return "air" if math.isclose(n, 1.0) else f"n = {_given(n)}"


def _material(n: float) -> str:
    return "air" if math.isclose(n, 1.0) else f"a material of index {_given(n)}"


def _wave_from_travel(p: dict[str, float], value: float) -> Scenes:
    return [travelling_scene(p["d"] / p["t"], value, p["wavelength"])]


def _em_wavelength(p: dict[str, float], value: float) -> Scenes:
    return [travelling_scene(SPEED_OF_LIGHT, p["freq"], value)]


_SCENES: dict[str, Callable[[dict[str, float], float], Scenes]] = {
    "acceleration_from_opposing_forces": lambda p, value: _opposing(p, value, net=False),
    "net_force_opposing": lambda p, value: _opposing(p, value, net=True),
    "mass_from_force": _mass_from_force,
    "speed_from_net_force": _speed_from_net_force,
    "terminal_drag": _terminal_drag,
    "applied_friction_acceleration": _applied_friction,
    "weight_along_slope": _weight_along_slope,
    "drop_speed": _drop_speed,
    "drop_height": _drop_height,
    "free_fall_speed_after": _fall_after,
    "circle_string_tension": _circle_string,
    "kepler_period_altitude": _kepler_altitude,
    "pendulum_length": _pendulum_length,
    "spring_compression_from_speed": _spring_compression,
    "recoil_speed": _recoil,
    "push_off_speed": _push_off_second,
    "push_off_speed_first": _push_off_first,
    "work_against_gravity": _work_against_gravity,
    "current_from_power": _current_from_power,
    "snell_refraction_angle": _snell,
    "critical_angle_to_air": _critical_angle,
    "wave_frequency_from_travel": _wave_from_travel,
    "em_wavelength": _em_wavelength,
}


def _magnification(intent: PhysicsIntent, value: float) -> Scenes:
    """A real image from a lens, in the question's own length unit."""
    given = intent.physics_params or {}
    units = intent.physics_units or {}
    u, v = given.get("d_obj", 0.0), given.get("d_img", 0.0)
    unit = units.get("d_obj", "m")
    if u <= 0 or v <= 0 or units.get("d_img", "m") != unit or unit not in ("m", "cm", "mm"):
        return []
    return lens_scene(u, u * v / (u + v), v, unit)


def catalog_scene(intent: PhysicsIntent, p: dict[str, float], value: float) -> Scenes:
    """The picture for this solved catalog law, or nothing when it has none.

    A builder that cannot draw these values (a zero length, a mass missing)
    is no picture rather than a failed answer: the number is already verified.
    """
    op = intent.physics_op or ""
    try:
        if op == "magnification_distances":
            return _magnification(intent, value)
        builder = _SCENES.get(op)
        return builder(p, value) if builder else []
    except (KeyError, ValueError, ZeroDivisionError):
        return []
