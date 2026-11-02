"""Regression coverage for complete quantities and whole physics requests."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from app.modules.physics.numbers import normalize_physics_numbers
from app.modules.physics.request import (
    PhysicsRequest,
    _collision_intent,
    _projectile_parts,
    complete_physics_intent,
)
from app.modules.physics.schemas import PhysicsIntent


@pytest.mark.parametrize(
    "literal,expected",
    [
        (".5", "0.5"),
        ("-.5", "-0.5"),
        ("+.5", "0.5"),
        ("5e-1", "0.5"),
        ("5E-1", "0.5"),
        ("-5e-1", "-0.5"),
        ("2e1", "20"),
        ("2E+1", "20"),
        ("+20.00", "20"),
        ("0", "0"),
        ("-0.0", "0"),
        ("0.005", "0.005"),
        ("0e-1000000", "0"),
        ("0e1000000", "0"),
        ("6e24", "6000000000000000000000000"),
        ("1e-2", "0.01"),
        ("1,000", "1000"),
        ("1,234,567.50", "1234567.5"),
        ("-12,500", "-12500"),
    ],
)
def test_complete_number_spellings(literal: str, expected: str) -> None:
    normalized = normalize_physics_numbers(f"mass {literal} kg")
    assert normalized == f"mass {expected} kg"
    assert normalize_physics_numbers(normalized) == normalized


@pytest.mark.parametrize(
    "literal",
    [
        "1e+",
        "1e-",
        "1e",
        "1.2.3",
        "1..2",
        "1,00",
        "12,34",
        "1,000,00",
        "1_000",
        "--.5",
        "- .5",
        "1/2",
        "1e1000000",
        "1e-1000000",
        "1e1.5",
        "9" * 129,
    ],
)
def test_malformed_or_oversized_numbers_are_refused(literal: str) -> None:
    assert normalize_physics_numbers(f"mass {literal} kg") is None


def test_a_finite_exponent_past_the_window_stays_scientific() -> None:
    normalized = normalize_physics_numbers("lambda is 1.00e-52 /m^2")
    assert normalized == "lambda is 1e-52 /m^2"
    assert normalize_physics_numbers(normalized) == normalized


def test_unit_case_labels_and_sentence_punctuation_are_preserved() -> None:
    assert normalize_physics_numbers("v0 = 2e1 m/s. Use g = 1e-2 m/s^2.") == (
        "v0 = 20 m/s. Use g = 0.01 m/s^2."
    )
    assert normalize_physics_numbers("12 V and 3 A") == "12 V and 3 A"
    assert normalize_physics_numbers("mass .5kg") == "mass 0.5kg"


@pytest.mark.parametrize("model", ["inelastically", "in an inelastic collision", "elastically"])
def test_a_collision_does_not_invent_the_second_velocity(model: str) -> None:
    assert _collision_intent(f"a 2 kg ball at 3 m/s collides {model} with a 1 kg ball") is None


@pytest.mark.parametrize("model", ["inelastically", "in an inelastic collision"])
def test_inelastic_alone_does_not_mean_sticking(model: str) -> None:
    assert (
        _collision_intent(f"a 2 kg ball at 3 m/s collides {model} with a 1 kg ball at rest") is None
    )


@pytest.mark.parametrize(
    "model", ["elastically", "perfectly inelastically", "completely inelastically"]
)
def test_explicit_collision_givens_are_preserved(model: str) -> None:
    intent = _collision_intent(f"a 2 kg ball at 3 m/s collides {model} with a 1 kg ball at rest")
    assert intent is not None
    assert intent.physics_params == {
        "m1": 2.0,
        "m2": 1.0,
        "v1": 3.0,
        "v2": 0.0,
        "elastic": float(model == "elastically"),
    }


def test_rest_belongs_to_the_correct_body() -> None:
    intent = _collision_intent("a 2 kg ball at rest collides elastically with a 1 kg ball at 3 m/s")
    assert intent is not None
    assert intent.physics_params is not None
    assert (intent.physics_params["v1"], intent.physics_params["v2"]) == (0.0, 3.0)


def test_sticking_with_mixed_mass_units() -> None:
    intent = _collision_intent(
        "a 500 g ball at 3 m/s hits a 1 kg ball at rest and they stick together"
    )
    assert intent is not None
    assert intent.physics_units is not None
    assert intent.physics_units["m1"] == "g"
    assert intent.physics_units["m2"] == "kg"


@pytest.mark.parametrize(
    "text",
    [
        "a 2 kg ball collides elastically with a 1 kg ball at 3 m/s",
        "a 2 kg ball at 3 m/s hits a 1 kg ball not at rest elastically",
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically at 30 degrees",
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically with restitution 0.5",
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically after 5 s",
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically; find energy lost",
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically and they stick together",
        "a -2 kg ball at 3 m/s hits a 1 kg ball at rest elastically",
        "a 2 kg ball at 3 m/s hits a 0 kg ball at rest elastically",
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest and a 4 kg ball at rest elastically",
        "a 2 kg ball at rest moving at 3 m/s hits a 1 kg ball at rest elastically",
    ],
)
def test_collision_conditions_are_not_silently_discarded(text: str) -> None:
    assert _collision_intent(text) is None


@pytest.mark.parametrize(
    "order", list(itertools.permutations(["time of flight", "maximum height", "range"]))
)
def test_multipart_projectile_order_is_preserved(order: tuple[str, ...]) -> None:
    labels = {"time of flight": "time_of_flight", "maximum height": "max_height", "range": "range"}
    text = (
        "A projectile is launched at 20 m/s at 30 degrees. Find "
        + ", ".join(order)
        + ". Use g = 9.8 m/s^2."
    )
    assert _projectile_parts(text) == tuple(labels[item] for item in order)


@pytest.mark.parametrize(
    "text",
    [
        "A projectile at 20 m/s at 30 degrees. Find maximum height, range, and kinetic energy.",
        "A projectile at 20 m/s at 30 degrees. Find maximum height and range. Find the time of flight.",
        "A projectile at 20 m/s at 30 degrees. Find maximum height and range. Also the time of flight.",
        "A projectile at 20 m/s at 30 degrees with wind at 5 m/s. Find maximum height and range.",
        "A projectile at 20 m/s at 30 degrees. A wall is 15 m away. Find maximum height and range.",
        "A projectile at 20 m/s at 30 degrees of mass 2 kg. Find maximum height and range.",
        "A projectile at 20 m/s at 30 degrees. Maximum height and range?",
        "A projectile at 20 m/s at 30 degrees with air resistance. Find maximum height and range.",
    ],
)
def test_multipart_requests_do_not_peel_off_extra_information(text: str) -> None:
    assert _projectile_parts(text) is None


def test_projectile_parts_are_validated_at_the_schema_boundary() -> None:
    valid = dict(kind="projectile", physics_op="range", requested_ops=["range", "max_height"])
    assert PhysicsIntent.model_validate(valid).requested_ops == ["range", "max_height"]
    for change in (
        {"kind": "energy"},
        {"physics_op": "time_of_flight"},
        {"requested_ops": ["range"]},
        {"requested_ops": ["range", "range"]},
        {"requested_ops": ["range", "kinetic_energy"]},
    ):
        with pytest.raises(ValidationError):
            PhysicsIntent.model_validate({**valid, **change})


def test_another_physics_kind_cannot_answer_a_projectile_list() -> None:
    intent = PhysicsIntent(kind="force", physics_op="net_force", physics_params={"m": 2, "a": 3})
    request = PhysicsRequest("", projectile_ops=("range", "max_height"))
    assert complete_physics_intent(intent, request) is None


def test_negative_mass_is_not_certified_after_correct_sign_parsing() -> None:
    intent = PhysicsIntent(
        kind="energy", physics_op="kinetic_energy", physics_params={"m": -0.5, "v": 2}
    )
    assert complete_physics_intent(intent, PhysicsRequest("")) is None


def test_pipeline_leading_decimal_and_scientific_notation() -> None:
    from app.tests.modules.physics.support import extract_physics_intent

    for mass in (".5", "0.5", "5e-1"):
        intent = extract_physics_intent(f"kinetic energy of a {mass} kg object moving at 2 m/s")
        assert isinstance(intent, PhysicsIntent)
        assert intent.physics_params is not None and intent.physics_params["m"] == 0.5
    intent = extract_physics_intent(
        "A projectile is launched at 2e1 m/s at 30 degrees. Find the range. Use g = 1e-2 m/s^2."
    )
    assert isinstance(intent, PhysicsIntent)
    assert intent.physics_params is not None
    assert intent.physics_params["v0"] == 20
    assert intent.physics_params["g"] == 0.01


@pytest.mark.parametrize("mass", ["1.2.3", "1e+", "1,00", "1/2"])
def test_pipeline_invalid_quantity_never_falls_through_to_algebra(mass: str) -> None:
    from app.tests.modules.physics.support import extract_physics_intent

    assert extract_physics_intent(f"kinetic energy of a {mass} kg object moving at 2 m/s") is None


def test_pipeline_accepts_standard_grouped_thousands() -> None:
    from app.tests.modules.physics.support import extract_physics_intent

    intent = extract_physics_intent("kinetic energy of a 1,000 kg object moving at 2 m/s")
    assert isinstance(intent, PhysicsIntent)
    assert intent.physics_params is not None and intent.physics_params["m"] == 1000


def test_pipeline_rejects_missing_collision_conditions() -> None:
    from app.tests.modules.physics.support import extract_physics_intent

    assert extract_physics_intent("a 2 kg ball at 3 m/s hits a 1 kg ball elastically") is None
    assert (
        extract_physics_intent("a 2 kg ball at 3 m/s hits a 1 kg ball at rest inelastically")
        is None
    )


def test_pipeline_all_projectile_answers_share_one_visual() -> None:
    from app.core.config import Settings
    from app.tests.modules.physics.support import (
        build_verified_physics_block,
        extract_physics_intent,
    )

    text = (
        "A projectile is launched at 20 m/s at 30 degrees. Find the total time of flight, "
        "maximum height, and horizontal range. Use g = 9.8 m/s^2."
    )
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent)
    assert intent.requested_ops == ["time_of_flight", "max_height", "range"]
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None and block.canonical_answer is not None
    for value in ("2.04", "5.1", "35.3"):
        assert value in block.canonical_answer
    fences = [block.canonical_fence, *block.canonical_fences]
    # One picture: the scene carries R, H and the launch angle; no graph repeats it.
    assert sum(f is not None and f.get("type") == "trajectory" for f in fences) == 0
    assert sum(f is not None and f.get("type") == "projectile_motion" for f in fences) == 1


def test_pipeline_a_failed_part_does_not_publish_a_partial_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings
    from app.modules.physics import block as physics_block
    from app.modules.physics.solver import PhysicsResult
    from app.services.solving import SolveServiceError

    intent = PhysicsIntent(
        kind="projectile",
        physics_op="range",
        requested_ops=["range", "max_height"],
        physics_params={"v0": 20, "angle": 30, "g": 9.8},
        physics_units={"angle": "deg"},
    )
    original = physics_block.solve_physics

    def fail_second(part: PhysicsIntent) -> PhysicsResult:
        if part.physics_op == "max_height":
            raise SolveServiceError("second part failed")
        return original(part)

    monkeypatch.setattr(physics_block, "solve_physics", fail_second)
    lines: list[str] = []
    result = physics_block._build_physics_block(intent, Settings(math_tools_enabled=True), lines)
    assert result is None
    assert lines == []
