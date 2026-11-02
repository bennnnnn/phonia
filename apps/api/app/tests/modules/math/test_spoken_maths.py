"""Maths said in words reads as the same maths written in symbols (match/spoken.py)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.match.spoken import spoken_math_to_plain
from app.modules.math.tools import _build_verified_block, extract_math_intent

_SETTINGS = Settings(math_tools_enabled=True)


@pytest.mark.parametrize(
    ("said", "written"),
    [
        ("what is 3 squared", "what is 3^2"),
        ("what is 5 cubed", "what is 5^3"),
        ("graph y equals x squared", "graph y = x^2"),
        ("solve x squared minus 4 equals 0", "solve x^2 - 4 = 0"),
        ("what is seven plus eight", "what is 7 + 8"),
        ("what's three times four", "what's 3 * 4"),
        ("what is twenty one times three", "what is 21 * 3"),
        ("what is a hundred minus seven", "what is 100 - 7"),
        ("what is 15 percent of 80", "what is 15% of 80"),
        ("what is 3 over 4 plus 1 over 4", "what is 3 / 4 + 1 / 4"),
        ("plot y equals sine x", "plot y = sin x"),
        ("what is negative 5 plus 3", "what is -5 + 3"),
        ("what is 2 to the third power", "what is 2^3"),
        ("what is 2 to the power of 10", "what is 2^10"),
        ("square root of one hundred", "sqrt(100)"),
        ("what is 12 divided by 4", "what is 12 / 4"),
        # Number words with no operator beside them stay words.
        ("which one is bigger", "which one is bigger"),
        ("I have two kids", "I have two kids"),
        ("turn over five cards", "turn over five cards"),
    ],
)
def test_spoken_maths_becomes_symbols(said: str, written: str) -> None:
    assert spoken_math_to_plain(said) == written


@pytest.mark.parametrize(
    ("said", "answer"),
    [
        ("what is 3 squared", "9"),
        ("what is 5 cubed", "125"),
        ("solve x squared minus 4 equals 0", r"x = \pm 2"),
        ("what is seven plus eight", "15"),
        ("what is 15 percent of 80", "12"),
        ("what is 3 over 4 plus 1 over 4", "1"),
        ("what is negative 5 plus 3", "-2"),
        ("square root of one hundred", "10"),
        ("x squared plus 2x plus 1 equals 0", "x = -1"),
    ],
)
def test_spoken_questions_get_the_verified_answer(said: str, answer: str) -> None:
    intent = extract_math_intent(said)
    assert intent is not None
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None and block.canonical_answer == answer


@pytest.mark.parametrize(
    ("said", "expr"),
    [
        # A graph read with no function drew nothing.
        ("graph y equals x squared", "x**2"),
        ("graph y equals 2x plus 3", "2x + 3"),
        ("plot y equals sine x", "sin x"),
    ],
)
def test_a_spoken_graph_reads_its_function(said: str, expr: str) -> None:
    intent = extract_math_intent(said)
    assert intent is not None and intent.kind == "graph"
    assert intent.expr == expr


@pytest.mark.parametrize(
    "text",
    [
        "plus I'm over it, honestly",
        "times are tough right now",
        "that equals trouble with my boss",
        "she's over thirty and still loves cartoons",
        "it was two times better than last year",
        "my score went from three to five",
        "I'll be there in five minutes",
        "which one is bigger, the blue box or the red one?",
    ],
)
def test_everyday_words_stay_chat(text: str) -> None:
    assert extract_math_intent(text) is None
