"""Round 3: the projectile ops that are not about distance.

Three wrong answers reached users here, all one defect. The op was an
*initializer* — ``op: Literal["range", "max_height"] = "range"`` — so any
projectile question that did not say "height" was answered with the horizontal
range: "what is the time of flight" came back ``35.31 m``.

Two neighbours turned out to be the same defect wearing different hats, and are
fixed here too. ``kinematics`` runs before ``projectile`` and claimed
"launched at 20 m/s at 30 degrees, how long until it hits the ground", where it
has no angle to apply and used the whole 20 m/s as the vertical component:
``4.08 s`` against the true ``2.04 s``. And P11's collision guard matched
``\bhits?\b``, so "how fast does it hit the ground" read as a two-body
collision and got no answer at all.

The fix is the shape SUVAT already uses (``_SUVAT_UNKNOWN_RES``): a phrasing ->
op table, and a question the table does not recognise is refused rather than
answered with whatever came first.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
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


def _op(text: str) -> str | None:
    intent = extract_physics_intent(text)
    return None if intent is None else getattr(intent, "physics_op", None)


# (question, expected physics_op, expected answer). Every answer is pinned: the
# whole bug was a right number bound to the wrong question, so asserting only
# the op would have passed throughout.
VERIFIED: list[tuple[str, str, str]] = [
    # --- time of flight: t = 2 v0 sin(theta) / g -------------------------
    (
        "what is the time of flight of a ball thrown at 20 m/s at 30 degrees",
        "time_of_flight",
        "2.04 s",
    ),
    (
        "how long is a ball in the air, thrown at 20 m/s at 30 degrees",
        "time_of_flight",
        "2.04 s",
    ),
    (
        "what is the flight time of a projectile launched at 20 m/s at 30 degrees",
        "time_of_flight",
        "2.04 s",
    ),
    (
        "a projectile is fired at 20 m/s at 30 degrees, how long before it lands",
        "time_of_flight",
        "2.04 s",
    ),
    (
        "how long does a ball thrown at 20 m/s at 30 degrees stay in the air",
        "time_of_flight",
        "2.04 s",
    ),
    # --- impact speed: symmetric flight lands at the launch speed --------
    (
        "how fast is a ball going when it lands, thrown at 20 m/s at 30 degrees",
        "impact_speed",
        "20 m/s",
    ),
    (
        "what is the speed at impact of a ball thrown at 20 m/s at 30 degrees",
        "impact_speed",
        "20 m/s",
    ),
    (
        "what is the landing speed of a ball thrown at 20 m/s at 30 degrees",
        "impact_speed",
        "20 m/s",
    ),
    (
        "what is the impact velocity of a projectile launched at 20 m/s at 30 degrees",
        "impact_speed",
        "20 m/s",
    ),
    # --- launch angle: theta = 1/2 arcsin(R g / v0^2), and 90 deg - theta ---------
    (
        "at what angle should a ball be thrown at 20 m/s to travel 35 m",
        "launch_angle",
        "29.6° or 60.4°",
    ),
    (
        "what launch angle gives a range of 35 m at 20 m/s",
        "launch_angle",
        "29.6° or 60.4°",
    ),
    (
        "what angle is needed for a 20 m/s throw to reach 35 m",
        "launch_angle",
        "29.6° or 60.4°",
    ),
    # --- the two ops that already worked, so the table cannot regress ----
    ("a ball is thrown at 20 m/s at 30 degrees, what is the range?", "range", "35.3 m"),
    ("how far does a ball go if thrown at 20 m/s at 30 degrees", "range", "35.3 m"),
    ("projectile launched at 20 m/s at 30 degrees find the range", "range", "35.3 m"),
    (
        "a ball is kicked at 20 m/s at 30 degrees, how high does it go",
        "max_height",
        "5.1 m",
    ),
    (
        "what is the maximum height of a projectile launched at 20 m/s at 30 degrees",
        "max_height",
        "5.1 m",
    ),
    (
        "find the max height of a ball thrown at 20 m/s at 30 degrees",
        "max_height",
        "5.1 m",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_projectile_phrasings(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, f"no intent extracted for {text!r}"
    assert intent.kind == "projectile"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_projectile_op_has_at_least_three_phrasings() -> None:
    """The five verified ops are the contract — add the phrasings, not an exception."""
    from collections import Counter

    counts = Counter(op for _, op, _ in VERIFIED)
    thin = {op: n for op, n in counts.items() if n < 3}
    assert not thin, f"ops with fewer than three phrasings: {thin}"
    assert set(counts) == {
        "range",
        "max_height",
        "time_of_flight",
        "impact_speed",
        "launch_angle",
    }


# ---------------------------------------------------------------------------
# The launch height changes every one of these, and differently each time.
# ---------------------------------------------------------------------------


def test_a_launch_height_lengthens_the_flight() -> None:
    """The quadratic branch, not 2 v0 sin(theta) / g."""
    assert (
        _verified_answer(
            "a ball is thrown at 20 m/s at 30 degrees from a 10 m cliff, how long is it in the air"
        )
        == "2.77 s"
    )


def test_a_launch_height_raises_the_impact_speed() -> None:
    """Symmetry is what makes the flat case land at 20 m/s; a cliff breaks it."""
    assert (
        _verified_answer(
            "a ball is thrown at 20 m/s at 30 degrees from a 10 m cliff, how fast does it land"
        )
        == "24.4 m/s"
    )


def test_impact_speed_off_a_cliff_exceeds_the_launch_speed() -> None:
    flat = _verified_answer("what is the landing speed of a ball thrown at 20 m/s at 30 degrees")
    cliff = _verified_answer(
        "what is the landing speed of a ball thrown at 20 m/s at 30 degrees from a 10 m cliff"
    )
    assert flat is not None and cliff is not None
    assert float(cliff.split()[0]) > float(flat.split()[0])


# ---------------------------------------------------------------------------
# The three questions that were answered wrongly, pinned against their old
# answers by value rather than by op.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "what is the time of flight of a ball thrown at 20 m/s at 30 degrees",
        "how long is a ball in the air, thrown at 20 m/s at 30 degrees",
        "how fast is a ball going when it lands, thrown at 20 m/s at 30 degrees",
        "what is the speed at impact of a ball thrown at 20 m/s at 30 degrees",
    ],
)
def test_a_non_range_question_is_never_answered_with_the_range(text: str) -> None:
    """35.31 m is the range of this throw. It was the answer to all four."""
    answer = _verified_answer(text)
    assert answer is not None
    assert answer != "35.3 m"
    assert not answer.endswith(" m")


def test_kinematics_does_not_claim_a_question_with_a_launch_angle() -> None:
    """It has no angle, so it used the whole speed as the vertical component.

    `4.08 s` is 2 * 20 / 9.81 — the answer for a ball thrown straight up at
    20 m/s. The vertical component at 30 degrees is 10 m/s, so the true flight
    is half that.
    """
    text = "a ball is launched at 20 m/s at 30 degrees, how long until it hits the ground"
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.kind == "projectile"
    assert _verified_answer(text) == "2.04 s"


def test_a_ball_hitting_the_ground_is_not_a_collision() -> None:
    """P11's guard matched `hits`, which is also how a projectile lands.

    The guard has to stay — an angled two-body collision is still refused —
    so the exception is on the target, not on the verb.
    """
    assert (
        _verified_answer(
            "a ball is thrown at 20 m/s at 30 degrees, how fast does it hit the ground"
        )
        == "20 m/s"
    )
    assert (
        _verified_answer("a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically at 30 degrees")
        is None
    )


# ---------------------------------------------------------------------------
# Negative table. A projectile question whose ask we cannot name is refused.
# ---------------------------------------------------------------------------

UNDERSPECIFIED = [
    # No recognisable ask: before this change every one of these answered
    # with the range.
    "a ball is thrown at 20 m/s at 30 degrees",
    "a projectile is launched at 20 m/s at 30 degrees",
    "projectile: v0 = 20 m/s, angle = 30 deg",
    # The angle is the unknown, but no range is given to invert.
    "at what angle should a ball be thrown at 20 m/s",
    # A range beyond reach at this speed has no launch angle at all.
    "at what angle should a ball be thrown at 5 m/s to travel 500 m",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_underspecified_projectiles_are_refused_not_guessed(text: str) -> None:
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "what is the range of the function f(x) = x^2",
    "find the range of 3, 7, 9, 12",
    "Pick a number in the range 2-6",
    "at what angle should I hold the camera",
    "how long is a piece of string",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_the_new_cues_do_not_steal_other_subjects(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS
