"""Draws from a bag of colours: the whole message read, and the replacement never assumed."""

from __future__ import annotations

from fractions import Fraction

import pytest

from app.core.config import Settings
from app.modules.math.tools.prompt import build_math_augmentation, needs_symbolic_math
from app.modules.math.tools.school.bag_draws import (
    bag_draws_probability,
    extract_bag_draws_intent,
)


@pytest.mark.parametrize(
    ("text", "op", "counts"),
    [
        (
            "a bag has 3 red and 5 blue marbles, pick 2 without replacement, probability both red",
            "bag_draws",
            [3, 8, 2],
        ),
        (
            "A jar contains 4 red, 3 green and 5 blue marbles. Two marbles are drawn without "
            "replacement. What is the probability that both are green?",
            "bag_draws",
            [3, 12, 2],
        ),
        (
            "2 balls are drawn at random without replacement from a box containing 6 white and "
            "4 black balls. what is the probability that both are white?",
            "bag_draws",
            [6, 10, 2],
        ),
        (
            "a bag has 3 red and 5 blue marbles, pick 2 with replacement, probability both red",
            "bag_draws_with_replacement",
            [3, 8, 2],
        ),
        (
            "a bag has 3 red and 5 blue marbles. you draw 3 at the same time. what is the "
            "probability all three are blue?",
            "bag_draws",
            [5, 8, 3],
        ),
    ],
)
def test_extract_bag_draws_intent_reads_the_whole_question(
    text: str, op: str, counts: list[int]
) -> None:
    intent = extract_bag_draws_intent(text)
    assert intent is not None
    assert intent.school_op == op
    assert intent.vec_a == [float(value) for value in counts]


@pytest.mark.parametrize(
    "text",
    [
        # Whether the marbles go back is never assumed.
        "a bag has 3 red and 5 blue marbles, pick 2, probability both red",
        # Only "every draw one colour" is read.
        "a bag has 3 red and 5 blue marbles, pick 2 without replacement, "
        "probability one of each colour",
        "a bag has 3 red and 5 blue marbles, pick 2 without replacement, "
        "probability the first is red and the second is blue",
        "a bag has 3 red and 5 blue marbles, pick 2 without replacement, "
        "probability at least one red",
        # "both" is two draws; a colour that is not in the bag is not read.
        "a bag has 3 red and 5 blue marbles, pick 3 without replacement, probability both red",
        "a bag has 3 red and 5 blue marbles, pick 2 without replacement, probability both green",
        # Extra conditions ride along.
        "a bag has 3 red and 5 blue marbles. the first is red. pick 2 without replacement, "
        "probability both red",
        # Not a probability question.
        "my bag has 3 red and 5 blue scarves, which should I wear",
    ],
)
def test_extract_bag_draws_intent_declines_what_it_cannot_read(text: str) -> None:
    assert extract_bag_draws_intent(text) is None


@pytest.mark.parametrize(
    ("favourable", "total", "draws", "replaced", "expected"),
    [
        (3, 8, 2, False, Fraction(3, 28)),
        (3, 8, 2, True, Fraction(9, 64)),
        (5, 8, 3, False, Fraction(5, 28)),
        (1, 8, 2, False, Fraction(0)),
        (6, 10, 2, False, Fraction(1, 3)),
    ],
)
def test_bag_draws_probability_multiplies_each_draw(
    favourable: int, total: int, draws: int, replaced: bool, expected: Fraction
) -> None:
    assert bag_draws_probability(favourable, total, draws, replaced=replaced) == expected


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        (
            "a bag has 3 red and 5 blue marbles, pick 2 without replacement, probability both red",
            r"\frac{3}{28} \approx 0.1071",
        ),
        (
            "a bag has 3 red and 5 blue marbles, pick 2 with replacement, probability both red",
            r"\frac{9}{64} = 0.140625",
        ),
    ],
)
@pytest.mark.asyncio
async def test_build_math_augmentation_verifies_bag_draws(text: str, answer: str) -> None:
    assert needs_symbolic_math(text)
    _, verified = await build_math_augmentation(text, Settings(math_tools_enabled=True))
    assert verified is not None
    assert verified.canonical_answer == answer
    assert verified.worked_reply is not None
    assert r"\frac{3}{8} \times" in verified.worked_reply
