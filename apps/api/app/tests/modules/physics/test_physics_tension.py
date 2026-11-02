"""P16: tension and Atwood machines.

The one topic round 1 **refused on purpose**. P2 found "the tension supporting a
5 kg mass accelerating at 2 m/s^2" answered `10 N` — m*a — when the answer is
T = m(g + a) = 59.05 N, and put `tension` and `pulley` into
`_UNSUPPORTED_FORCE_CONTEXT` rather than let a confidently wrong number ship.
The refusal was right; the gap is that it was never filled.

Both sides are kept. P5's correction said the refusal tuple guards the
fall-through and its entries are not deleted wholesale when a topic lands, so
this extractor runs *ahead* of force and claims only the two shapes it can
solve. A rope at an angle, a rope across a table, two ropes sharing a load —
each still reaches the refusal, because each would be answered confidently and
wrongly by T = m(g ± a).
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
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
    # T = m(g + a) — the rope pulls up harder than the weight alone.
    ("what is the tension in a rope lifting a 5 kg mass at 2 m/s^2", "tension", "59.1 N"),
    ("the tension supporting a 5 kg mass accelerating at 2 m/s^2", "tension", "59.1 N"),
    ("find the tension in a cable hoisting a 5 kg mass at 2 m/s^2", "tension", "59.1 N"),
    # a = 0: the rope holds the weight and nothing more.
    ("find the tension in a cable holding a 5 kg mass", "tension", "49.1 N"),
    ("what is the tension in a rope suspending a 5 kg mass", "tension", "49.1 N"),
    # T = m(g - a) — lowering, so the rope takes less than the full weight.
    ("what is the tension in a rope lowering a 5 kg mass at 2 m/s^2", "tension", "39.1 N"),
    # Atwood: one answer carrying both quantities, as the 1D collision does.
    (
        "an atwood machine with masses 3 kg and 5 kg, what is the acceleration",
        "atwood",
        "2.45 m/s² and 36.8 N",
    ),
    (
        "two masses 3 kg and 5 kg over a pulley, find the tension",
        "atwood",
        "2.45 m/s² and 36.8 N",
    ),
    (
        "a pulley has a 5 kg mass on one side and a 3 kg mass on the other, find the acceleration",
        "atwood",
        "2.45 m/s² and 36.8 N",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_tension_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)

    assert intent is not None, "no intent extracted"
    assert intent.kind == "force"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_both_ops_have_at_least_three_phrasings() -> None:
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert set(covered) == {"tension", "atwood"}
    assert {op: n for op, n in covered.items() if n < 3} == {}


# --- the physics ------------------------------------------------------------


def test_the_answer_p2_refused_is_the_answer_p16_gives() -> None:
    """59.05 N, and specifically not the 10 N that caused the refusal.

    Asserting the right number alone would catch a regression; asserting it is
    not *that* number records what the bug looked like, since 10 N is a
    perfectly plausible-looking answer to the same sentence.
    """
    answer = _verified_answer("the tension supporting a 5 kg mass accelerating at 2 m/s^2")

    assert answer is not None
    assert float(answer.split()[0]) == pytest.approx(5 * (9.81 + 2), rel=5e-3)
    assert float(answer.split()[0]) != pytest.approx(10.0)


def test_direction_changes_the_answer_in_the_right_direction() -> None:
    """Lifting > holding > lowering, and nothing in the digits says which.

    The three questions carry the same 5 kg and the same 2 m/s²; only the verb
    differs. A reading that ignored the verb would return one number for all
    three.
    """
    up = _verified_answer("what is the tension in a rope lifting a 5 kg mass at 2 m/s^2")
    still = _verified_answer("find the tension in a cable holding a 5 kg mass")
    down = _verified_answer("what is the tension in a rope lowering a 5 kg mass at 2 m/s^2")

    assert up is not None and still is not None and down is not None
    up_n, still_n, down_n = (float(x.split()[0]) for x in (up, still, down))

    assert down_n < still_n < up_n
    # Holding is exactly the weight, and the two moving cases straddle it evenly.
    assert still_n == pytest.approx(5 * 9.81, rel=5e-3)
    assert up_n - still_n == pytest.approx(still_n - down_n, abs=0.01)


def test_a_missing_g_on_the_moon_or_mars_is_that_body() -> None:
    """Tension and Atwood never stored g, so the solver used to keep Earth's."""
    moon = _verified_answer(
        "an atwood machine on the moon with masses 3 kg and 5 kg, what is the acceleration"
    )
    mars = _verified_answer("find the tension in a cable holding a 5 kg mass on mars")
    earth = _verified_answer("find the tension in a cable holding a 5 kg mass")

    assert moon is not None and mars is not None and earth is not None
    moon_accel = float(moon.split(" and ")[0].split()[0])
    mars_tension = float(mars.split()[0])
    earth_tension = float(earth.split()[0])
    assert moon_accel == pytest.approx((5 - 3) * 1.62 / (5 + 3), rel=5e-3)
    assert mars_tension == pytest.approx(5 * 3.71, rel=5e-3)
    assert earth_tension == pytest.approx(5 * 9.81, rel=5e-3)


def test_an_atwood_machine_on_jupiter_declines() -> None:
    assert (
        _verified_answer(
            "an atwood machine on jupiter with masses 3 kg and 5 kg, what is the acceleration"
        )
        is None
    )


def test_an_atwood_pair_returns_both_quantities() -> None:
    """The ticket's acceptance clause: acceleration *and* tension."""
    answer = _verified_answer(
        "an atwood machine with masses 3 kg and 5 kg, what is the acceleration"
    )

    assert answer is not None
    assert "m/s²" in answer and "N" in answer


def test_the_atwood_tension_sits_between_the_two_weights() -> None:
    """The property that catches a transposed formula immediately.

    The rope cannot pull harder than the heavy mass weighs (it would rise) nor
    less than the light one (it would fall), so 3g < T < 5g.
    """
    answer = _verified_answer("two masses 3 kg and 5 kg over a pulley, find the tension")

    assert answer is not None
    tension = float(answer.split(" and ")[1].split()[0])

    assert 3 * 9.81 < tension < 5 * 9.81


def test_equal_masses_do_not_move() -> None:
    """a = (m1 - m2)g/(m1 + m2) is zero when the pair balances, and then the
    tension is just one weight — the sanity check the formula has to pass."""
    answer = _verified_answer(
        "an atwood machine with masses 4 kg and 4 kg, what is the acceleration"
    )

    assert answer is not None
    accel, tension = answer.split(" and ")

    assert float(accel.split()[0]) == pytest.approx(0.0, abs=0.01)
    assert float(tension.split()[0]) == pytest.approx(4 * 9.81, rel=5e-3)


def test_written_order_of_the_masses_does_not_change_the_answer() -> None:
    """Which mass is named first is a fact about the sentence, not the pulley.

    The heavier one descends whichever way round it is written, so the two
    orderings have to agree — the pairing hazard P9 found in the balance case,
    headed off here.
    """
    heavy_first = _verified_answer("two masses 5 kg and 3 kg over a pulley, find the tension")
    light_first = _verified_answer("two masses 3 kg and 5 kg over a pulley, find the tension")

    assert heavy_first is not None
    assert heavy_first == light_first


# --- what is still refused, and why -----------------------------------------


STILL_REFUSED = [
    # A rope at an angle is a vector problem, not T = m(g ± a).
    "a 5 kg mass hangs from two ropes at 30 degrees, what is the tension in each",
    "find the tension in a rope holding a 5 kg mass at 40 degrees",
    # Horizontal: the weight does not enter the equation at all.
    "what is the tension in a rope pulling a 5 kg box across the floor at 2 m/s^2",
    "the tension in a string dragging a 5 kg block along a horizontal table",
    # Two ropes share the load; one formula cannot say how.
    "a 5 kg mass hangs from two cables, what is the tension in each cable",
    # A rope over a pulley to something unstated is an incomplete Atwood.
    "a 5 kg mass on a pulley, what is the tension",
    # Friction changes the free body, and the coefficient is not read here.
    "the tension in a rope lifting a 5 kg mass with a friction coefficient of 0.2",
]


@pytest.mark.parametrize("text", STILL_REFUSED, ids=[t[:46] for t in STILL_REFUSED])
def test_rope_shapes_outside_the_two_solved_are_still_refused(text: str) -> None:
    """The ticket's third acceptance clause.

    P2's refusal tuple is not deleted because this extractor landed — it is
    what these fall through to. Each of them would get a confident wrong number
    from T = m(g ± a), which is the failure P2 was protecting against.
    """
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "the tension in the room was high",
    "there is tension between the two teams",
    "I have a tension headache for 3 days",
    "find the tension in a 10 kg rope",
    "solve 2x + 7 = 19",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_tension_needs_a_mass_and_a_vertical_rope_beside_it(text: str) -> None:
    """ "tension" is ordinary English, and this cue feeds the global pre-filter.

    So it counts only with a mass *and* a word putting the rope vertical. The
    last row is the one that forced the third condition: a 10 kg rope is the
    rope's own mass, not a hanging load, and an existing pre-filter test
    already said we must not spend a tool round on it.
    """
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_plain_newtons_second_law_still_reaches_the_force_extractor() -> None:
    """Tension runs before force, so it must not swallow ordinary F = ma."""
    intent = extract_physics_intent("a 5 kg mass accelerates at 2 m/s^2, what is the net force")

    assert isinstance(intent, PhysicsIntent) and intent.physics_op == "net_force"
    assert _verified_answer("a 5 kg mass accelerates at 2 m/s^2, what is the net force") == "10 N"


def test_a_rope_in_free_fall_is_refused_rather_than_reported_slack() -> None:
    """At a = -g the rope goes slack and T = 0; beyond it the formula turns
    negative, which is not a rope pushing but a question that has left the
    model behind."""
    assert (
        _verified_answer("what is the tension in a rope lowering a 5 kg mass at 12 m/s^2") is None
    )
