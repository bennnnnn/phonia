"""P17: vector forces — resultants and components.

Everything else on the `force` kind is scalar, which is why "a 3 N force east
and a 4 N force north" had no answer at all.

The ticket asked which extractor should own this, since `modules/math/` already
has a `vector` kind for magnitude/dot/cross. It cannot: that one matches literal
angle-bracket operands ("magnitude of <3, 4>") through
`is_closed_coordinate_vector_request`, and a force question names units and
compass directions instead. The two never see the same sentence. This is a
physics extractor and the maths one is untouched — asserted below rather than
asserted in a PR description.
"""

from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.modules.math.tools import _build_verified_block as build_math_block
from app.modules.math.tools import extract_math_intent as extract_real_math_intent
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

PHYSICS_KINDS = {
    "kinematics",
    "suvat",
    "projectile",
    "force",
    "energy",
    "momentum",
    "friction",
    "circular",
    "spring",
    "circuit",
    "torque",
}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


VERIFIED: list[tuple[str, str, str]] = [
    # 3-4-5, and the bearing is measured from the first force.
    (
        "a 3 N force east and a 4 N force north, what is the resultant",
        "resultant_force",
        "5 N at 53.1°",
    ),
    (
        "what is the resultant of a 3 N and a 4 N force at right angles",
        "resultant_force",
        "5 N at 53.1°",
    ),
    (
        "find the resultant of a 3 N horizontal force and a 4 N vertical force",
        "resultant_force",
        "5 N at 53.1°",
    ),
    (
        "Two forces act on an object: 3 N east and 4 N north. "
        "Find the resultant magnitude and direction.",
        "resultant_force",
        "5 N at 53.1°",
    ),
    # Not perpendicular: the general parallelogram law.
    (
        "what is the resultant of a 3 N and a 4 N force at 60 degrees to each other",
        "resultant_force",
        "6.08 N at 34.7°",
    ),
    (
        "resolve a 10 N force at 30 degrees into components",
        "resolve_force",
        "8.66 N horizontally and 5 N vertically",
    ),
    (
        "find the components of a 10 N force acting at 30 degrees",
        "resolve_force",
        "8.66 N horizontally and 5 N vertically",
    ),
    (
        "resolve a 10 N force acting at 30 degrees into horizontal and vertical components",
        "resolve_force",
        "8.66 N horizontally and 5 N vertically",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_vector_force_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)

    assert intent is not None, "no intent extracted"
    assert intent.kind == "force"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_both_ops_have_at_least_three_phrasings() -> None:
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert set(covered) == {"resultant_force", "resolve_force"}
    assert {op: n for op, n in covered.items() if n < 3} == {}


# --- the physics ------------------------------------------------------------


def test_perpendicular_is_the_general_law_at_ninety_degrees() -> None:
    """One formula, not two.

    R = sqrt(F1² + F2² + 2F1F2cos φ) drops its cosine term at 90°, so the
    right-angle case needs no separate branch — and if someone later adds one,
    this catches the two drifting apart.
    """
    perpendicular = _verified_answer(
        "what is the resultant of a 3 N and a 4 N force at right angles"
    )
    stated = _verified_answer(
        "what is the resultant of a 3 N and a 4 N force at 90 degrees to each other"
    )

    assert perpendicular == stated == "5 N at 53.1°"


def test_the_components_rebuild_the_force_they_came_from() -> None:
    """Resolve then recombine: the round trip has to return the original.

    A swapped sine and cosine passes a magnitude check and fails this one.
    """
    answer = _verified_answer("resolve a 10 N force at 30 degrees into components")

    assert answer is not None
    fx, fy = (float(part.split()[0]) for part in answer.split(" and "))

    assert math.hypot(fx, fy) == pytest.approx(10.0, abs=0.01)
    assert math.degrees(math.atan2(fy, fx)) == pytest.approx(30.0, abs=0.01)
    # cos(30°) > sin(30°), so the horizontal component is the larger one.
    assert fx > fy


def test_the_bearing_is_measured_from_the_first_force() -> None:
    """53.13° is atan(4/3), not atan(3/4).

    Which force the angle is measured from is a choice, and the wrong one gives
    36.87° — a plausible number for the same question. Naming it pins the
    convention.
    """
    answer = _verified_answer("a 3 N force east and a 4 N force north, what is the resultant")

    assert answer is not None
    bearing = float(answer.split(" at ")[1].rstrip("°"))

    assert bearing == pytest.approx(math.degrees(math.atan2(4, 3)), rel=5e-3)
    assert bearing != pytest.approx(math.degrees(math.atan2(3, 4)), rel=5e-3)


def test_two_forces_in_line_simply_add() -> None:
    """The degenerate case the parallelogram law still has to get right."""
    answer = _verified_answer(
        "what is the resultant of a 3 N and a 4 N force at 0 degrees to each other"
    )

    assert answer is not None
    assert float(answer.split()[0]) == pytest.approx(7.0, abs=0.01)


def test_two_opposed_forces_cancel_to_their_difference() -> None:
    answer = _verified_answer(
        "what is the resultant of a 3 N and a 4 N force at 180 degrees to each other"
    )

    assert answer is not None
    assert float(answer.split()[0]) == pytest.approx(1.0, abs=0.01)


# --- the cue hazard the ticket named ----------------------------------------


def test_the_maths_vector_kind_is_untouched() -> None:
    """The ticket asked which extractor should own this. Both do, separately.

    The maths one needs literal angle brackets; this one needs units. Neither
    sentence is ambiguous, so neither had to give way.
    """
    magnitude = extract_real_math_intent("magnitude of <3, 4>")
    dot = extract_real_math_intent("dot product of <1, 2> and <3, 4>")

    assert magnitude is not None and magnitude.kind == "vector"
    assert dot is not None and dot.kind == "vector"
    magnitude_block = build_math_block(magnitude, _settings())
    dot_block = build_math_block(dot, _settings())
    assert magnitude_block is not None and magnitude_block.canonical_answer == "5"
    assert dot_block is not None and dot_block.canonical_answer == "11"


NOT_PHYSICS = [
    "lets resolve this issue in 3 days",
    "the components of the plan take 3 weeks",
    "resolve the 2 merge conflicts",
    "what are the 3 components of the system",
    "the resultant of the meeting was 2 action items",
    "solve 2x + 7 = 19",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_resolve_and_component_never_stand_alone(text: str) -> None:
    """Both are ordinary English, and these cues feed the global pre-filter.

    "resultant" is specific and still needs a newton reading; "resolve" and
    "component" are not specific at all, so they need the force *and* the angle
    before they count.
    """
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_plain_newtons_second_law_still_reaches_the_force_extractor() -> None:
    """This runs before force, so it must not swallow ordinary F = ma."""
    intent = extract_physics_intent("a 5 kg mass accelerates at 2 m/s^2, what is the net force")

    assert isinstance(intent, PhysicsIntent) and intent.physics_op == "net_force"
    assert _verified_answer("a 5 kg mass accelerates at 2 m/s^2, what is the net force") == "10 N"


UNDERSPECIFIED = [
    # The angle between them is the whole problem; two magnitudes do not imply it.
    "what is the resultant of a 3 N and a 4 N force",
    "what is the resultant force on the box",
    # Resolving needs a direction to resolve along.
    "resolve a 10 N force into components",
    "find the components of the force",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_missing_geometry_is_refused_not_assumed(text: str) -> None:
    """Assuming a right angle would be the most natural wrong answer here.

    Two magnitudes and no stated geometry describe infinitely many resultants
    between 1 N and 7 N; picking 5 N because perpendicular is common would be a
    guess wearing a verified block.
    """
    assert _verified_answer(text) is None
