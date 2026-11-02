"""P5: friction, normal force and inclined planes.

`routing.py`'s `_looks_like_physics_homework` already named inclines as a case
the solver could not handle, escalating them to the smarter model — the gap was
documented but unfilled. This fills it.

The negative table carries most of the weight here for one specific reason:
**"slope" is a mathematics word first.** `find the slope of the line through
(1, 2) and (3, 8)` resolves to a coordinate-geometry intent, and the geometry
extractors run *after* physics, so a "slope" cue would have stolen it outright.
It is deliberately not a cue; "ramp" and "incline" say the same thing without
the collision.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import _build_verified_block as build_math_block
from app.modules.math.tools import extract_math_intent as extract_real_math_intent
from app.modules.physics.direct import maybe_direct_physics_reply
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

PHYSICS_KINDS = {"kinematics", "projectile", "force", "energy", "momentum", "friction"}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


VERIFIED: list[tuple[str, str, str]] = [
    # f = mu N, level ground: 0.2 * 10 * 9.81
    ("friction force on a 10 kg block with coefficient 0.2", "friction_force", "19.6 N"),
    (
        "what is the friction force on a 10 kg box with a coefficient of friction of 0.2",
        "friction_force",
        "19.6 N",
    ),
    (
        "calculate the frictional force for a 10 kg crate and mu = 0.2",
        "friction_force",
        "19.6 N",
    ),
    # N = m g, and N = m g cos(theta) on a slope
    ("normal force on a 10 kg block on level ground", "normal_force", "98.1 N"),
    ("what is the normal force on a 10 kg box resting on a table", "normal_force", "98.1 N"),
    ("find the normal force for a 10 kg mass on a 30 degree incline", "normal_force", "85 N"),
    # a = g(sin(theta) - mu cos(theta))
    (
        "a 10 kg block on a 30 degree incline with coefficient of friction 0.2, "
        "what is the acceleration",
        "incline_acceleration",
        "3.21 m/s²",
    ),
    (
        "what is the acceleration of a block on a frictionless 30 degree incline",
        "incline_acceleration",
        "4.9 m/s²",
    ),
    (
        "a crate slides down a 30 degree ramp with mu = 0.2, find the acceleration",
        "incline_acceleration",
        "3.21 m/s²",
    ),
    (
        "For the 12.0 kg crate on a 30 degree incline with μs = 0.45 and "
        "μk = 0.30, does it start sliding?",
        "incline_sliding",
        "Yes, it starts sliding.",
    ),
    (
        "Will a 10 kg block on a 10 degree ramp with coefficient of static "
        "friction 0.5 start to slide?",
        "incline_sliding",
        "No, it stays at rest.",
    ),
    (
        "Does a 12 kg crate on a 30 degree incline with mu_s = 0.45 start sliding?",
        "incline_sliding",
        "Yes, it starts sliding.",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_friction_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, "no intent extracted"
    assert intent.kind == "friction"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_friction_op_has_at_least_three_phrasings() -> None:
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert {op: n for op, n in covered.items() if n < 3} == {}
    assert set(covered) == {
        "friction_force",
        "normal_force",
        "incline_acceleration",
        "incline_sliding",
    }


# --- the physics, not just the plumbing ------------------------------------


def test_incline_acceleration_does_not_depend_on_mass() -> None:
    """`a = g(sin t - mu cos t)` has no mass in it, and that is the lesson.

    So the extractor must not require one — the textbook phrasing ("a block on
    a frictionless 30 degree incline") routinely omits it — and stating a mass
    must not change the answer.
    """
    without = _verified_answer(
        "what is the acceleration of a block on a frictionless 30 degree incline"
    )
    with_mass = _verified_answer(
        "what is the acceleration of a 250 kg block on a frictionless 30 degree incline"
    )

    assert without == "4.9 m/s²"
    assert with_mass == without


def test_a_block_that_cannot_slide_is_reported_as_stationary() -> None:
    """When tan(theta) <= mu, static friction holds it.

    `g(sin t - mu cos t)` goes negative there, which read literally describes
    the block accelerating *up* the slope on its own. Zero is the true answer.
    """
    assert (
        _verified_answer(
            "a block on a 10 degree incline with coefficient of friction 0.5, "
            "what is the acceleration"
        )
        == "0 m/s²"
    )


@pytest.mark.parametrize(
    "text, expected, static_coefficient",
    [
        (
            "For the 12.0 kg crate on a 30 degree incline with μs = 0.45 and "
            "μk = 0.30, does it start sliding?",
            "Yes, it starts sliding.",
            0.45,
        ),
        (
            "Will a 10 kg block on a 10 degree ramp with coefficient of static "
            "friction 0.5 start to slide?",
            "No, it stays at rest.",
            0.5,
        ),
        (
            "Does a 12 kg crate on a 30 degree incline with mu_s = 0.45 start sliding?",
            "Yes, it starts sliding.",
            0.45,
        ),
        (
            "Will a 12 kg crate on a 30 degree incline start sliding if its static friction "
            "coefficient is 0.45?",
            "Yes, it starts sliding.",
            0.45,
        ),
        (
            "Does a block on a 30 degree incline with μ_s = 0.5773502691896257 start sliding?",
            "No, it stays at rest.",
            0.5773502691896257,
        ),
    ],
)
def test_sliding_threshold_uses_static_friction(
    text: str, expected: str, static_coefficient: float
) -> None:
    intent = extract_physics_intent(text)

    assert intent is not None
    assert intent.kind == "friction"
    assert intent.physics_op == "incline_sliding"
    assert intent.physics_params is not None
    assert intent.physics_params["mu_s"] == static_coefficient

    block = build_verified_physics_block(intent, _settings())

    assert block is not None
    assert block.canonical_answer == expected
    assert "F_{g,\\parallel}" in (block.physics_working or "")
    assert "f_{s,\\max}" in (block.physics_working or "")
    assert "Verified result" in (block.physics_working or "")
    if "12.0 kg" in text:
        assert "58.86" in (block.physics_working or "")
        assert "45.88" in (block.physics_working or "")


def test_sliding_threshold_does_not_treat_kinetic_friction_as_static() -> None:
    text = (
        "Does a 12 kg crate on a 30 degree incline start sliding if "
        "the coefficient of kinetic friction is 0.30?"
    )

    assert _verified_answer(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Does a 12 kg crate on a 30 degree incline start sliding?",
        "Does a 12 kg crate on a 30 degree incline start sliding with μ = 0.45?",
        "Does a 12 kg crate on a 30 degree incline start sliding with coefficient of friction 0.45?",
    ],
)
def test_sliding_threshold_requires_an_explicit_static_coefficient(text: str) -> None:
    assert _verified_answer(text) is None


def test_sliding_threshold_rejects_a_negative_static_coefficient() -> None:
    text = "Does a 12 kg crate on a 30 degree incline with μs = -0.45 start sliding?"

    assert _verified_answer(text) is None


def test_sliding_answer_has_a_clear_find_line_and_renderable_threshold() -> None:
    text = (
        "For the 12 kg crate on a 30 degree incline with μs = 0.45 and "
        "μk = 0.30, does it start sliding?"
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    block = build_verified_physics_block(intent, _settings())
    reply = maybe_direct_physics_reply(block, text)

    assert reply is not None
    assert "**Required**  \n$\\text{Will it start sliding?}$" in reply
    assert "Rearranged for" not in reply
    assert r"\quad mg\sin\theta>\mu_smg\cos\theta" in reply
    assert r"\quadmg" not in reply


def test_acceleration_request_keeps_priority_when_it_mentions_sliding() -> None:
    text = (
        "A 5 kg crate slides down a 30 degree incline with coefficient of kinetic "
        "friction 0.30, find acceleration."
    )
    intent = extract_physics_intent(text)

    assert intent is not None
    assert intent.physics_op == "incline_acceleration"
    assert _verified_answer(text) == "2.36 m/s²"


def test_the_slope_reduces_the_normal_force() -> None:
    """N = mg on the flat, mg*cos(theta) on a slope — strictly less."""
    level = _verified_answer("normal force on a 10 kg block on level ground")
    sloped = _verified_answer("find the normal force for a 10 kg mass on a 30 degree incline")

    assert level is not None and sloped is not None
    assert float(sloped.split()[0]) < float(level.split()[0])


# --- refusals --------------------------------------------------------------


UNDERSPECIFIED = [
    # No coefficient and not stated frictionless — the answer needs a number
    # nobody gave.
    "a 10 kg block on a 30 degree incline, what is the acceleration",
    "what is the friction force on a 10 kg block",
    "what is the friction force on a block with coefficient 0.2",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_underspecified_friction_questions_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "solve 2x + 7 = 19",
    # The reason "slope" is not a cue. This must stay coordinate geometry.
    "find the slope of the line through (1, 2) and (3, 8)",
    "the coefficient of x^2 in 3x^2 + 5x is what",
    "find the factors of 24",
    "there was friction between the two teams for 3 months",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_friction_cues_do_not_steal_other_subjects(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_slope_between_two_points_is_still_coordinate_geometry() -> None:
    """The single most likely casualty of a careless cue, pinned explicitly."""
    intent = extract_real_math_intent("find the slope of the line through (1, 2) and (3, 8)")

    assert intent is not None and intent.kind == "coord"
    block = build_math_block(intent, _settings())
    assert block is not None and block.canonical_answer == "3"


def test_a_net_force_question_is_not_answered_with_the_friction_force() -> None:
    """Mentioning friction is not asking for it.

    An earlier draft of this extractor claimed any question containing the word
    and answered mu*m*g. For "what is the net force on a 5 kg block with a
    friction coefficient of 0.2" that is a different quantity — the P2 refusal
    test caught it, and this pins the case directly.
    """
    text = "what is the net force on a 5 kg block with a friction coefficient of 0.2"

    assert _verified_answer(text) is None


def test_friction_without_a_given_does_not_engage_the_math_path() -> None:
    """These cues feed the global pre-filter, not just this extractor.

    "find the friction on a 5 kg block" names no coefficient and no angle, so
    nothing here can answer it — and firing the tool path to discover that
    costs a round for nothing.
    """
    from app.tests.modules.physics.support import needs_physics

    assert not needs_physics("find the friction on a 5 kg block")
    # With a coefficient it is solvable, so it should engage.
    assert needs_physics("find the friction force on a 5 kg block with coefficient 0.2")


def test_plain_newtons_second_law_still_reaches_the_force_extractor() -> None:
    """Friction runs *before* force, so it must not swallow ordinary F = ma."""
    intent = extract_physics_intent("a 5 kg mass accelerates at 2 m/s^2, what is the net force")

    assert intent is not None and intent.kind == "force"
    assert _verified_answer("a 5 kg mass accelerates at 2 m/s^2, what is the net force") == "10 N"
