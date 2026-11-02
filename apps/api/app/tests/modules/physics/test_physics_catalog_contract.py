"""Every solver branch must be a catalog input, and its substitution must use a given."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.physics.catalog import CATALOG, select_formula
from app.modules.physics.direct import format_direct_physics_working
from app.modules.physics.notation import shown
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solver import solve_physics
from app.services.workout import as_formula_heading
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

# A constant result with no quantity to insert. Everything else must show a given.
_NO_GIVEN_TO_INSERT = frozenset({"gauss_inside_shell"})

_NUMBER = re.compile(r"(?<![\d.])(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)(?![\d.])", re.IGNORECASE)


def _contains_given(text: str, value: float) -> bool:
    rendered = f"{value:g}"
    return rendered in set(_NUMBER.findall(text))


# Fixed coefficients, squares, and subscripts belong to the law, not a plugged-in given.
# A square is removed even after a subscript digit (`v_1^2`); a bare `t = 8` is not.
_LAW_COEFFICIENT = re.compile(
    r"\\t?frac\{1\}\{2\}"
    r"|\^\{-1\}"
    r"|\^(?:\{2\}|2)"
    r"|_\{?\d+\}?"
    r"|(?<![\d.])2(?=[A-Za-z\\(])"
)


def _without_law_coefficients(formula: str) -> str:
    return _LAW_COEFFICIENT.sub("", formula)


# One direct intent per solver key set. Phrasing is not involved.
_BRANCHES: tuple[tuple[str, str, dict[str, float]], ...] = (
    ("rotation", "rotational_omega", {"omega0": 2.0, "ang_alpha": 3.0, "t": 4.0}),
    ("rotation", "rotational_omega", {"omega0": 2.0, "ang_alpha": 3.0, "theta": 8.0}),
    ("rotation", "rotational_theta", {"omega0": 1.0, "ang_alpha": 2.0, "t": 3.0}),
    ("rotation", "rotational_theta", {"omega": 10.0, "omega0": 4.0, "ang_alpha": 3.0}),
    ("rotation", "rotational_theta", {"omega": 10.0, "omega0": 4.0, "t": 3.0}),
    ("rotation", "rotational_alpha", {"omega": 10.0, "omega0": 4.0, "t": 2.0}),
    ("rotation", "rotational_alpha", {"omega": 10.0, "omega0": 4.0, "theta": 14.0}),
    ("rotation", "torque_inertia", {"inertia": 2.0, "ang_alpha": 3.0}),
    ("rotation", "torque_inertia", {"tau": 6.0, "inertia": 2.0}),
    ("rotation", "torque_inertia", {"tau": 6.0, "ang_alpha": 3.0}),
    ("rotation", "torque_angular_impulse", {"L_i": 4.0, "L_f": 10.0, "t": 3.0}),
    ("rotation", "torque_angular_impulse", {"L_i": 4.0, "tau": 2.0, "t": 3.0}),
    ("rotation", "torque_angular_impulse", {"L_f": 10.0, "tau": 2.0, "t": 3.0}),
    ("rotation", "torque_angular_impulse", {"L_i": 4.0, "L_f": 10.0, "tau": 2.0}),
    (
        "rotation",
        "angular_momentum_conservation",
        {"inertia_i": 4.0, "omega_i": 2.0, "inertia_f": 1.0},
    ),
    (
        "rotation",
        "angular_momentum_conservation",
        {"inertia_i": 4.0, "omega_f": 8.0, "inertia_f": 1.0},
    ),
    (
        "rotation",
        "angular_momentum_conservation",
        {"inertia_i": 4.0, "omega_i": 2.0, "omega_f": 8.0},
    ),
    (
        "rotation",
        "angular_momentum_conservation",
        {"omega_i": 2.0, "inertia_f": 1.0, "omega_f": 8.0},
    ),
    ("rotation", "rolling_speed", {"omega": 4.0, "r": 0.5}),
    ("rotation", "rolling_speed", {"v": 2.0, "r": 0.5}),
    ("rotation", "rolling_speed", {"v": 2.0, "omega": 4.0}),
    ("rotation", "rolling_acceleration", {"ang_alpha": 8.0, "r": 0.25}),
    ("rotation", "rolling_acceleration", {"a": 2.0, "r": 0.25}),
    ("rotation", "rolling_acceleration", {"a": 2.0, "ang_alpha": 8.0}),
    ("rotation", "rolling_kinetic_energy", {"m": 3.0, "inertia": 0.06, "r": 0.2, "v": 4.0}),
    ("rotation", "rolling_kinetic_energy", {"m": 3.0, "inertia": 0.06, "r": 0.2, "omega": 20.0}),
    ("rotation", "rolling_kinetic_energy", {"m": 3.0, "inertia": 0.06, "v": 4.0, "omega": 20.0}),
    ("rotation", "parallel_axis", {"inertia_cm": 2.0, "m": 3.0, "d": 4.0}),
    ("rotation", "parallel_axis", {"inertia": 50.0, "m": 3.0, "d": 4.0}),
    ("rotation", "parallel_axis", {"inertia": 50.0, "inertia_cm": 2.0, "d": 4.0}),
    ("rotation", "parallel_axis", {"inertia": 50.0, "inertia_cm": 2.0, "m": 3.0}),
    ("energy", "work_energy", {"m": 2.0, "v1": 3.0, "v2": 5.0}),
    ("energy", "work_energy", {"W": 16.0, "v1": 3.0, "v2": 5.0}),
    ("energy", "work_energy", {"W": 16.0, "m": 2.0, "v1": 3.0}),
    ("energy", "work_energy", {"W": 10.0, "m": 2.0, "v2": 5.0}),
    ("energy", "mechanical_energy_gravity", {"v1": 3.0, "h1": 5.0, "h2": 1.0, "g": 10.0}),
    ("energy", "mechanical_energy_gravity", {"v2": 3.0, "h1": 1.0, "h2": 5.0, "g": 10.0}),
    ("energy", "mechanical_energy_gravity", {"v1": 4.0, "v2": 2.0, "h1": 8.0, "g": 10.0}),
    ("energy", "mechanical_energy_gravity", {"v1": 2.0, "v2": 4.0, "h2": 8.0, "g": 10.0}),
    ("energy", "mechanical_energy_spring", {"k": 100.0, "m": 4.0, "v1": 2.0, "x1": 0.2, "x2": 0.1}),
    ("energy", "mechanical_energy_spring", {"k": 100.0, "m": 4.0, "v2": 2.0, "x1": 0.1, "x2": 0.2}),
    ("energy", "mechanical_energy_spring", {"k": 100.0, "m": 4.0, "v1": 2.0, "v2": 0.0, "x1": 0.3}),
    ("energy", "mechanical_energy_spring", {"k": 100.0, "m": 4.0, "v1": 0.0, "v2": 2.0, "x2": 0.3}),
    ("circular", "centripetal_acceleration", {"r": 2.0, "omega": 3.0}),
    ("circular", "orbital_period", {"r": 3.0, "omega": 4.0}),
    (
        "fluids",
        "bernoulli_pressure",
        {"pres1": 120000.0, "rho": 1000.0, "v1": 4.0, "v2": 2.0, "h1": 8.0, "h2": 3.0, "g": 10.0},
    ),
    ("optics", "brewster_angle", {"n1": 1.0, "n2": 1.5}),
    ("fluids", "continuity_velocity", {"A1": 0.05, "v": 3.0, "A2": 0.02}),
    ("circuit", "kirchhoff_junction", {"i_enter": 5.0, "i_leave": 2.0}),
    ("magnetism", "gauss_inside_shell", {"Q": 1e-6, "r": 0.2, "radius_body": 1.0}),
    ("suvat", "suvat_velocity", {"u": 5.0, "a": 3.0, "t": 4.0}),
    ("suvat", "suvat_velocity", {"u": 4.0, "a": 3.0, "d": 6.0}),
    ("suvat", "suvat_velocity", {"u": 4.0, "d": 10.0, "t": 5.0}),
    ("suvat", "suvat_distance", {"u": 5.0, "a": 3.0, "t": 4.0}),
    ("suvat", "suvat_distance", {"u": 10.0, "v": 30.0, "a": 4.0}),
    ("suvat", "suvat_distance", {"u": 12.0, "v": 0.0, "t": 4.0}),
    ("suvat", "suvat_distance", {"v": 20.0, "a": 2.0, "t": 4.0}),
    ("suvat", "suvat_time", {"u": 5.0, "v": 20.0, "a": 3.0}),
    ("suvat", "suvat_time", {"u": 4.0, "a": 3.0, "d": 10.0}),
    ("suvat", "suvat_time", {"u": 4.0, "v": 6.0, "d": 20.0}),
    ("suvat", "suvat_acceleration", {"u": 5.0, "v": 20.0, "t": 5.0}),
    ("suvat", "suvat_acceleration", {"u": 20.0, "v": 0.0, "d": 100.0}),
    ("suvat", "suvat_acceleration", {"u": 0.0, "t": 5.0, "d": 37.5}),
    ("projectile", "range", {"v0": 20.0, "angle": 30.0, "h0": 10.0, "g": 9.81}),
    ("projectile", "time_of_flight", {"v0": 20.0, "angle": 30.0, "h0": 10.0, "g": 9.81}),
    ("circuit", "parallel_resistance", {"R1": 2.0, "R2": 3.0}),
    ("circuit", "parallel_resistance", {"R1": 2.0, "R2": 3.0, "R3": 5.0}),
)


@pytest.mark.parametrize(("kind", "op", "params"), _BRANCHES)
def test_each_solver_branch_is_in_the_catalog_and_substitutes(
    kind: str, op: str, params: dict[str, float]
) -> None:
    spec = CATALOG[op]
    undeclared = set(params) - {variable.name for variable in spec.variables}
    assert undeclared == set()
    intent = PhysicsIntent(kind=kind, physics_op=op, physics_params=params)  # type: ignore[arg-type]
    result = solve_physics(intent)
    assert result.formulas
    assert result.substitutions
    visible = {variable.name for variable in spec.variables if variable.visible}
    formula_text = _without_law_coefficients(" ".join(result.formulas))
    leaked = [
        name
        for name, value in params.items()
        if name in visible and _contains_given(formula_text, value)
    ]
    assert leaked == [], formula_text
    if op in _NO_GIVEN_TO_INSERT:
        assert result.substitutions == ("E = 0",)
        return
    assert result.substitutions != result.formulas
    text = " ".join(result.substitutions)
    assert any(_contains_given(text, value) for name, value in params.items() if name in visible)
    if op == "work_energy" and "v1" not in params:
        # Shown as v_i (``notation``): the starting speed of the work done.
        assert result.substitutions[0].startswith("v_i")


def test_law_coefficient_strip_keeps_a_plugged_in_number() -> None:
    assert _contains_given(_without_law_coefficients(r"t = 8"), 8.0)
    plugged = _without_law_coefficients(r"\frac{1}{2} + \frac{1}{3} + \frac{1}{5}")
    assert _contains_given(plugged, 3.0)
    assert _contains_given(plugged, 5.0)
    symbolic = _without_law_coefficients(r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta")
    assert not _contains_given(symbolic, 2.0)


def test_angular_velocity_rejects_a_supplied_omega() -> None:
    with pytest.raises(ValidationError, match="angular_velocity does not declare omega"):
        PhysicsIntent(
            kind="circular",
            physics_op="angular_velocity",
            physics_params={"r": 2.0, "omega": 3.0},
        )


def test_angular_velocity_phrasing_does_not_echo_a_supplied_omega() -> None:
    intent = extract_physics_intent(
        "what is the angular velocity at 3 rad/s around a 2 m radius circle"
    )
    if intent is not None and intent.physics_op == "angular_velocity":
        assert "omega" not in (intent.physics_params or {})


@pytest.mark.parametrize(
    ("text", "op", "required"),
    [
        (
            "Initial angular velocity of 2 rad/s and angular acceleration of 3 rad/s^2 "
            "through an angular displacement of 8 rad. Find the angular velocity.",
            "rotational_omega",
            {"omega0", "ang_alpha", "theta"},
        ),
        (
            "Angular velocity increases from 4 rad/s to 10 rad/s with angular acceleration "
            "of 3 rad/s^2. Find the angular displacement.",
            "rotational_theta",
            {"omega", "omega0", "ang_alpha"},
        ),
        (
            "Angular velocity increases from 4 rad/s to 10 rad/s in 3 s. "
            "Find the angular displacement.",
            "rotational_theta",
            {"omega", "omega0", "t"},
        ),
        (
            "Angular velocity increases from 4 rad/s to 10 rad/s through an angular "
            "displacement of 14 rad. Find the angular acceleration.",
            "rotational_alpha",
            {"omega", "omega0", "theta"},
        ),
        (
            "A 3 kg solid cylinder of radius 0.2 m rolls without slipping at 20 rad/s. "
            "Its moment of inertia is 0.06 kg m^2. Find the total kinetic energy.",
            "rolling_kinetic_energy",
            {"m", "inertia", "r", "omega"},
        ),
        (
            "centripetal acceleration at 3 rad/s with radius 2 m",
            "centripetal_acceleration",
            {"r", "omega"},
        ),
        (
            "what is the orbital period for radius 3 m at 4 rad/s",
            "orbital_period",
            {"r", "omega"},
        ),
        (
            "a car at 10 m/s accelerates at 2 m/s^2 over 8 m, what is its final speed",
            "suvat_velocity",
            {"u", "a", "d"},
        ),
        (
            "A projectile is launched at 20 m/s at 30 degrees from a 10 m cliff. "
            "What is its range?",
            "range",
            {"v0", "angle", "h0"},
        ),
    ],
)
def test_alternate_parameter_sentences_validate_and_solve(
    text: str, op: str, required: set[str]
) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == op
    assert required <= set(intent.physics_params or {})
    result = solve_physics(intent)
    assert result.quantities
    text_rows = " ".join(result.substitutions)
    assert any(_contains_given(text_rows, (intent.physics_params or {})[name]) for name in required)


# (kind, op, params, displayed law, law that must not open the reply, assumptions)
_ALTERNATE_FAMILIES: tuple[tuple[str, str, dict[str, float], str, str, tuple[str, ...]], ...] = (
    (
        "suvat",
        "suvat_velocity",
        {"u": 4.0, "a": 3.0, "d": 6.0},
        r"v = \sqrt{u^2 + 2as}",
        "v = u + at",
        (),
    ),
    (
        "suvat",
        "suvat_velocity",
        {"u": 4.0, "d": 10.0, "t": 5.0},
        r"v = \frac{2s}{t} - u",
        "v = u + at",
        (),
    ),
    (
        "suvat",
        "suvat_distance",
        {"u": 10.0, "v": 30.0, "a": 4.0, "distance_path": 0.0},
        r"s = \frac{v^2 - u^2}{2a}",
        r"s = ut + \tfrac{1}{2}at^2",
        (),
    ),
    (
        "suvat",
        "suvat_distance",
        {"u": 12.0, "v": 0.0, "t": 4.0, "distance_path": 0.0},
        r"s = \tfrac{1}{2}(u + v)t",
        r"s = ut + \tfrac{1}{2}at^2",
        (),
    ),
    (
        "suvat",
        "suvat_time",
        {"u": 4.0, "a": 3.0, "d": 10.0},
        r"\tfrac{1}{2}at^2 + ut - s = 0",
        "v = u + at",
        (),
    ),
    (
        "suvat",
        "suvat_time",
        {"u": 4.0, "v": 6.0, "d": 20.0},
        r"t = \frac{2s}{u + v}",
        "v = u + at",
        (),
    ),
    (
        "suvat",
        "suvat_acceleration",
        {"u": 20.0, "v": 0.0, "d": 100.0},
        r"a = \frac{v^2 - u^2}{2s}",
        "v = u + at",
        (),
    ),
    (
        "suvat",
        "suvat_acceleration",
        {"u": 0.0, "t": 5.0, "d": 37.5},
        r"a = \frac{2(s - ut)}{t^2}",
        "v = u + at",
        (),
    ),
    (
        "rotation",
        "rotational_omega",
        {"omega0": 5.0, "ang_alpha": 3.0, "theta": 8.0},
        r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow \omega",
        r"\omega = \omega_0 + \alpha t",
        ("constant angular acceleration",),
    ),
    (
        "rotation",
        "rotational_theta",
        {"omega": 10.0, "omega0": 4.0, "ang_alpha": 3.0},
        r"\omega^2 = \omega_0^2 + 2\alpha\Delta\theta \Rightarrow \theta",
        r"\theta = \theta_0 + \omega_0 t + \frac{1}{2}\alpha t^2",
        (
            "constant angular acceleration",
            "angular displacement is measured from zero",
        ),
    ),
    (
        "rotation",
        "rotational_alpha",
        {"omega": 10.0, "omega0": 4.0, "theta": 14.0},
        r"\alpha = \frac{\omega^2 - \omega_0^2}{2\Delta\theta}",
        r"\omega = \omega_0 + \alpha t",
        ("constant angular acceleration",),
    ),
)


@pytest.mark.parametrize(
    ("kind", "op", "params", "law", "other", "assumptions"),
    _ALTERNATE_FAMILIES,
)
def test_alternate_family_is_the_law_the_reply_opens_with(
    kind: str,
    op: str,
    params: dict[str, float],
    law: str,
    other: str,
    assumptions: tuple[str, ...],
) -> None:
    latex, lines, selected = select_formula(CATALOG[op], params)
    assert lines == ()
    assert latex == law
    assert selected == assumptions
    intent = PhysicsIntent(kind=kind, physics_op=op, physics_params=params)  # type: ignore[arg-type]
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    reply = format_direct_physics_working(block)
    assert reply is not None
    formula = as_formula_heading(reply).split("**Substitution**", 1)[0].split("**Formula**", 1)[1]
    # The reply shows the law in its shown symbols (v_f = v_i + at for v = u + at).
    assert f"${shown(law, op)}$" in formula
    assert shown(other, op) not in formula


def test_time_branch_stays_when_both_families_were_given() -> None:
    omega, _, _ = select_formula(
        CATALOG["rotational_omega"],
        {"omega0": 2.0, "ang_alpha": 3.0, "t": 4.0, "theta": 8.0},
    )
    assert omega == r"\omega = \omega_0 + \alpha t"
    velocity, _, _ = select_formula(
        CATALOG["suvat_velocity"],
        {"u": 4.0, "a": 3.0, "t": 5.0, "d": 6.0},
    )
    assert velocity == "v = u + at"


def test_parallel_resistance_formula_counts_each_resistor() -> None:
    two = solve_physics(
        PhysicsIntent(
            kind="circuit",
            physics_op="parallel_resistance",
            physics_params={"R1": 2.0, "R2": 3.0},
        )
    )
    three = solve_physics(
        PhysicsIntent(
            kind="circuit",
            physics_op="parallel_resistance",
            physics_params={"R1": 2.0, "R2": 3.0, "R3": 5.0},
        )
    )
    assert two.formulas == (r"\frac{1}{R_p} = \frac{1}{R_1} + \frac{1}{R_2}",)
    # The row names what it gives, so the working can carry it to R_p.
    assert two.substitutions == (r"\frac{1}{R_p} = \frac{1}{2} + \frac{1}{3}",)
    assert three.formulas == (r"\frac{1}{R_p} = \frac{1}{R_1} + \frac{1}{R_2} + \frac{1}{R_3}",)
    assert three.substitutions == (r"\frac{1}{R_p} = \frac{1}{2} + \frac{1}{3} + \frac{1}{5}",)
