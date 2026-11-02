"""Round 3: the quantities the existing kinds could not answer.

Nothing here was a wrong answer — all fourteen phrasings returned nothing at
all — so this file is about reach rather than correctness. Each one is a
one-line formula the kind already had every given for:

    circular   omega = v / r            had v and r, computed neither
    spring     f = 1/T, v_max = A omega had neither a k nor an L to hang on
    friction   mu = tan(theta), F = mu m g

Two of them needed a cue as well as an op, which is the part that is easy to
miss: "the angular velocity of a car going 10 m/s around a 20 m radius track"
fired no circular cue at all, so a new op alone would have changed nothing.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    needs_physics,
)

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


# (question, kind, expected physics_op, expected answer)
VERIFIED: list[tuple[str, str, str, str]] = [
    # --- circular: omega = v / r -------------------------------------
    (
        "what is the angular velocity of a car going 10 m/s around a 20 m radius track",
        "circular",
        "angular_velocity",
        "0.5 rad/s",
    ),
    (
        "what is the angular speed of an object moving at 8 m/s in a circle of radius 4 m",
        "circular",
        "angular_velocity",
        "2 rad/s",
    ),
    (
        "find the angular velocity for a speed of 6 m/s on a circular path of radius 3 m",
        "circular",
        "angular_velocity",
        "2 rad/s",
    ),
    # --- SHM: f = 1 / T ----------------------------------------------
    ("what is the frequency of a pendulum with period 2 s", "spring", "shm_frequency", "0.5 Hz"),
    (
        "what is the frequency of an oscillator with a period of 0.5 s",
        "spring",
        "shm_frequency",
        "2 Hz",
    ),
    (
        "a mass on a spring has a period of 4 s, what is the frequency",
        "spring",
        "shm_frequency",
        "0.25 Hz",
    ),
    # --- SHM: v_max = A omega ----------------------------------------
    (
        "what is the maximum speed of an oscillator with amplitude 0.5 m at 2 rad/s",
        "spring",
        "shm_max_speed",
        "1 m/s",
    ),
    (
        "find the maximum speed of a mass oscillating with amplitude 0.2 m "
        "and angular frequency 5 rad/s",
        "spring",
        "shm_max_speed",
        "1 m/s",
    ),
    (
        "peak velocity of a body oscillating with amplitude 0.1 m at 10 rad/s",
        "spring",
        "shm_max_speed",
        "1 m/s",
    ),
    # --- friction: mu = tan(theta) at the slipping angle -------------
    (
        "what is the coefficient of friction if a block slides at 30 degrees",
        "friction",
        "friction_coefficient",
        "0.577",
    ),
    (
        "a block starts to slide on a 25 degree incline, what is the coefficient of friction",
        "friction",
        "friction_coefficient",
        "0.466",
    ),
    (
        "find the coefficient of static friction if slipping begins at 20 degrees",
        "friction",
        "friction_coefficient",
        "0.364",
    ),
    # --- friction: F_min = mu m g ------------------------------------
    (
        "what is the minimum force to move a 5 kg block with friction coefficient 0.4",
        "friction",
        "minimum_force",
        "19.6 N",
    ),
    (
        "what force is needed to start a 10 kg crate moving if the coefficient of friction is 0.3",
        "friction",
        "minimum_force",
        "29.4 N",
    ),
    (
        "minimum force to push a 4 kg box with a coefficient of friction of 0.5",
        "friction",
        "minimum_force",
        "19.6 N",
    ),
]


@pytest.mark.parametrize("text,kind,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_round_three_gap_phrasings(text: str, kind: str, op: str, answer: str) -> None:
    assert needs_physics(text), "dropped by the pre-filter before extraction"
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent), "no intent extracted"
    assert intent.kind == kind
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_round_three_gap_op_has_at_least_three_phrasings() -> None:
    from collections import Counter

    counts = Counter(op for _, _, op, _ in VERIFIED)
    thin = {op: n for op, n in counts.items() if n < 3}
    assert not thin, f"ops with fewer than three phrasings: {thin}"
    assert set(counts) == {
        "angular_velocity",
        "shm_frequency",
        "shm_max_speed",
        "friction_coefficient",
        "minimum_force",
    }


# ---------------------------------------------------------------------------
# Physical relationships, so a phrasing cannot pass by binding the right number
# to the wrong variable.
# ---------------------------------------------------------------------------


def test_angular_velocity_falls_as_the_radius_grows() -> None:
    """Same speed, bigger circle, slower sweep."""
    tight = _verified_answer(
        "what is the angular velocity of a car going 10 m/s around a 10 m radius track"
    )
    wide = _verified_answer(
        "what is the angular velocity of a car going 10 m/s around a 20 m radius track"
    )
    assert tight is not None and wide is not None
    assert float(tight.split()[0]) > float(wide.split()[0])


def test_frequency_is_the_reciprocal_of_the_period() -> None:
    half = _verified_answer("what is the frequency of an oscillator with a period of 0.5 s")
    double = _verified_answer("what is the frequency of an oscillator with a period of 2 s")
    assert half is not None and double is not None
    assert float(half.split()[0]) * float(double.split()[0]) == pytest.approx(1.0, abs=0.01)


def test_a_steeper_slipping_angle_means_more_friction() -> None:
    shallow = _verified_answer(
        "find the coefficient of static friction if slipping begins at 20 degrees"
    )
    steep = _verified_answer(
        "find the coefficient of static friction if slipping begins at 40 degrees"
    )
    assert shallow is not None and steep is not None
    assert float(steep) > float(shallow)


def test_the_minimum_force_is_mass_proportional() -> None:
    light = _verified_answer(
        "what is the minimum force to move a 5 kg block with friction coefficient 0.4"
    )
    heavy = _verified_answer(
        "what is the minimum force to move a 10 kg block with friction coefficient 0.4"
    )
    assert light is not None and heavy is not None
    assert float(heavy.split()[0]) == pytest.approx(2 * float(light.split()[0]), abs=0.01)


# ---------------------------------------------------------------------------
# Refusals. Each of these is a formula that looks like one of the above and
# is not, so guessing would produce a confidently wrong number.
# ---------------------------------------------------------------------------

UNDERSPECIFIED = [
    # mu = tan(theta) holds only where motion *begins*. On any other incline
    # the angle says nothing at all about the coefficient.
    "what is the coefficient of friction on a 30 degree incline",
    "what is the coefficient of friction for a block on a 15 degree ramp",
    # Both given and asked.
    "what is the coefficient of friction if a block slides at 30 degrees with a coefficient of 0.5",
    # On a slope F_min is mu*m*g*cos(t) + m*g*sin(t), which is not solved here.
    "what is the minimum force to move a 5 kg block up a 20 degree slope "
    "with friction coefficient 0.4",
    # No mass to scale the friction by.
    "what is the minimum force to move a block with friction coefficient 0.4",
    # An amplitude with no angular frequency to multiply it by.
    "what is the maximum speed of an oscillator with amplitude 0.5 m",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_underspecified_round_three_questions_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    # "angular" is a framework, and it ships version numbers.
    "angular 17 released 3 new features",
    "we rotate 4 people on support each week",
    # A period and a frequency in ordinary English.
    "my sleep frequency dropped to 5 hours",
    "there was a quiet period of 3 weeks",
    "the frequency of these 2 outages is worrying",
    # Trigonometry still owns the period of a function.
    "what is the period of sin(2x)",
    # Algebra still owns coefficients.
    "what is the coefficient of x^2 in 3x^2 + 2x",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_the_round_three_cues_do_not_steal_other_subjects(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS
