"""Physics solvers — SymPy symbolic kinematics/projectile/force/energy."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable

import pytest

from app.core.config import Settings
from app.modules.math.solve import SolveServiceError
from app.modules.physics import block as physics_block
from app.modules.physics import solver as physics_solver
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.average_speed import solve_average_speed
from app.modules.physics.solvers.rates import _solve_distance_speed_time
from app.modules.physics.solvers.relative_motion import solve_relative_motion
from app.modules.physics.solvers.results import PhysicsResult
from app.modules.physics.solvers.stopping import _solve_stopping_distance
from app.modules.physics.solvers.two_stage import solve_two_stage

# ---------------------------------------------------------------------------
# Kinematics
# ---------------------------------------------------------------------------


def test_kinematics_time_to_ground() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"h0": 20.0, "v0": 0.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)
    # t = sqrt(2*20/9.81) ≈ 2.02 s
    expected = math.sqrt(2 * 20 / 9.81)
    assert abs(result.quantities[0].value - expected) < 0.01
    # One picture: the drop from its ledge, not a height-time curve beside it.
    assert result.graph_specs == []
    (scene,) = result.simulation_specs
    assert scene.title_key == "free_fall" and scene.ground
    body = scene.bodies[0]
    # From 20 m to the landing itself, not a sample past it.
    assert body.path[0][1] == pytest.approx(20.0 + body.radius)
    assert body.path[-1][1] == pytest.approx(body.radius)
    assert [vector.label for vector in scene.vectors] == ["h = 20 m"]
    # It falls beside the ledge with air between them, not down the ledge's face.
    (ledge,) = scene.solids
    assert body.path[0][0] - body.radius - ledge.rect[2] >= body.radius


def test_kinematics_time_to_ground_derivation_includes_initial_velocity() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"h0": 0.0, "v0": 15.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)

    assert abs(result.quantities[0].value - (2 * 15.0 / 9.81)) < 0.01
    assert "v_0" in result.answer
    assert "h_0" in result.answer
    assert r"\sqrt{\frac{2 \cdot 0}{9.81}}" not in result.answer


def test_kinematics_vertical_launch_maximum_height() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="vertical_max_height",
        physics_params={"h0": 0.0, "v0": 20.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2"},
        operation="solve",
    )

    result = physics_solver.solve_kinematics(intent)

    assert result.answer_value == "20.4 m"
    assert r"h_{\max}" in result.answer
    assert r"\frac{20^{2}}{2 \cdot 9.81}" in result.answer
    (scene,) = result.simulation_specs
    body = scene.bodies[0]
    assert max(y for _, y in body.path) - body.radius == pytest.approx(20.387, 0.001)


def test_kinematics_velocity_op() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="velocity",
        physics_params={"h0": 20.0, "v0": 0.0, "g": 9.81, "t": 1.0},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2", "t": "s"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)
    # v = v0 - g*t = 0 - 9.81*1 = -9.81 m/s
    assert abs(result.quantities[0].value - (-9.81)) < 0.01
    spec = result.graph_specs[0]
    assert spec.x_max == pytest.approx(1.0)
    assert spec.points[-1][0] == pytest.approx(1.0, abs=1e-4)
    assert spec.points[-1][1] == pytest.approx(-9.81, abs=1e-3)


def test_kinematics_speed_op_is_magnitude() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="speed",
        physics_params={"h0": 20.0, "v0": 0.0, "g": 9.81, "t": 1.0},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2", "t": "s"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)
    assert abs(result.quantities[0].value - 9.81) < 0.01
    assert result.quantities[0].value > 0
    assert r"\lvert v_0 - g \cdot t\rvert" in result.answer


def test_kinematics_thrown_down_latex_parenthesises_negative_v0() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"h0": 20.0, "v0": -5.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)
    assert r"(-5)^{2}" in result.answer
    assert "-5^2" not in result.answer
    assert abs(result.quantities[0].value - 1.57) < 0.02


def test_params_in_si_rejects_length_as_velocity() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"h0": 20.0, "v0": 5.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "miles", "g": "m/s^2"},
        operation="solve",
    )
    with pytest.raises(SolveServiceError, match="does not match expected dimension"):
        physics_solver.solve_kinematics(intent)


def test_kinematics_position_op_uses_requested_time() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="position",
        physics_params={"h0": 20.0, "v0": 5.0, "g": 9.81, "t": 2.0},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2", "t": "s"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)

    expected = 20.0 + 5.0 * 2.0 - 0.5 * 9.81 * 2.0**2
    assert abs(result.quantities[0].value - expected) < 0.01


def test_kinematics_position_past_impact_is_not_verified() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="position",
        physics_params={"h0": 20.0, "v0": 0.0, "g": 9.81, "t": 10.0},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2", "t": "s"},
        operation="solve",
    )
    with pytest.raises(SolveServiceError, match="already on the ground"):
        physics_solver.solve_kinematics(intent)
    settings = Settings()
    assert physics_block._build_physics_block(intent, settings, []) is None


def test_kinematics_velocity_past_impact_is_not_verified() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="velocity",
        physics_params={"h0": 100.0, "v0": 0.0, "g": 9.81, "t": 10.0},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2", "t": "s"},
        operation="solve",
    )
    with pytest.raises(SolveServiceError, match="already on the ground"):
        physics_solver.solve_kinematics(intent)


def test_kinematics_acceleration_is_constant() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="acceleration",
        physics_params={"h0": 20.0, "v0": 0.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_kinematics(intent)
    # a = -g = -9.81 m/s^2, no graph for constant acceleration
    assert "m/s" in result.answer_value
    assert len(result.graph_specs) == 0


_VERTICAL_UNITS = {"h0": "m", "v0": "m/s", "g": "m/s^2", "t": "s"}


def _vertical(op: str, **params: float) -> PhysicsIntent:
    return PhysicsIntent(
        kind="kinematics",
        physics_op=op,
        physics_params=params,
        physics_units={name: _VERTICAL_UNITS[name] for name in params},
    )


def test_kinematics_time_to_peak_answers_the_top_and_draws_the_whole_trip() -> None:
    result = physics_solver.solve_kinematics(_vertical("time_to_peak", v0=19.62, g=9.81))

    assert result.answer_value == "2 s"
    assert result.formulas == (r"t_{\text{top}} = \frac{v_0}{g}",)
    assert result.graph_specs == []
    (scene,) = result.simulation_specs
    assert scene.title_key == "free_fall" and scene.ground


@pytest.mark.parametrize(
    ("op", "symbol", "value"),
    [("speed", r"v_{impact} = \sqrt", 19.81), ("velocity", r"v = -\sqrt", -19.81)],
)
def test_kinematics_speed_without_a_time_is_the_impact(op: str, symbol: str, value: float) -> None:
    result = physics_solver.solve_kinematics(_vertical(op, h0=20.0, v0=0.0, g=9.81))

    assert result.formulas[0].startswith(symbol)
    assert result.quantities[0].value == pytest.approx(value, abs=0.01)
    (graph,) = result.graph_specs
    assert graph.x_max == pytest.approx(math.sqrt(2 * 20.0 / 9.81))
    assert graph.points[-1][1] == pytest.approx(value, abs=0.01)
    (scene,) = result.simulation_specs
    assert scene.ground


def test_kinematics_speed_graph_plots_the_magnitude() -> None:
    result = physics_solver.solve_kinematics(_vertical("speed", h0=20.0, v0=5.0, g=9.81, t=2.0))

    (graph,) = result.graph_specs
    assert graph.expr == "v(t) = |5 - 9.81*t|"
    assert graph.title == "Speed vs. Time" and graph.y_label == "Speed (m/s)"
    assert graph.trajectory_type == "velocity_vs_time"
    assert len(graph.points) == 100
    assert all(speed >= 0 for _, speed in graph.points)
    assert graph.points[-1] == [2.0, 14.62]


def test_kinematics_velocity_at_release_has_no_picture() -> None:
    result = physics_solver.solve_kinematics(_vertical("velocity", h0=20.0, v0=5.0, g=9.81, t=0.0))

    assert result.answer_value == "5 m/s"
    assert result.graph_specs == [] and result.simulation_specs == []


def test_kinematics_rise_without_a_ledge_is_drawn_without_ground() -> None:
    result = physics_solver.solve_kinematics(_vertical("position", v0=12.0, g=9.81, t=1.0))

    assert result.formulas == (r"h = v_0 t - \frac{1}{2} g t^2",)
    (scene,) = result.simulation_specs
    assert not scene.ground


@pytest.mark.parametrize(
    ("op", "params", "reason"),
    [
        ("time_to_ground", {"v0": 0.0, "g": 9.81}, "no stated height for a fall"),
        ("position", {"v0": 0.0, "g": 9.81, "t": 1.0}, "no stated height for a fall"),
        ("speed", {"v0": 3.0, "g": 9.81}, "no stated height to land from"),
        ("acceleration", {"h0": 10.0, "g": 0.0}, "gravity must be positive"),
        ("position", {"h0": 10.0, "v0": 0.0, "g": 9.81}, "position requires a time t"),
        ("time_to_peak", {"h0": 5.0, "v0": -1.0, "g": 9.81}, "only an upward launch"),
        ("vertical_max_height", {"h0": 10.0, "v0": 0.0, "g": 9.81}, "requires v0 > 0"),
        ("time_to_ground", {"h0": 0.0, "v0": 0.0, "g": 9.81}, "no positive real time"),
    ],
)
def test_kinematics_vertical_declines(op: str, params: dict[str, float], reason: str) -> None:
    with pytest.raises(SolveServiceError, match=reason):
        physics_solver.solve_kinematics(_vertical(op, **params))


def test_kinematics_unknown_vertical_op_is_refused() -> None:
    intent = PhysicsIntent.model_construct(
        kind="kinematics", physics_op="bogus", physics_params={"h0": 5.0}, physics_units={}
    )
    with pytest.raises(SolveServiceError, match="unsupported kinematics op: bogus"):
        physics_solver.solve_kinematics(intent)


@pytest.mark.parametrize(
    ("op", "params", "units", "solver"),
    [
        (
            "rate_speed",
            {"d": 100.0, "t": 20.0},
            {"d": "m", "t": "s"},
            _solve_distance_speed_time,
        ),
        (
            "average_speed_equal_distances",
            {"v1": 30.0, "v2": 60.0},
            {"v1": "km/h", "v2": "km/h"},
            solve_average_speed,
        ),
        (
            "stopping_distance",
            {"v": 20.0, "t_react": 1.0, "decel": 5.0},
            {"v": "m/s", "t_react": "s", "decel": "m/s^2"},
            _solve_stopping_distance,
        ),
        (
            "two_stage_distance",
            {"a1": 2.0, "t1": 5.0, "t_cruise": 10.0},
            {"a1": "m/s^2", "t1": "s", "t_cruise": "s"},
            solve_two_stage,
        ),
        (
            "catch_up_time",
            {"d": 100.0, "v_chaser": 10.0, "v_target": 6.0},
            {"d": "m", "v_chaser": "m/s", "v_target": "m/s"},
            solve_relative_motion,
        ),
    ],
)
def test_kinematics_routes_other_motion_to_its_solver(
    op: str,
    params: dict[str, float],
    units: dict[str, str],
    solver: Callable[[PhysicsIntent], PhysicsResult],
) -> None:
    intent = PhysicsIntent(
        kind="kinematics", physics_op=op, physics_params=params, physics_units=units
    )

    assert physics_solver.solve_kinematics(intent) == solver(intent)


# ---------------------------------------------------------------------------
# Projectile
# ---------------------------------------------------------------------------


def test_projectile_range_45_degrees() -> None:
    intent = PhysicsIntent(
        kind="projectile",
        physics_op="range",
        physics_params={"v0": 15.0, "angle": 45.0, "g": 9.81},
        physics_units={"v0": "m/s", "angle": "deg", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_projectile(intent)
    # R = v0^2 * sin(2*45) / g = 225 * 1 / 9.81 ≈ 22.94 m
    expected = 15.0**2 * math.sin(math.radians(90)) / 9.81
    assert abs(result.quantities[0].value - expected) < 0.01
    assert result.graph_specs == []
    (scene,) = result.simulation_specs
    body = scene.bodies[0]
    # From the origin to the ground, resting on it.
    assert body.path[0] == [0.0, body.radius]
    assert body.path[-1][1] == pytest.approx(body.radius)


def test_projectile_range_from_cliff_uses_quadratic_tof() -> None:
    intent = PhysicsIntent(
        kind="projectile",
        physics_op="range",
        physics_params={"v0": 20.0, "angle": 30.0, "h0": 10.0, "g": 9.81},
        physics_units={"v0": "m/s", "angle": "deg", "h0": "m", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_projectile(intent)
    range_m = result.quantities[0].value
    # Vacuum formula is ~35.31 m; cliff quadratic TOF is ~48 m.
    assert range_m > 40.0
    assert abs(range_m - 48.0) < 1.5
    body = result.simulation_specs[0].bodies[0]
    assert body.path[0][1] == pytest.approx(10.0 + body.radius)
    assert body.path[-1][1] == pytest.approx(body.radius)


def test_projectile_max_height() -> None:
    intent = PhysicsIntent(
        kind="projectile",
        physics_op="max_height",
        physics_params={"v0": 20.0, "angle": 30.0, "g": 9.81},
        physics_units={"v0": "m/s", "angle": "deg", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_projectile(intent)
    # H = v0^2 * sin^2(30) / (2*g) = 400 * 0.25 / 19.62 ≈ 5.10 m
    expected = 20.0**2 * math.sin(math.radians(30)) ** 2 / (2 * 9.81)
    assert abs(result.quantities[0].value - expected) < 0.01


# ---------------------------------------------------------------------------
# Force
# ---------------------------------------------------------------------------


def test_force_solve_acceleration() -> None:
    intent = PhysicsIntent(
        kind="force",
        physics_op="net_force",
        physics_params={"F": 20.0, "m": 5.0},
        physics_units={"F": "N", "m": "kg"},
        operation="solve",
    )
    result = physics_solver.solve_force(intent)
    # a = F/m = 20/5 = 4 m/s^2
    assert abs(result.quantities[0].value - 4.0) < 0.01


def test_force_solve_force() -> None:
    intent = PhysicsIntent(
        kind="force",
        physics_op="net_force",
        physics_params={"m": 5.0, "a": 2.0},
        physics_units={"m": "kg", "a": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_force(intent)
    # F = m*a = 5*2 = 10 N
    assert abs(result.quantities[0].value - 10.0) < 0.01


def test_force_missing_two_knowns_raises() -> None:
    intent = PhysicsIntent(
        kind="force",
        physics_op="net_force",
        physics_params={"F": 20.0, "m": 5.0, "a": 4.0},
        physics_units={"F": "N", "m": "kg", "a": "m/s^2"},
        operation="solve",
    )
    # All three provided — solver expects exactly two.
    try:
        physics_solver.solve_force(intent)
        raise AssertionError("should have raised")
    except SolveServiceError:
        pass


# ---------------------------------------------------------------------------
# Energy
# ---------------------------------------------------------------------------


def test_energy_kinetic() -> None:
    intent = PhysicsIntent(
        kind="energy",
        physics_op="kinetic_energy",
        physics_params={"m": 2.0, "v": 10.0},
        physics_units={"m": "kg", "v": "m/s"},
        operation="solve",
    )
    result = physics_solver.solve_energy(intent)
    # KE = 0.5 * 2 * 10^2 = 100 J
    assert abs(result.quantities[0].value - 100.0) < 0.01


def test_energy_potential() -> None:
    intent = PhysicsIntent(
        kind="energy",
        physics_op="potential_energy",
        physics_params={"m": 3.0, "h": 5.0, "g": 9.81},
        physics_units={"m": "kg", "h": "m", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_energy(intent)
    # PE = m*g*h = 3*9.81*5 = 147.15 J
    expected = 3.0 * 9.81 * 5.0
    assert abs(result.quantities[0].value - expected) < 0.01


def test_energy_work() -> None:
    intent = PhysicsIntent(
        kind="energy",
        physics_op="work",
        physics_params={"F": 10.0, "d": 4.0},
        physics_units={"F": "N", "d": "m"},
        operation="solve",
    )
    result = physics_solver.solve_energy(intent)
    # W = F*d = 10*4 = 40 J
    assert abs(result.quantities[0].value - 40.0) < 0.01


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_solve_physics_dispatches_by_kind() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"h0": 20.0, "v0": 0.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m/s", "g": "m/s^2"},
        operation="solve",
    )
    result = physics_solver.solve_physics(intent)
    assert "s" in result.answer_value


def test_solve_physics_unknown_kind_raises() -> None:
    # PhysicsIntent.kind is now a closed twenty-value Literal, so an
    # out-of-domain kind can no longer reach solve_physics through the normal
    # constructor — this exercises solve_physics's own defensive dispatch-miss
    # branch directly, the way a kind added to the Literal without a matching
    # handler in solve_physics would (model_construct bypasses validation on
    # purpose, matching that scenario rather than a since-impossible one).
    intent = PhysicsIntent.model_construct(kind="equation", operation="solve")
    try:
        physics_solver.solve_physics(intent)
        raise AssertionError("should have raised")
    except SolveServiceError:
        pass


def test_physics_block_logs_expected_solver_rejection(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="position",
        physics_params={"h0": 20.0},
        operation="solve",
    )

    def reject(_intent: PhysicsIntent):
        raise SolveServiceError("position requires a time t")

    monkeypatch.setattr(physics_block, "solve_physics", reject)
    with caplog.at_level(logging.INFO, logger=physics_block.__name__):
        block = physics_block._build_physics_block(intent, Settings(), [])

    assert block is None
    assert "physics verification skipped" in caplog.text
    assert "position requires a time t" in caplog.text


def test_physics_block_requires_multiline_worked_layout() -> None:
    intent = PhysicsIntent(
        kind="force",
        physics_op="net_force",
        physics_params={"F": 20.0, "m": 5.0},
        physics_units={"F": "N", "m": "kg"},
        operation="solve",
    )

    block = physics_block._build_physics_block(intent, Settings(), [])

    assert block is not None
    for heading in ("**Given**", "**Required**", "**Formula**", "**Substitution**", "**Answer**"):
        assert heading in block.text
    assert "Put every equation on its own line" in block.text
    assert block.text.index("**Given**") < block.text.index("**Answer**")


def test_physics_block_does_not_disclaim_its_native_visual() -> None:
    intent = PhysicsIntent(
        kind="friction",
        physics_op="incline_acceleration",
        physics_params={"angle": 30.0, "mu": 0.2, "g": 9.81, "m": 4.0},
        physics_units={"angle": "deg", "g": "m/s^2", "m": "kg"},
        operation="solve",
    )

    block = physics_block._build_physics_block(intent, Settings(), [])

    assert block is not None
    assert physics_block.NATIVE_VISUAL_RULE in block.text


def test_velocity_unit_metres_raises_dimension_error() -> None:
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"h0": 20.0, "v0": 5.0, "g": 9.81},
        physics_units={"h0": "m", "v0": "m", "g": "m/s^2"},
        operation="solve",
    )
    with pytest.raises(SolveServiceError):
        physics_solver.solve_kinematics(intent)
    block = physics_block._build_physics_block(intent, Settings(), [])
    assert block is None


def test_physics_block_logs_unexpected_solver_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    intent = PhysicsIntent(
        kind="force",
        physics_op="net_force",
        physics_params={"F": 20.0, "m": 5.0},
        operation="solve",
    )

    def fail(_intent: PhysicsIntent):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(physics_block, "solve_physics", fail)
    with caplog.at_level(logging.WARNING, logger=physics_block.__name__):
        block = physics_block._build_physics_block(intent, Settings(), [])

    assert block is None
    assert "physics verification failed" in caplog.text
