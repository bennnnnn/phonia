"""A message's separate requests, and a problem's several questions (``plan_turn``).

"Will it rain tomorrow? And what's 15% of 80?" was one request: a question of numbers alone
had no topics, so the plan merged it into the weather and the maths route took both. "A ball
is dropped from 20 m. What is its speed after 1 s? How long does it take to reach the
ground?" cut the second question from its givens, read it as a trip from the user, and
searched. Each question about a problem now carries the problem's setup and is read with
it; a request of its own (a forecast, the news, places) stands alone.
"""

from __future__ import annotations

import pytest

from app.modules.chat.turn_prep.clauses import topic_words
from app.modules.chat.turn_prep.intents import plan_turn


def _parts(text: str) -> list[tuple[str, str]]:
    return [(part.text, part.kind) for part in plan_turn(text).parts]


def test_a_question_of_numbers_alone_has_topics() -> None:
    assert topic_words("And what's 15% of 80?") >= {"15%", "80"}


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        (
            "Will it rain tomorrow? And what's 15% of 80?",
            [("Will it rain tomorrow?", "live"), ("what's 15% of 80?", "solve")],
        ),
        (
            "What's the latest news on SpaceX? And what is 12 squared?",
            [("What's the latest news on SpaceX?", "live"), ("what is 12 squared?", "solve")],
        ),
        (
            "A ball is dropped from 20 m. How long does it take to reach the ground? What's the "
            "weather like today?",
            [
                (
                    "A ball is dropped from 20 m. How long does it take to reach the ground?",
                    "solve",
                ),
                ("What's the weather like today?", "live"),
            ],
        ),
        (
            "A ball is dropped from 20 m. How long does it take to land? Who won the Arsenal "
            "game last night?",
            [
                ("A ball is dropped from 20 m. How long does it take to land?", "solve"),
                ("Who won the Arsenal game last night?", "live"),
            ],
        ),
        (
            "A train travels at 20 m/s. How long does it take to reach the station 4 km away? "
            "Are there coffee shops near me?",
            # "A train travels at 20 m/s" has no subject of its own: no setup, and the
            # question has its own givens.
            [
                ("How long does it take to reach the station 4 km away?", "solve"),
                ("Are there coffee shops near me?", "live"),
            ],
        ),
    ],
)
def test_a_request_of_its_own_stands_beside_homework(
    text: str, parts: list[tuple[str, str]]
) -> None:
    assert _parts(text) == parts


@pytest.mark.parametrize(
    ("text", "questions"),
    [
        (
            "A ball is dropped from 20 m. What is its speed after 1 s? How long does it take to "
            "reach the ground?",
            ["What is its speed after 1 s?", "How long does it take to reach the ground?"],
        ),
        (
            "A ball is thrown up at 15 m/s. How high does it go? How long does it take to reach "
            "the top?",
            ["How high does it go?", "How long does it take to reach the top?"],
        ),
    ],
)
def test_each_question_of_a_problem_carries_its_setup(text: str, questions: list[str]) -> None:
    plan = plan_turn(text)
    setup = text.split(". ", 1)[0] + "."

    assert plan.context == ""
    assert [(part.text, part.kind) for part in plan.parts] == [
        (f"{setup} {question}", "solve") for question in questions
    ]


@pytest.mark.parametrize(
    "text",
    [
        "A ball is dropped from a height of 20 m. How long does it take to reach the ground?",
        "A car of mass 1000 kg moves at 20 m/s. It brakes to a stop in 4 s. What is the braking "
        "force?",
        "I'm studying for a test. A ball is dropped from 20 m. How long does it take to reach "
        "the ground?",
        "A car moves 100 m in 20 s. Find its speed and give the unit.",
        "Two dice are rolled. What is the probability that the sum is 4? Give your answer as a "
        "fraction.",
    ],
)
def test_one_question_in_several_sentences_is_one_request(text: str) -> None:
    assert not plan_turn(text).multi


def test_a_setup_about_the_user_is_no_problem() -> None:
    plan = plan_turn("I'm a backend dev. What laptop should I buy? Also, find remote jobs.")

    assert plan.context == "I'm a backend dev"
    assert [part.text for part in plan.parts] == ["What laptop should I buy?", "find remote jobs."]


@pytest.mark.parametrize(
    ("text", "context", "parts"),
    [
        (
            "I'm a backend dev. What laptop should I buy? What is 12 squared?",
            "I'm a backend dev",
            ["What laptop should I buy?", "What is 12 squared?"],
        ),
        (
            "We're in Paris. How far is 300 m in feet? What's good to eat here?",
            "We're in Paris",
            ["How far is 300 m in feet?", "What's good to eat here?"],
        ),
    ],
)
def test_a_later_question_lends_the_setup_no_subject(
    text: str, context: str, parts: list[str]
) -> None:
    plan = plan_turn(text)

    assert plan.context == context
    assert [part.text for part in plan.parts] == parts
