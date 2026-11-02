"""P13: motion under constant acceleration.

The largest coverage gap round 1 left, and the most common school physics topic
there is. `kinematics` solves free fall *under gravity*, so a car pulling away
from a stop was not physics to us at all — all six probed phrasings returned
nothing.

Two things shaped the implementation. The op names the **unknown** and the
solver picks whichever of the four equations the givens support, so one set of
phrasing rules covers all four rather than four sets — the approach P8 used for
Ohm's law. And the extractor runs *after* kinematics rather than before: free
fall is a constant acceleration too, and kinematics already owns it, so
inheriting only what gravity did not claim perturbs nothing that already
answered.
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


def _graph(text: str):
    """The one graph a SUVAT solve emits, or an assertion failure saying why."""
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent), f"no intent extracted for {text!r}"
    specs = solve_physics(intent).graph_specs
    assert len(specs) == 1, f"expected one graph for {text!r}, got {len(specs)}"
    return specs[0]


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


# (question, expected physics_op, expected answer). Every answer is pinned, so
# a phrasing cannot pass by binding the right number to the wrong variable —
# the failure mode P9 found the hard way.
VERIFIED: list[tuple[str, str, str]] = [
    # v = u + at
    (
        "a car accelerates from rest at 3 m/s^2 for 5 s, what is its final velocity",
        "suvat_velocity",
        "15 m/s",
    ),
    (
        "a train starting from rest accelerates at 2 m/s^2, how fast after 10 s",
        "suvat_velocity",
        "20 m/s",
    ),
    (
        "a cyclist at 4 m/s accelerates at 2 m/s^2 for 3 s, what is the final speed",
        "suvat_velocity",
        "10 m/s",
    ),
    # s = ut + ½at²
    (
        "how far does a car go in 5 s accelerating from rest at 3 m/s^2",
        "suvat_distance",
        "37.5 m",
    ),
    # v² = u² + 2as
    (
        "a car travelling at 20 m/s decelerates at 4 m/s^2, how far before it stops",
        "suvat_distance",
        "50 m",
    ),
    (
        "what distance does a car cover accelerating from 10 m/s to 30 m/s at 2 m/s^2",
        "suvat_distance",
        "200 m",
    ),
    # s = ½(u + v)t — the equation with no acceleration in it at all
    (
        "a cyclist decelerates from 12 m/s to rest in 4 s, how far do they travel",
        "suvat_distance",
        "24 m",
    ),
    # s = vt - (1/2)at^2: final speed, acceleration, and time, no initial speed
    (
        "a car reaches 20 m/s after accelerating at 2 m/s^2 for 4 s, how far does it travel",
        "suvat_distance",
        "64 m",
    ),
    # solving for t
    (
        "a car accelerates from rest at 3 m/s^2, how long to reach 15 m/s",
        "suvat_time",
        "5 s",
    ),
    # solving for a
    (
        "a car goes from rest to 30 m/s in 10 s, what is the acceleration",
        "suvat_acceleration",
        "3 m/s²",
    ),
    (
        "a train slows down from 20 m/s to rest over 100 m, what is the deceleration",
        "suvat_acceleration",
        "-2 m/s²",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_suvat_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, "no intent extracted"
    assert intent.kind == "suvat"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_all_four_equations_are_exercised() -> None:
    """The ticket's acceptance clause, enforced rather than counted by hand.

    Four unknowns times the equations that reach them; the table above must keep
    covering every op rather than piling onto the easy one.
    """
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert set(covered) == {
        "suvat_velocity",
        "suvat_distance",
        "suvat_time",
        "suvat_acceleration",
    }
    assert covered["suvat_velocity"] >= 3
    assert covered["suvat_distance"] >= 3


# --- the physics is right, not just the plumbing ----------------------------


def test_the_four_equations_agree_on_one_journey() -> None:
    """u = 0, a = 3, t = 5 → v = 15, s = 37.5.

    Each equation reaches a different variable of the same motion, so they have
    to be mutually consistent. Pinning the numbers proves transcription; this
    proves they describe one journey.
    """
    v = _verified_answer(
        "a car accelerates from rest at 3 m/s^2 for 5 s, what is its final velocity"
    )
    s = _verified_answer("how far does a car go in 5 s accelerating from rest at 3 m/s^2")
    t = _verified_answer("a car accelerates from rest at 3 m/s^2, how long to reach 15 m/s")

    assert v is not None and s is not None and t is not None
    v_val, s_val, t_val = (float(x.split()[0]) for x in (v, s, t))

    assert v_val == pytest.approx(3.0 * t_val)  # v = u + at
    assert s_val == pytest.approx(0.5 * (0.0 + v_val) * t_val)  # s = ½(u+v)t
    assert v_val**2 == pytest.approx(2 * 3.0 * s_val)  # v² = u² + 2as


def test_deceleration_is_read_as_a_negative_acceleration() -> None:
    """The sign lives in the word, not the number.

    "decelerates at 4 m/s^2" states a magnitude; nothing in the digits says the
    car is slowing. Read as +4 the car would speed up and never stop, and the
    stopping distance would come out imaginary or negative.
    """
    stopping = _verified_answer(
        "a car travelling at 20 m/s decelerates at 4 m/s^2, how far before it stops"
    )

    assert stopping is not None
    assert float(stopping.split()[0]) == pytest.approx(50.0)


def test_a_stated_deceleration_is_reported_as_negative() -> None:
    """Solving *for* the acceleration keeps the sign rather than hiding it."""
    answer = _verified_answer(
        "a train slows down from 20 m/s to rest over 100 m, what is the deceleration"
    )

    assert answer is not None
    assert float(answer.split()[0]) < 0


def test_suvat_emits_a_velocity_time_graph() -> None:
    """A straight line whose slope *is* the acceleration.

    `velocity_vs_time` already exists — P3 added it and P7 uses it — so this
    needed no new fence, and P3's player animates it for free.
    """
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent(
        "a car accelerates from rest at 3 m/s^2 for 5 s, what is its final velocity"
    )
    assert isinstance(intent, PhysicsIntent)
    result = solve_physics(intent)

    assert len(result.graph_specs) == 1
    spec = result.graph_specs[0]
    assert spec.trajectory_type == "velocity_vs_time"
    assert spec.points[0] == [0.0, 0.0]
    assert spec.points[-1][1] == pytest.approx(15.0)


def test_the_graph_plots_the_quantity_that_was_asked_for() -> None:
    """Found in the app: "how far does a car go in 5 s" was answered 37.50 m
    under a chart climbing to 15 m/s.

    Every op drew the same velocity-against-time line, on the reasoning that
    its slope *is* the acceleration. True, and still wrong — the 37.50 is the
    *area* under that line, a real relationship and not the one on screen, with
    nothing saying so. Two different questions about the same journey also drew
    byte-identical charts, which reads as a duplication bug rather than a wrong
    axis.

    The test that matters: the curve's last point is the answer.
    """
    distance = _graph("how far does a car go in 5 s accelerating from rest at 3 m/s^2")
    velocity = _graph("a car accelerates from rest at 3 m/s^2 for 5 s, what is its final velocity")

    assert distance.title == "Distance vs. Time"
    assert distance.trajectory_type == "position_vs_time"
    assert distance.points[-1][1] == pytest.approx(37.5)

    assert velocity.title == "Velocity vs. Time"
    assert velocity.trajectory_type == "velocity_vs_time"
    assert velocity.points[-1][1] == pytest.approx(15.0)

    # Same journey, different questions — the charts must not be identical.
    assert distance.points != velocity.points


def test_the_distance_curve_bends_the_way_the_equation_bends() -> None:
    """s = ut + ½at² is a parabola, and drawing it as the straight velocity
    line was exactly the substitution this fixes."""
    points = _graph("how far does a car go in 5 s accelerating from rest at 3 m/s^2").points

    first_step = points[1][1] - points[0][1]
    last_step = points[-1][1] - points[-2][1]

    assert last_step > first_step * 5


def test_solving_for_a_time_plots_whichever_target_the_givens_carry() -> None:
    """A stated final velocity makes it a velocity question; a stated distance
    makes it a distance one."""
    to_speed = _graph("a car accelerates from rest at 3 m/s^2, how long to reach 15 m/s")

    assert to_speed.title == "Velocity vs. Time"
    assert to_speed.points[-1][1] == pytest.approx(15.0)


def test_a_graph_needs_a_time_span_to_be_honest() -> None:
    """No time anywhere in the givens means nothing to plot against.

    Drawing a curve over an invented span would be the same class of error as
    inventing geometry dimensions.
    """
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent(
        "what distance does a car cover accelerating from 10 m/s to 30 m/s at 2 m/s^2"
    )
    assert isinstance(intent, PhysicsIntent)

    assert solve_physics(intent).graph_specs == []


# --- the cue hazard the ticket named ----------------------------------------


NEWTONS_SECOND_LAW = [
    ("a 5 kg mass accelerates at 2 m/s^2, what is the net force", "10 N"),
    ("what is the force on a 10 kg object accelerating at 3 m/s^2", "30 N"),
    ("what force accelerates a 2 kg mass at 4 m/s^2", "8 N"),
]


@pytest.mark.parametrize(
    "text,answer", NEWTONS_SECOND_LAW, ids=[t[:44] for t, _ in NEWTONS_SECOND_LAW]
)
def test_plain_f_equals_ma_is_left_alone(text: str, answer: str) -> None:
    """`accelerates at` was already a force cue (P2), so these overlap by design.

    What separates them is not the verb: it is that F = ma names a mass and no
    time or distance, so SUVAT never has three of its five variables and cannot
    claim the question even though it recognises the wording.
    """
    intent = extract_physics_intent(text)

    assert intent is not None and intent.kind == "force"
    assert _verified_answer(text) == answer


def test_free_fall_still_belongs_to_kinematics() -> None:
    """Gravity is a constant acceleration, so the two genuinely overlap.

    Order settles it: kinematics runs first and keeps everything it already
    answered.
    """
    intent = extract_physics_intent(
        "a ball is dropped from 20 m, how long until it hits the ground"
    )

    assert intent is not None and intent.kind == "kinematics"
    assert (
        _verified_answer("a ball is dropped from 20 m, how long until it hits the ground")
        == "2.02 s"
    )


# --- a live wrong answer this ticket had to fix before it could land --------
#
# "how long to reach" was already a kinematics cue, so kinematics claimed
# "a car accelerates from rest at 3 m/s^2, how long to reach 15 m/s" and
# answered **3.06 s**. That is 15/9.81 — the time a ball thrown up at 15 m/s
# takes to stop. The stated 3 m/s² was discarded and Earth's gravity put in its
# place. Confirmed against the merged code before any of P13 was written, so it
# is a bug of its own, not one this ticket introduced.
#
# Ordering alone could not fix it: running SUVAT first would have had it
# competing with free fall for every falling-body question. Kinematics has to
# decline instead, and the rule is the definition of free fall — gravity *is*
# the acceleration, so a question that supplies its own is not one.


STOLEN_BY_FREE_FALL = [
    ("a car accelerates from rest at 3 m/s^2, how long to reach 15 m/s", "5 s"),
    ("a car accelerates from rest at 2 m/s^2, how long to reach 20 m/s", "10 s"),
]


@pytest.mark.parametrize(
    "text,answer", STOLEN_BY_FREE_FALL, ids=[t[:44] for t, _ in STOLEN_BY_FREE_FALL]
)
def test_a_stated_acceleration_is_not_replaced_by_gravity(text: str, answer: str) -> None:
    intent = extract_physics_intent(text)

    assert intent is not None and intent.kind == "suvat"
    assert _verified_answer(text) == answer


def test_the_old_answer_was_gravity_wearing_the_question_s_clothes() -> None:
    """Names the wrong number so a regression cannot pass quietly.

    A future change that re-routes this to kinematics would produce 3.06 s
    again — an answer that looks entirely plausible next to a question about a
    car. Asserting the right value alone would catch it; asserting it is not
    *that* value says why.
    """
    answer = _verified_answer("a car accelerates from rest at 3 m/s^2, how long to reach 15 m/s")

    assert answer is not None
    assert float(answer.split()[0]) == pytest.approx(5.0)
    assert float(answer.split()[0]) != pytest.approx(15 / 9.81, abs=0.01)


NAMED_GRAVITY = [
    ("a ball is dropped on the moon from 20 m, how long until it hits the ground", "4.97 s"),
    ("a ball is dropped from 20 m with g = 1.6 m/s^2, how long until it hits the ground", "5 s"),
    (
        "a ball is dropped from 20 m with gravity of 9.81 m/s^2, how long to hit the ground",
        "2.02 s",
    ),
]


@pytest.mark.parametrize("text,answer", NAMED_GRAVITY, ids=[t[:44] for t, _ in NAMED_GRAVITY])
def test_a_named_gravity_is_still_free_fall(text: str, answer: str) -> None:
    """The guard asks whether the stated acceleration *is* the gravity in play.

    "g = 1.6 m/s^2" states an acceleration in exactly the shape the guard looks
    for, and it is free fall — on the Moon. A guard that merely spotted a m/s²
    reading would have taken these away, which is why it compares against the
    gravity `_detect_gravity` already resolves rather than against 9.81.
    """
    intent = extract_physics_intent(text)

    assert intent is not None and intent.kind == "kinematics"
    assert _verified_answer(text) == answer


NOT_PHYSICS = [
    "solve 2x + 7 = 19",
    "find the factors of 24",
    "the project accelerated from 3 to 5 people",
    "I need a rest from 3 hours of meetings",
    "how far is 5 km in miles",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_suvat_cues_do_not_steal_other_subjects(text: str) -> None:
    """Every SUVAT cue is a signature, never a bare word.

    These cues feed the global `needs_math_tools` pre-filter, not just this
    extractor, so a loose one costs a model call on every sentence containing
    "accelerates" or "at rest" — P2's lesson, applied before it could bite.
    """
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


UNDERSPECIFIED = [
    "a car accelerates at 3 m/s^2, what is its final velocity",
    "a car starts from rest, how far does it go",
    "how fast is the train going after accelerating at 2 m/s^2",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_two_givens_are_not_enough(text: str) -> None:
    """Every SUVAT equation relates exactly four variables.

    With the unknown removed, three must remain. Two is a question that cannot
    be answered, and answering it anyway would mean inventing the third.
    """
    assert _verified_answer(text) is None


def test_a_reversal_reports_the_whole_path() -> None:
    """Reaching 15 m/s after 2 m/s^2 for 10 s implies u = -5 m/s.

    s = vt - (1/2)at^2 is then 50 m of displacement. The path is 62.5 m, and
    "how far" must not certify the smaller number.
    """
    text = "a car reaches 15 m/s after accelerating at 2 m/s^2 for 10 s, how far does it travel"
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == "suvat_distance"
    assert _verified_answer(text) == "62.5 m"


@pytest.mark.parametrize(
    "ask,expected,title",
    [
        ("find the distance travelled, not the displacement", "34 m", "Distance vs. Time"),
        ("find the displacement, not the distance travelled", "16 m", "Displacement vs. Time"),
        ("how far does it travel, rather than its displacement", "34 m", "Distance vs. Time"),
    ],
)
def test_distance_and_displacement_follow_the_requested_quantity(ask, expected, title) -> None:
    text = "A particle initially moves at 10 m/s with acceleration -2 m/s^2 for 8 s; " + ask
    assert _verified_answer(text) == expected
    graph = _graph(text)
    assert graph.title == title
    assert graph.points[-1][1] == pytest.approx(float(expected.split()[0]))


@pytest.mark.parametrize(
    "text,op,expected",
    [
        (
            "A particle moves with constant acceleration from rest. "
            "Its displacement after 5 s is 100 m. Find the acceleration",
            "suvat_acceleration",
            "8 m/s²",
        ),
        (
            "A particle moves from rest with constant acceleration of 8 m/s^2. "
            "Its displacement is 100 m. Find the time",
            "suvat_time",
            "5 s",
        ),
        (
            "A particle moves from rest with constant acceleration. "
            "Its final velocity after 5 s is 20 m/s. Find the acceleration",
            "suvat_acceleration",
            "4 m/s²",
        ),
    ],
)
def test_suvat_givens_do_not_shadow_the_unknown(text, op, expected) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == op
    assert _verified_answer(text) == expected


def test_an_unanswerable_question_shape_is_refused() -> None:
    """A question with givens but no recognisable ask stays out.

    "a car accelerates from rest at 3 m/s^2 for 5 s" is a description, not a
    question; without knowing which variable is wanted there is nothing to
    solve for.
    """
    assert _verified_answer("a car accelerates from rest at 3 m/s^2 for 5 s") is None
