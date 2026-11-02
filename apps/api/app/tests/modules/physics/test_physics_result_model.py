"""The catalog owns an operation, and a solve returns quantities rather than text."""

from __future__ import annotations

import math
import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.physics.block import _solve_requested_quantities
from app.modules.physics.catalog import CATALOG, select_formula
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solver import PHYSICS_SOLVERS, solve_physics
from app.modules.physics.solvers.chip import render_chip
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.working import attach_recorded_working, result_symbol_for
from app.services.solving import SolveServiceError
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
)


def test_intent_rejects_a_parameter_the_operation_does_not_declare() -> None:
    with pytest.raises(ValidationError, match="ideal_gas_pressure does not declare banana"):
        PhysicsIntent(
            kind="thermal",
            physics_op="ideal_gas_pressure",
            physics_params={"temp": 300.0, "banana": 42.0},
        )


def test_intent_rejects_a_unit_for_an_absent_parameter() -> None:
    with pytest.raises(ValidationError, match="net_force units are not parameters: F"):
        PhysicsIntent(
            kind="force",
            physics_op="net_force",
            physics_params={"m": 2.0, "a": 3.0},
            physics_units={"m": "kg", "F": "N"},
        )


def test_net_force_solve_for_names_the_missing_quantity() -> None:
    intent = PhysicsIntent(
        kind="force", physics_op="net_force", physics_params={"F": 10.0, "m": 2.0}
    )
    assert result_symbol_for(intent) == "a"


def test_intent_rejects_an_operation_from_another_kind() -> None:
    with pytest.raises(ValidationError, match="rotation does not define angular_velocity"):
        PhysicsIntent(
            kind="rotation",
            physics_op="angular_velocity",
            physics_params={"theta": 10.0, "t": 2.0},
            physics_units={"theta": "rad", "t": "s"},
        )


def test_circular_and_rotation_angular_speeds_stay_separate() -> None:
    circular = extract_physics_intent(
        "what is the angular velocity of a car going 10 m/s around a 20 m radius track"
    )
    rotation = extract_physics_intent(
        "what is the angular velocity of a wheel turning 10 radians in 2 s"
    )
    assert circular is not None and rotation is not None
    assert (circular.kind, circular.physics_op) == ("circular", "angular_velocity")
    assert (rotation.kind, rotation.physics_op) == ("rotation", "angular_displacement_rate")

    circular_result = solve_physics(circular)
    rotation_result = solve_physics(rotation)
    assert circular_result.quantities[0].value == pytest.approx(0.5)
    assert circular_result.quantities[0].unit == "rad/s"
    assert rotation_result.quantities[0].value == pytest.approx(5.0)
    assert rotation_result.quantities[0].unit == "rad/s"


def test_multipart_projectile_reads_each_quantity() -> None:
    text = (
        "A projectile is launched at 20 m/s at 30 degrees. Find the total time of flight, "
        "maximum height, and horizontal range. Use g = 9.8 m/s^2."
    )
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent)
    result = _solve_requested_quantities(intent)
    assert [item.unit for item in result.quantities] == ["s", "m", "m"]
    assert [item.symbol for item in result.quantities] == [
        r"t_{\mathrm{flight}}",
        r"H_{\mathrm{max}}",
        "R",
    ]
    assert result.answer_value == render_chip(result.quantities, "projectile")
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None and block.canonical_answer is not None
    for value in ("2.04", "5.1", "35.3"):
        assert value in block.canonical_answer


def test_work_at_an_angle_selects_the_angle_variant() -> None:
    latex, _lines, assumptions = select_formula(
        CATALOG["work"], {"F": 10.0, "d": 2.0, "angle": 60.0}
    )
    assert latex == r"W = Fd\cos\theta"
    assert assumptions == ()


def test_bernoulli_with_one_height_keeps_the_horizontal_equation() -> None:
    latex, _lines, assumptions = select_formula(
        CATALOG["bernoulli_pressure"],
        {"pres1": 100000.0, "rho": 1000.0, "v1": 2.0, "v2": 2.0, "h1": 5.0},
    )
    assert latex is not None and r"\rho gh_1" not in latex
    assert assumptions == ("horizontal flow, so the height terms cancel",)


def test_bernoulli_with_height_selects_the_full_equation() -> None:
    latex, _lines, assumptions = select_formula(
        CATALOG["bernoulli_pressure"],
        {"pres1": 100000.0, "rho": 1000.0, "v1": 2.0, "v2": 2.0, "h1": 5.0, "h2": 1.0},
    )
    assert latex is not None and r"\rho gh_1" in latex
    assert assumptions == ("steady incompressible flow with no viscosity",)


@pytest.mark.parametrize(
    ("params", "expected", "unit"),
    [
        ({"inertia_cm": 2.0, "m": 3.0, "d": 4.0}, 2.0 + 3.0 * 16.0, "kg*m^2"),
        ({"inertia": 50.0, "m": 3.0, "d": 4.0}, 50.0 - 3.0 * 16.0, "kg*m^2"),
        ({"inertia": 50.0, "inertia_cm": 2.0, "d": 4.0}, (50.0 - 2.0) / 16.0, "kg"),
        ({"inertia": 50.0, "inertia_cm": 2.0, "m": 3.0}, math.sqrt((50.0 - 2.0) / 3.0), "m"),
    ],
)
def test_parallel_axis_rearranges_every_declared_variable(
    params: dict[str, float], expected: float, unit: str
) -> None:
    intent = PhysicsIntent(kind="rotation", physics_op="parallel_axis", physics_params=params)
    result = solve_physics(intent)
    assert result.quantities[0].value == pytest.approx(expected)
    assert result.quantities[0].unit == unit
    assert result.formulas and result.substitutions


def test_a_solver_must_store_formula_and_substitution_rows() -> None:
    intent = PhysicsIntent(
        kind="force", physics_op="net_force", physics_params={"m": 2.0, "a": 3.0}
    )
    bare = PhysicsResult(
        answer=r"F = m \cdot a \approx 6",
        quantities=(QuantityResult("", 6.0, "N"),),
    )
    with pytest.raises(SolveServiceError, match="net_force did not store"):
        attach_recorded_working(bare, intent)


def test_rotational_displacement_is_measured_from_zero() -> None:
    with pytest.raises(ValidationError, match="rotational_theta does not declare theta0"):
        PhysicsIntent(
            kind="rotation",
            physics_op="rotational_theta",
            physics_params={"omega0": 1.0, "ang_alpha": 2.0, "t": 3.0, "theta0": 4.0},
        )
    intent = PhysicsIntent(
        kind="rotation",
        physics_op="rotational_theta",
        physics_params={"omega0": 1.0, "ang_alpha": 2.0, "t": 3.0},
    )
    result = solve_physics(intent)
    assert result.quantities[0].value == pytest.approx(1.0 * 3.0 + 0.5 * 2.0 * 9.0)
    assert r"\theta_0" in result.formulas[0]
    assert result.substitutions[0].startswith(r"\theta = 0 +")


def test_rpm_converts_once_to_the_same_angular_speed() -> None:
    intent = PhysicsIntent(
        kind="circular",
        physics_op="angular_velocity",
        physics_params={"rpm": 120.0},
        physics_units={"rpm": "rpm"},
    )
    result = solve_physics(intent)
    assert result.quantities[0].value == pytest.approx(120 * 2 * math.pi / 60)
    assert result.answer_value.startswith("12.6")
    assert r"120\cdot\frac{2\pi}{60}" in result.answer


_VISIBLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHORT_TOKEN = re.compile(r"^[A-Za-z](?:_[0-9A-Za-z])?$")


def test_visible_symbols_are_notation() -> None:
    leaks = [
        f"{spec.id}.{variable.name}={variable.symbol}"
        for spec in CATALOG.values()
        for variable in spec.variables
        if variable.visible
        and _VISIBLE_NAME.fullmatch(variable.symbol)
        and not _SHORT_TOKEN.fullmatch(variable.symbol)
    ]
    assert leaks == []


def test_every_catalog_operation_has_one_solver() -> None:
    assert set(PHYSICS_SOLVERS) == set(CATALOG)
