"""Independent hand-worked regressions from the October physics review."""

from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.modules.physics.block import build_verified_physics_block
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.extract import extract_physics_intent
from app.modules.physics.solver import solve_physics


def result(question: str):
    intent = extract_physics_intent(question)
    assert intent is not None
    assert build_verified_physics_block(intent, Settings(math_tools_enabled=True)) is not None
    return solve_physics(intent)


@pytest.mark.parametrize(
    "description,want",
    [
        (
            "rests on a 20 degree incline with coefficient of static friction 0.4",
            5 * 9.81 * math.sin(math.radians(20)),
        ),
        ("rests on level ground with coefficient of static friction 0.4", 0),
        (
            "slides down a 20 degree incline with coefficient of kinetic friction 0.4",
            0.4 * 5 * 9.81 * math.cos(math.radians(20)),
        ),
    ],
)
def test_static_friction_is_the_equilibrium_demand(description: str, want: float) -> None:
    solved = result(f"A 5 kg block {description}. Find the friction force.")
    assert solved.quantities[0].value == pytest.approx(want)


@pytest.mark.parametrize(
    "direction,angle,coefficient,want",
    [
        ("down", 10, 0.5, 9.81 * (math.sin(math.radians(10)) - 0.5 * math.cos(math.radians(10)))),
        ("up", 30, 0.2, 9.81 * (math.sin(math.radians(30)) + 0.2 * math.cos(math.radians(30)))),
    ],
)
def test_kinetic_acceleration_keeps_motion_direction(direction, angle, coefficient, want) -> None:
    solved = result(
        f"A 5 kg block slides {direction} a {angle} degree incline with "
        f"coefficient of kinetic friction {coefficient}. Find the acceleration."
    )
    assert solved.quantities[0].value == pytest.approx(want)
    scene = solved.simulation_specs[0]
    assert all(point == scene.bodies[0].path[0] for point in scene.bodies[0].path)
    if direction == "up":
        assert "friction" not in scene.arrows
        assert scene.vectors[0].dx > 0 and scene.vectors[0].dy < 0


def test_impossible_static_equilibrium_declines() -> None:
    question = "A 5 kg block rests on a 30 degree incline with coefficient of static friction 0.2. Find the friction force."
    intent = extract_physics_intent(question)
    assert intent is not None
    assert build_verified_physics_block(intent, Settings(math_tools_enabled=True)) is None


def test_initial_rest_allows_subsequent_kinetic_sliding() -> None:
    solved = result(
        "A 5 kg block is initially at rest, then released and slides down a 30 degree "
        "incline with coefficient of kinetic friction 0.2. Find its acceleration."
    )
    assert solved.quantities[0].value == pytest.approx(9.81 * (0.5 - 0.2 * math.cos(math.pi / 6)))
    assert (
        solved.simulation_specs[0].bodies[0].path[0]
        != solved.simulation_specs[0].bodies[0].path[-1]
    )


def test_distance_reply_does_not_call_displacement_an_equivalent_distance_law() -> None:
    given = "A particle initially moves at 10 m/s and has constant acceleration -2 m/s^2 for 10 s. "
    question = given + "Find the distance travelled."
    intent = extract_physics_intent(question)
    assert intent is not None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    reply = maybe_direct_physics_reply(block, question)
    assert reply is not None and r"\int_0^t" in reply
    assert r"$s = v_i t + \tfrac{1}{2}at^2$" not in reply
    question = given + "Find the displacement."
    intent = extract_physics_intent(question)
    assert intent is not None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    reply = maybe_direct_physics_reply(block, question)
    assert reply is not None and r"$s = v_i t + \tfrac{1}{2}at^2$" in reply


@pytest.mark.parametrize(
    "duration,path_length,displacement", [(8, 34, 16), (10, 50, 0), (12, 74, -24)]
)
def test_distance_and_displacement_after_reversal(duration, path_length, displacement) -> None:
    given = f"A particle initially moves at 10 m/s and has constant acceleration -2 m/s^2 for {duration} s. "
    distance = result(given + "Find the distance travelled.")
    assert distance.quantities[0].value == pytest.approx(path_length)
    assert distance.graph_specs[0].points[-1][1] == pytest.approx(path_length)
    assert all(
        a[1] <= b[1]
        for a, b in zip(
            distance.graph_specs[0].points, distance.graph_specs[0].points[1:], strict=False
        )
    )
    offset = result(given + "Find the displacement.")
    assert offset.quantities[0].value == pytest.approx(displacement)
    assert offset.graph_specs[0].points[-1][1] == pytest.approx(displacement)


def test_displacement_with_distractor_mass_uses_the_same_motion() -> None:
    solved = result(
        "A 2 kg car with initial velocity 5 m/s accelerates at 2 m/s^2. Find its displacement after 4 s."
    )
    assert solved.quantities[0].value == 36


def test_mixed_unit_collision_working_uses_si() -> None:
    solved = result(
        "A 2 kg ball moving at 20 m/s collides elastically with a 500 g ball at rest. Find the final velocities."
    )
    assert [q.value for q in solved.quantities] == pytest.approx([12, 32])
    assert "500" not in " ".join(solved.substitutions)
    assert "0.5" in " ".join(solved.substitutions)


def test_atwood_orders_masses_after_unit_conversion() -> None:
    solved = result(
        "An Atwood machine connects masses of 4 lb and 3 kg over a pulley. Find the acceleration and tension."
    )
    mass_lb = 4 * 0.45359237
    assert solved.quantities[0].value == pytest.approx((3 - mass_lb) * 9.81 / (3 + mass_lb))
    assert solved.simulation_specs[0].bodies[0].label == "3 kg"


def test_vertical_and_microscopic_motion_remain_drawable() -> None:
    vertical = result("A projectile is launched at 10 m/s at 90 degrees. Find the maximum height.")
    assert vertical.quantities[0].value == pytest.approx(100 / (2 * 9.81))
    assert vertical.simulation_specs[0].x_max > vertical.simulation_specs[0].x_min
    orbit = result(
        "A particle moves at 1 m/s in a circle of radius 0.000001 m. Find its centripetal acceleration."
    )
    path = orbit.simulation_specs[0].bodies[0].path
    assert max(x for x, y in path) > 0 and min(x for x, y in path) < 0
    for x, y in path:
        assert math.hypot(x, y) == pytest.approx(1e-6)


@pytest.mark.parametrize(
    "question",
    [
        "Find the potential energy of a 2 kg object at a height of 10 m.",
        "A 10 N force moves a block 5 m in the direction of the force. Find the work done.",
        "What is the resultant of a 3 N and a 10 N force at 150 degrees to each other?",
    ],
)
def test_scene_bounds_include_every_vector_endpoint(question: str) -> None:
    scene = result(question).simulation_specs[0]
    for vector in scene.vectors:
        for x, y in (vector.anchor, [vector.anchor[0] + vector.dx, vector.anchor[1] + vector.dy]):
            assert scene.x_min <= x <= scene.x_max
            assert scene.y_min <= y <= scene.y_max
    if "potential energy" in question:
        assert scene.bodies[0].path[0][1] == 10
        assert scene.ground
