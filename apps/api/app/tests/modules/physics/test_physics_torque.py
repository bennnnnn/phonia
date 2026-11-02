"""P9: torque and rotational equilibrium.

`"moment"` is ordinary English — *"give me a moment"*, *"at the moment"* — so it
is never a cue on its own; it qualifies only beside a pivot word.

The balance case needed more than cue care. Reading the two forces and the one
distance in *written order* looks right and is not: in "the distance for a 10 N
force to balance a 5 N force at 2 m", the 10 N is mentioned first but the 2 m is
the **5 N force's** arm. Written order answers 4 m; the true answer is 1 m. The
distance is paired with the force that precedes it instead, and the force left
without an arm is the unknown.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

PHYSICS_KINDS = {
    "kinematics",
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
    ("torque of a 5 N force at 2 m from the pivot", "torque", "10 N·m"),
    ("what is the torque when a 5 N force acts 2 m from the fulcrum", "torque", "10 N·m"),
    ("find the moment of a 5 N force 2 m from the pivot", "torque", "10 N·m"),
    # F d sin(theta): 5 * 2 * sin(30) = 5
    ("torque of a 5 N force applied 2 m from the pivot at 30 degrees", "torque", "5 N·m"),
    (
        "a 5 N force is 2 m from the pivot, how far must a 10 N force be to balance it",
        "moment_balance",
        "1 m",
    ),
    (
        "two forces balance on a see-saw: 5 N at 2 m and 10 N at what distance",
        "moment_balance",
        "1 m",
    ),
    (
        "find the distance for a 10 N force to balance a 5 N force at 2 m from the fulcrum",
        "moment_balance",
        "1 m",
    ),
    (
        "A 50 N downward force acts 2 m to the left of a pivot. "
        "What downward force 4 m to the right balances the lever?",
        "moment_balance",
        "25 N",
    ),
    (
        "What force at 4 m balances a 50 N load acting 2 m from the pivot?",
        "moment_balance",
        "25 N",
    ),
    (
        "Balance a lever with 50 N at 2 m using an unknown force at 4 m.",
        "moment_balance",
        "25 N",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_torque_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, "no intent extracted"
    assert intent.kind == "torque"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_torque_op_has_at_least_three_phrasings() -> None:
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert {op: n for op, n in covered.items() if n < 3} == {}
    assert set(covered) == {"torque", "moment_balance"}


# --- the pairing bug this ticket had to solve -------------------------------


def test_the_distance_binds_to_the_force_that_owns_it() -> None:
    """Written order is not ownership, and getting it wrong is silent.

    All three phrasings describe the same see-saw — 5 N at 2 m balanced by 10 N
    — so all three must give the same arm. An earlier draft read the numbers in
    written order and answered 4 m for the third, because it paired the 2 m with
    the 10 N force that happened to be mentioned first.
    """
    answers = {
        _verified_answer(
            "a 5 N force is 2 m from the pivot, how far must a 10 N force be to balance it"
        ),
        _verified_answer("two forces balance on a see-saw: 5 N at 2 m and 10 N at what distance"),
        _verified_answer(
            "find the distance for a 10 N force to balance a 5 N force at 2 m from the fulcrum"
        ),
    }

    assert answers == {"1 m"}


def test_the_balance_actually_balances() -> None:
    """F1 d1 = F2 d2 — check the moments match, not just the arithmetic."""
    arm = _verified_answer(
        "a 5 N force is 2 m from the pivot, how far must a 10 N force be to balance it"
    )

    assert arm is not None
    assert 5.0 * 2.0 == pytest.approx(10.0 * float(arm.split()[0]))


def test_a_requested_balancing_force_uses_both_stated_arms() -> None:
    force = _verified_answer(
        "A 50 N downward force acts 2 m to the left of a pivot. "
        "What downward force 4 m to the right balances the lever?"
    )

    assert force is not None
    assert float(force.split()[0]) * 4.0 == pytest.approx(50.0 * 2.0)


def test_an_angled_force_gives_less_torque() -> None:
    """tau = F d sin(theta) — a force off the perpendicular does less turning."""
    square_on = _verified_answer("torque of a 5 N force at 2 m from the pivot")
    angled = _verified_answer("torque of a 5 N force applied 2 m from the pivot at 30 degrees")

    assert square_on is not None and angled is not None
    assert float(angled.split()[0]) < float(square_on.split()[0])


# --- refusals and the vocabulary hazard -------------------------------------


NOT_PHYSICS = [
    "solve 2x + 7 = 19",
    "give me a moment to think about 3 options",
    "at the moment I have 3 tasks",
    "in a moment of 5 seconds everything changed",
    "find the factors of 24",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_moment_alone_is_not_a_torque_cue(text: str) -> None:
    """It is ordinary English, so it counts only beside a pivot word."""
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_moment_of_inertia_is_not_confused_with_torque() -> None:
    """A different quantity entirely (kg·m^2), sharing the word "moment".

    P9 named it in `_TORQUE_UNSUPPORTED` rather than leaving it to chance, and
    that refusal is kept: it is what stops *torque* claiming it. Round 3 added
    a `rotation` kind that runs afterwards and answers it properly, so the
    assertion is no longer "nobody answers this" - it is "torque does not, and
    whoever does calls it by the right name".
    """
    from app.modules.physics.extractors.torque import _extract_torque_intent

    text = "what is the moment of inertia of a 5 kg disc of radius 2 m"
    assert _extract_torque_intent(text) is None

    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.kind == "rotation"
    assert intent.physics_op == "moment_of_inertia"
    assert _verified_answer(text) == "10 kg·m²"


def test_a_shapeless_moment_of_inertia_is_still_refused() -> None:
    """I = k m r^2, and k is the shape. A wheel is not a shape.

    This is the half of P9's caution that survives verbatim: answering an
    unnamed body with the disc constant would be a confidently wrong number.
    """
    assert _verified_answer("what is the moment of inertia of a 5 kg wheel of radius 2 m") is None


def test_plain_newtons_second_law_still_reaches_the_force_extractor() -> None:
    """Torque runs before force, so it must not swallow ordinary F = ma."""
    intent = extract_physics_intent("a 5 kg mass accelerates at 2 m/s^2, what is the net force")

    assert intent is not None and intent.kind == "force"
    assert _verified_answer("a 5 kg mass accelerates at 2 m/s^2, what is the net force") == "10 N"


UNDERSPECIFIED = [
    "what is the torque on the lever",
    "torque of a 5 N force",
    "how far from the pivot should the weight go to balance",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_torque_questions_missing_a_given_are_refused(text: str) -> None:
    assert _verified_answer(text) is None
