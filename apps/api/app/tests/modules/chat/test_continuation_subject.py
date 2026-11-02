"""Continuation turns keep the prior subject's presentation contract."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.chat.continuation_subject import (
    blocks_math_followup,
    chemistry_working_followup_problem,
    classify_presentation_subject,
    effective_presentation_subject,
    is_new_problem_request,
    is_pure_continuation,
)
from app.modules.chat.model_routing.route import route_chat_model
from app.modules.chat.prompt_constants import (
    BIOLOGY_PRESENTATION_HINT,
    NEW_PROBLEM_HINT,
    STATISTICS_PRESENTATION_HINT,
)
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.chemistry.reply_policy import CHEMISTRY_PRESENTATION_HINT
from app.modules.math.followup import is_math_followup
from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_REPLY_POLICY
from app.modules.physics.extract import needs_physics
from app.modules.physics.reply_policy import PHYSICS_INTENT_HINT, PHYSICS_REPLY_POLICY
from app.services.subjects.dispatch import detect_subject

CYCLIST = "A cyclist rides 12 km at 20 km/h then 8 km at 10 km/h. Find average speed."
EQUATION = "Solve 2x + 3 = 11"
STATS = "The values are 2, 4, 6 and 8. Find the sample mean."
BIOLOGY = "In a Punnett square, 1 of 4 offspring shows the recessive allele."
CHEMISTRY = "Balance H2 + O2 -> H2O"


def _exchange(*turns: tuple[str, str]) -> list[tuple[str, str]]:
    return list(turns)


def test_another_is_not_itself_a_subject() -> None:
    assert detect_subject("Another") is None
    assert classify_presentation_subject("Another") is None
    assert is_pure_continuation("Another")
    assert is_pure_continuation("Another such question")
    assert is_pure_continuation("Trickier")
    assert is_pure_continuation("One more")
    assert is_pure_continuation("Same but harder")
    assert is_pure_continuation("Make it harder")
    assert is_pure_continuation("Change chapter")
    assert not is_pure_continuation("How do plants grow?")
    assert not is_pure_continuation("explain photosynthesis")
    assert not is_pure_continuation("Write me an email")


def test_physics_continuation_keeps_physics_and_a_new_topic_does_not() -> None:
    assert needs_physics(CYCLIST)
    prior = _exchange(("user", CYCLIST), ("assistant", "The average speed is 48 km/h."))
    assert effective_presentation_subject("Another", prior) == "physics"
    assert effective_presentation_subject("Another such question", prior) == "physics"
    assert effective_presentation_subject("Change chapter", prior) == "physics"
    assert effective_presentation_subject("Make it harder", prior) == "physics"
    assert effective_presentation_subject("Trickier", prior) == "physics"
    assert effective_presentation_subject("please give me another", prior) == "physics"
    chained = [
        *prior,
        ("user", "Another"),
        ("assistant", "Here is a harder ride."),
    ]
    assert effective_presentation_subject("Trickier", chained) == "physics"
    assert effective_presentation_subject("Write me an email", prior) is None
    assert effective_presentation_subject("How do plants grow?", prior) is None
    france = [
        *prior,
        ("user", "What is the capital of France?"),
        ("assistant", "Paris."),
    ]
    assert effective_presentation_subject("Another", france) is None


def test_math_chemistry_statistics_and_biology_continuations() -> None:
    assert effective_presentation_subject(
        "One more", [("user", EQUATION), ("assistant", "x = 4")]
    ) == ("math")
    assert effective_presentation_subject(
        "Harder", [("user", CHEMISTRY), ("assistant", "2 H2O")]
    ) == ("chemistry")
    assert effective_presentation_subject("Another", [("user", STATS), ("assistant", "5")]) == (
        "statistics"
    )
    assert effective_presentation_subject(
        "Another", [("user", BIOLOGY), ("assistant", "100 fold")]
    ) == ("biology")


def test_style_hints_follow_the_continuation_subject() -> None:
    physics_prior = [("user", CYCLIST), ("assistant", "48 km/h")]
    for query in ("Another", "Another such question", "Change chapter", "Make it harder"):
        hints = _style_format_hints(
            query_text=query,
            is_day_plan=False,
            minimal_personal_context=False,
            prior_messages=physics_prior,
        )
        assert PHYSICS_INTENT_HINT in hints
        assert MATH_REPLY_POLICY not in hints

    email = _style_format_hints(
        query_text="Write me an email",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=physics_prior,
    )
    assert PHYSICS_INTENT_HINT not in email

    math_hints = _style_format_hints(
        query_text="One more",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=[("user", EQUATION), ("assistant", "x = 4")],
    )
    assert MATH_INTENT_HINT in math_hints
    # "One more" wants a new problem, which outranks the policy's no-examples rule.
    assert math_hints[-2:] == [MATH_REPLY_POLICY, NEW_PROBLEM_HINT]

    chemistry = _style_format_hints(
        query_text="Another",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=[("user", CHEMISTRY), ("assistant", "2 H2O")],
    )
    assert CHEMISTRY_PRESENTATION_HINT in chemistry
    assert MATH_REPLY_POLICY not in chemistry

    statistics = _style_format_hints(
        query_text="Another",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=[("user", STATS), ("assistant", "5")],
    )
    assert STATISTICS_PRESENTATION_HINT in statistics

    biology = _style_format_hints(
        query_text="Another",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=[("user", BIOLOGY), ("assistant", "100 fold")],
    )
    assert BIOLOGY_PRESENTATION_HINT in biology


def test_why_is_it_after_physics_keeps_the_physics_contract() -> None:
    prior = [("user", CYCLIST), ("assistant", "48 km/h")]
    assert effective_presentation_subject("why is it 40", prior) == "physics"
    hints = _style_format_hints(
        query_text="why is it 40",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=prior,
    )
    assert PHYSICS_INTENT_HINT in hints


def test_how_after_physics_is_not_a_math_solver_replay() -> None:
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content=CYCLIST),
        SimpleNamespace(id=uuid4(), role="assistant", content="48 km/h"),
    ]
    assert is_math_followup("How?", recent, blocked=blocks_math_followup) is False
    math_recent = [
        SimpleNamespace(id=uuid4(), role="user", content=EQUATION),
        SimpleNamespace(id=uuid4(), role="assistant", content="```answer\nx = 4\n```"),
    ]
    assert is_math_followup("How?", math_recent) is True
    assert is_math_followup("Another", math_recent) is False


def test_how_after_chemistry_resolves_the_prior_problem() -> None:
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content=CHEMISTRY),
        SimpleNamespace(id=uuid4(), role="assistant", content="2 H2O"),
    ]
    assert is_math_followup("How?", recent, blocked=blocks_math_followup) is False
    assert chemistry_working_followup_problem("how?", recent) == CHEMISTRY
    assert chemistry_working_followup_problem("why?", recent) == CHEMISTRY
    assert chemistry_working_followup_problem(EQUATION, recent) is None
    assert chemistry_working_followup_problem(CYCLIST, recent) is None
    assert chemistry_working_followup_problem("How?", math_recent_for_chemistry()) is None


def math_recent_for_chemistry() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id=uuid4(), role="user", content=EQUATION),
        SimpleNamespace(id=uuid4(), role="assistant", content="x = 4"),
    ]


def test_another_inherits_the_strong_model_after_a_hard_turn() -> None:
    prior = "a block slides down a 90° frictionless incline, find its acceleration"
    assert route_chat_model("Another", prior_user=prior) == "smart-chat"
    assert route_chat_model("Write me an email", prior_user=prior) == route_chat_model(
        "Write me an email"
    )
    assert route_chat_model("explain photosynthesis", prior_user="debug this algorithm") == (
        "qwen-3.7-flash"
    )


@pytest.mark.parametrize(
    "line, expected",
    [
        ("One more", True),
        ("I said one more example", True),
        ("another example please", True),
        ("Give me a new problem", True),
        ("One more, harder", True),
        ("Next one!", True),
        ("Another way", False),
        ("Another method", False),
        ("Why?", False),
        ("A car goes 5 km in 1 h, another?", False),
    ],
)
def test_is_new_problem_request_reads_a_fresh_problem_ask(line: str, expected: bool) -> None:
    assert is_new_problem_request(line) is expected


def test_one_more_asks_for_a_new_problem_after_the_subject_policy() -> None:
    speed = "John drove 20 kms in 2 hours. What is his speed"
    prior = _exchange(("user", speed), ("assistant", "John's speed = 10 km/h."))
    repeated = [*prior, ("user", "One more"), ("assistant", "John's speed = 10 km/h.")]
    assert effective_presentation_subject("One more", prior) == "physics"
    assert effective_presentation_subject("I said one more example", repeated) == "physics"
    for compact in (False, True):
        parts = _style_format_hints(
            query_text="I said one more example",
            is_day_plan=False,
            minimal_personal_context=False,
            compact=compact,
            prior_messages=repeated,
        )
        assert NEW_PROBLEM_HINT in parts
        assert parts.index(NEW_PROBLEM_HINT) > parts.index(PHYSICS_REPLY_POLICY)
    plain = _style_format_hints(
        query_text="Why?",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=prior,
    )
    assert NEW_PROBLEM_HINT not in plain


def test_one_more_does_not_replay_the_chemistry_problem() -> None:
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content=CHEMISTRY),
        SimpleNamespace(id=uuid4(), role="assistant", content="2 H2O"),
    ]
    assert chemistry_working_followup_problem("One more", recent) is None
    assert chemistry_working_followup_problem("Another", recent) is None
