"""A short line after a physics problem replays that problem, or declines."""

import pytest

from app.modules.physics.extract import extract_physics_intent
from app.modules.physics.followup import PHYSICS_FOLLOWUP_HINT, physics_followup_problem
from app.tests.modules.physics.test_physics_binding import _answer


def test_followup_hint_never_compares_with_the_earlier_answer() -> None:
    # "And after 10 s?" opened with "The previous result of 30 m/s corresponds to
    # a time of 10 s, not 5 s".
    assert "never compare it with or comment on the earlier answer" in PHYSICS_FOLLOWUP_HINT
    assert "changed given under Given" in PHYSICS_FOLLOWUP_HINT


_DROP = "A ball is dropped from 80 m. Find its speed just before it hits the ground."
_FORCE = "A block of mass 5 kg accelerates at 2 m/s^2. Find the force."
_LAUNCH = "A projectile is launched at 20 m/s at 30 degrees. Find the maximum height."


def _recent(problem: str) -> list[tuple[str, str]]:
    return [("user", problem), ("assistant", "Here is the working.")]


def test_an_explanation_replays_the_previous_problem() -> None:
    for line in (
        "why",
        "how",
        "why is it 40 m/s",
        "I didn't get it",
        "help me understand it",
        "that's confusing",
    ):
        assert physics_followup_problem(line, _recent(_DROP)) == _DROP


def test_another_quantity_keeps_the_givens_and_changes_the_ask() -> None:
    rewritten = physics_followup_problem("what about the range", _recent(_LAUNCH))
    assert rewritten is not None
    intent = extract_physics_intent(rewritten)
    assert intent is not None and intent.physics_op == "range"
    assert "20 m/s" in rewritten


def test_one_changed_given_is_replaced_and_resolved() -> None:
    rewritten = physics_followup_problem("but if it was 2 kg", _recent(_FORCE))
    assert rewritten is not None
    assert "5 kg" not in rewritten
    assert "2 kg" in rewritten
    assert _answer(rewritten) == "4 N"


def test_a_named_replacement_uses_that_quantity() -> None:
    rewritten = physics_followup_problem("if the mass is 2 kg", _recent(_FORCE))
    assert rewritten is not None and _answer(rewritten) == "4 N"


def test_two_possible_replacements_decline() -> None:
    prior = "Masses of 3 kg and 6 kg collide. Find the reduced mass."
    assert physics_followup_problem("if the mass is 2 kg", _recent(prior)) is None


def test_a_new_problem_is_not_a_followup() -> None:
    fresh = "A 2 kg block is dropped from 10 m. Find the speed."
    assert physics_followup_problem(fresh, _recent(_DROP)) is None
    assert physics_followup_problem("what about the kinetic energy", _recent(_FORCE)) is None
    assert (
        physics_followup_problem("if the mass is 2 kg and the height is 10 m", _recent(_FORCE))
        is None
    )


def test_a_followup_after_a_non_physics_turn_declines() -> None:
    recent = [("user", "Solve 2x + 3 = 11"), ("assistant", "x = 4")]
    assert physics_followup_problem("why is it 4", recent) is None


_CAR = "A car accelerates from rest at 3 m/s^2 for 5 s. What is its final velocity?"
_BALL = "A 2 kg ball is dropped from 20 m. How fast is it moving when it hits the ground?"


@pytest.mark.parametrize(
    ("prior", "line", "answer"),
    [
        # Another quantity of the same setup, asked as a question.
        (_CAR, "how far does it go?", "37.5 m"),
        (_BALL, "how long does it take?", "2.02 s"),
        # The same result in another unit.
        (_CAR, "in km/h please", "54 km/h"),
        (_CAR, "what is that in mph", "33.6 mph"),
        (_BALL, "in km/h", "71.3 km/h"),
        # One given replaced by a new value, named or not.
        (_CAR, "and after 10 s?", "30 m/s"),
        (_CAR, "what about after 10 s", "30 m/s"),
        (_BALL, "what if it's dropped from 80 m?", "39.6 m/s"),
        (_BALL, "and from 80 m?", "39.6 m/s"),
        # One given scaled.
        (_CAR, "what if the acceleration doubles?", "30 m/s"),
        (_BALL, "what if the mass doubles?", "19.8 m/s"),
        (_BALL, "what if the height is halved", "14 m/s"),
    ],
)
def test_physics_followup_reverifies_the_previous_problem(
    prior: str, line: str, answer: str
) -> None:
    rewritten = physics_followup_problem(line, _recent(prior))
    assert rewritten is not None
    assert _answer(rewritten) == answer


@pytest.mark.parametrize(
    "line", ["show steps", "show me the working", "explain it", "step by step"]
)
def test_physics_followup_asks_for_working_replay_the_problem(line: str) -> None:
    assert physics_followup_problem(line, _recent(_CAR)) == _CAR


@pytest.mark.parametrize(
    ("prior", "line"),
    [
        # No velocity was given: "from rest" is not a value to replace.
        (_CAR, "what if it starts at 2 m/s instead?"),
        # A clock time is not a length, though the ball has one length given.
        (_BALL, "and at 5 pm?"),
        # A unit of another kind, or not a unit at all.
        (_CAR, "in kg"),
        (_CAR, "in decimals please"),
        # "it" names no given to scale.
        (_BALL, "what if it doubles?"),
        # Not a follow-up shape: the model explains.
        (_BALL, "why doesn't mass matter?"),
    ],
)
def test_physics_followup_declines_what_it_cannot_reverify(prior: str, line: str) -> None:
    assert physics_followup_problem(line, _recent(prior)) is None


_CAR_FROM_ZERO = "a car goes from 0 to 20 m/s in 5 seconds. whats the acceleration"


def test_how_far_in_that_time_asks_the_same_car() -> None:
    rewritten = physics_followup_problem("how far did it go in that time", _recent(_CAR_FROM_ZERO))
    assert rewritten is not None
    assert _answer(rewritten) == "50 m"
