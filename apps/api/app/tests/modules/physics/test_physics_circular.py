"""P6: circular motion — centripetal force, acceleration and orbital period.

The whole risk in this ticket is the vocabulary. "circle", "radius" and
"period" all belong to subjects Recall already verifies — circle geometry and
trigonometry — and the geometry extractors run *after* physics, so any of them
used as a cue would have taken those questions rather than competed for them.
Only words that mean *motion* qualify, and "period" counts solely beside a
radius.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import _build_verified_block as build_math_block
from app.modules.math.tools import extract_math_intent as extract_real_math_intent
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

PHYSICS_KINDS = {
    "kinematics",
    "projectile",
    "force",
    "energy",
    "momentum",
    "friction",
    "circular",
}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


# v = 4 m/s, r = 3 m throughout: a_c = 16/3, F_c = 2*16/3, T = 2*pi*3/4.
VERIFIED: list[tuple[str, str, str]] = [
    (
        "centripetal force on a 2 kg mass at 4 m/s in a circle of radius 3 m",
        "centripetal_force",
        "10.7 N",
    ),
    (
        "what is the centripetal force for a 2 kg object moving at 4 m/s around a 3 m radius",
        "centripetal_force",
        "10.7 N",
    ),
    (
        "find the centripetal force on a 2 kg ball at 4 m/s with radius 3 m",
        "centripetal_force",
        "10.7 N",
    ),
    ("centripetal acceleration at 4 m/s with radius 3 m", "centripetal_acceleration", "5.33 m/s²"),
    (
        "what is the centripetal acceleration of an object moving at 4 m/s "
        "in a circle of radius 3 m",
        "centripetal_acceleration",
        "5.33 m/s²",
    ),
    (
        "find the centripetal acceleration for a 3 m radius at 4 m/s",
        "centripetal_acceleration",
        "5.33 m/s²",
    ),
    (
        "Find the centripetal acceleration for angular speed 3.00 rad/s and radius 2.00 m.",
        "centripetal_acceleration",
        "18 m/s²",
    ),
    ("period of an object moving at 4 m/s in a circle of radius 3 m", "orbital_period", "4.71 s"),
    ("what is the orbital period for radius 3 m at 4 m/s", "orbital_period", "4.71 s"),
    ("how long is one revolution at 4 m/s around a 3 m radius circle", "orbital_period", "4.71 s"),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_circular_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, "no intent extracted"
    assert intent.kind == "circular"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_circular_op_has_at_least_three_phrasings() -> None:
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert {op: n for op, n in covered.items() if n < 3} == {}
    assert set(covered) == {"centripetal_force", "centripetal_acceleration", "orbital_period"}


# --- the physics ------------------------------------------------------------


def test_stated_mass_does_not_crash_centripetal_acceleration() -> None:
    """A mass next to a = v^2/r is unused. It must not reject the intent."""
    text = (
        "A 2.00 kg mass moves at 6.00 m/s in a circle of radius 3.00 m. "
        "Find the centripetal acceleration."
    )
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == "centripetal_acceleration"
    assert intent.physics_params is not None and "m" not in intent.physics_params
    assert _verified_answer(text) == "12 m/s²"


def test_centripetal_acceleration_and_period_do_not_need_a_mass() -> None:
    """`v^2/r` and `2*pi*r/v` have no mass in them.

    Only `F = m v^2 / r` does, so only that one may require it — the same
    distinction P5 drew for the incline.
    """
    assert _verified_answer("centripetal acceleration at 4 m/s with radius 3 m") == "5.33 m/s²"
    assert _verified_answer("what is the orbital period for radius 3 m at 4 m/s") == "4.71 s"
    # …and the force question without a mass is refused rather than guessed.
    assert _verified_answer("centripetal force at 4 m/s with radius 3 m") is None


def test_force_is_mass_times_the_acceleration() -> None:
    """F_c and a_c come from one formula; they must not drift apart."""
    a_c = _verified_answer("centripetal acceleration at 4 m/s with radius 3 m")
    f_c = _verified_answer("centripetal force on a 2 kg mass at 4 m/s in a circle of radius 3 m")

    assert a_c is not None and f_c is not None
    # Each is shown to three figures, so the pair agrees to within that rounding.
    assert float(f_c.split()[0]) == pytest.approx(2 * float(a_c.split()[0]), rel=5e-3)


def test_a_tighter_circle_needs_more_acceleration() -> None:
    """a_c = v^2/r falls as r grows — the sign of the relationship, not a number."""
    tight = _verified_answer("centripetal acceleration at 4 m/s with radius 2 m")
    wide = _verified_answer("centripetal acceleration at 4 m/s with radius 8 m")

    assert tight is not None and wide is not None
    assert float(tight.split()[0]) > float(wide.split()[0])


# --- refusals and the vocabulary hazard -------------------------------------


UNDERSPECIFIED = [
    "what is the centripetal acceleration of a car going round a bend",
    "centripetal force on a 2 kg mass at 4 m/s",
    "centripetal acceleration with radius 3 m",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_circular_questions_missing_a_radius_or_speed_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "solve 2x + 7 = 19",
    "find the factors of 24",
    "the radius of the earth is 6371 km",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_circular_cues_do_not_steal_other_subjects(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


@pytest.mark.parametrize(
    "text,kind,answer",
    [
        ("area of a circle of radius 3", "circle", "28.27"),
        ("circumference of a circle with radius 3 m", "circle", "18.85"),
    ],
)
def test_circle_geometry_is_untouched(text: str, kind: str, answer: str) -> None:
    """The reason "circle" and "radius" are not cues.

    Geometry extractors run *after* physics, so either word would have taken
    these outright rather than losing a tie-break.
    """
    intent = extract_real_math_intent(text)

    assert intent is not None and intent.kind == kind
    block = build_math_block(intent, _settings())
    assert block is not None and block.canonical_answer == answer


def test_the_period_of_a_function_is_still_trigonometry() -> None:
    """ "period" only counts beside a radius; on its own it belongs to trig."""
    intent = extract_physics_intent("what is the period of the function sin(2x)")

    assert intent is None or intent.kind not in PHYSICS_KINDS
