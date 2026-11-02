"""A question is read with the setup it states: a die that is not the fair six-sided one,
a biased coin, or a condition after the answer's format is never dropped for a default."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.match.chatter import question_after_chat
from app.modules.math.response_intent import strip_ask_frame
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.extract import extract_math_intent


@pytest.mark.parametrize(
    "text",
    [
        "An eight-sided die is rolled. What is the probability of rolling a 3?",
        "A biased die is rolled. What is the probability of rolling a 6?",
        "Two dice are rolled. What is the probability of rolling a 6?",
        "Three dice are rolled. What is the probability of rolling a 6?",
        "Suppose the die is loaded. What is the probability of rolling a 6?",
    ],
)
def test_a_sentence_naming_a_chance_device_is_a_given(text: str) -> None:
    assert question_after_chat(text) is None


@pytest.mark.parametrize(
    ("text", "question"),
    [
        ("ok cool. what is 2+2", "what is 2+2"),
        ("lol got the second one wrong. random but whats 2+2", "whats 2+2"),
        # No die, coin, deck or bag: a remark, however it is worded.
        ("This is so hard. what is 5 factorial", "what is 5 factorial"),
        ("The test is tomorrow. what is 5 factorial", "what is 5 factorial"),
        ("The test was hard. What is the derivative of x^2", "What is the derivative of x^2"),
        # A letter named before the question: the question's reading sees the whole message.
        (
            "Let i be the interest rate. Simplify 1000(1+i)^2 - 1000",
            "Simplify 1000(1+i)^2 - 1000",
        ),
    ],
)
def test_chat_before_a_question_is_still_dropped(text: str, question: str) -> None:
    assert question_after_chat(text) == question


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("The test is tomorrow. what is 5 factorial", "120"),
        ("The homework is due Friday. what is 2+2", "4"),
        ("Each problem has a trick. what is 7*8", "56"),
        ("My sister has a cat. what is 9 squared", "81"),
        ("That was annoying. whats 72 fahrenheit in celsius", "22.22"),
    ],
)
def test_a_question_after_a_remark_is_still_answered(text: str, answer: str) -> None:
    intent = extract_math_intent(text)
    assert intent is not None
    block = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None and answer in (block.canonical_answer or "")


@pytest.mark.parametrize(
    "text",
    [
        "An eight-sided die is rolled. What is the probability of rolling a 3?",
        "A tetrahedral die is rolled. What is the probability of rolling a 1?",
        "A die is rolled twice. What is the probability of rolling a 6?",
        "A biased coin is tossed. What is the probability of 3 heads in 5 tosses?",
        "A coin lands heads with probability 0.6. What is the probability of 3 heads in 5 tosses?",
        "Two dice are rolled. What is the probability that the sum is 4? "
        "Give your answer as a fraction, assuming the first die is even.",
    ],
)
def test_a_die_or_coin_the_question_describes_otherwise_is_not_read_as_fair(text: str) -> None:
    assert extract_math_intent(text) is None


@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Give your answer as a fraction, assuming the first die is even.", "assuming"),
        ("Express your answer as a decimal if the die is fair.", "if the die is fair"),
    ],
)
def test_only_the_format_words_are_frame(text: str, left: str) -> None:
    stripped = strip_ask_frame(text)
    assert left in stripped
    assert "fraction" not in stripped and "decimal" not in stripped
