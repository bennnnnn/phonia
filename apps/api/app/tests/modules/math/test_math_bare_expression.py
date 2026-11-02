"""A message that is only an algebra expression: what it means, an example, what to ask.

"3x" was answered "3 times 3 is 9" and "4x" "4 times 4 is 16" (2026-10-24).
"""

from __future__ import annotations

import re

import pytest

from app.modules.math.match.bare_expression import bare_expression_reply, read_bare_expression
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import needs_symbolic_math

_3X = """**$3x$** means **3 times x**. Written right before a letter, a number multiplies it.

For example, if $x = 4$:
$$3x = 3 \\times 4 = 12$$

What would you like to do with it? You could:
- find its value for a number: "3x when x = 4"
- solve an equation: "3x = 12"
- graph it: "graph y = 3x\""""


def test_3x_is_3_times_x_with_an_example_and_what_to_ask() -> None:
    assert bare_expression_reply("3x") == _3X
    assert bare_expression_reply("what is 3x?") == _3X
    assert bare_expression_reply("3X") == _3X


@pytest.mark.parametrize(
    "message, means, example",
    [
        ("4x", "4 times x", "4x = 4 \\times 4 = 16"),
        ("2y", "2 times y", "2y = 2 \\times 4 = 8"),
        ("3x+2", "3 times x, plus 2", "3x + 2 = 3 \\times 4 + 2 = 14"),
        ("3x − 2", "3 times x, minus 2", "3x - 2 = 3 \\times 4 - 2 = 10"),
        (
            "x^2+3x+2",
            "x squared, plus 3 times x, plus 2",
            "x^{2} + 3x + 2 = 4^{2} + 3 \\times 4 + 2 = 30",
        ),
        ("3x²", "3 times x squared", "3x^{2} = 3 \\times 4^{2} = 48"),
        ("-3x + 5", "negative 3 times x, plus 5", "-3x + 5 = -3 \\times 4 + 5 = -7"),
        ("x/2", "x divided by 2", "x / 2 = 4 \\div 2 = 2"),
        ("a + b", "a plus b", "a + b = 4 + 2 = 6"),
        ("2xy", "2 times x times y", "2xy = 2 \\times 4 \\times 2 = 16"),
    ],
)
def test_an_expression_says_what_it_means_and_works_an_example(
    message: str, means: str, example: str
) -> None:
    reply = bare_expression_reply(message)
    assert reply is not None
    assert f"means **{means}**." in reply
    assert f"$${example}$$" in reply


def test_brackets_are_multiplied_and_can_be_expanded() -> None:
    reply = bare_expression_reply("2(x+1)")
    assert reply is not None
    assert "a number multiplies everything in it" in reply
    assert "$$2(x + 1) = 2 \\times (4 + 1) = 10$$" in reply
    assert '"expand 2(x + 1)"' in reply
    pair = bare_expression_reply("(x+1)(x-1)")
    assert pair is not None and "Two brackets written side by side are multiplied." in pair


def test_a_value_that_divides_by_zero_takes_another_example() -> None:
    reply = bare_expression_reply("1/(x-4)")
    assert reply is not None
    assert "if $x = 5$" in reply


@pytest.mark.parametrize(
    "message",
    ["3x", "4x", "3x+2", "x^2+3x+2", "2(x+1)", "(x+1)(x-1)", "2y", "a + b", "2xy", "x/2"],
)
def test_every_suggestion_is_a_question_the_maths_engine_solves(message: str) -> None:
    reply = bare_expression_reply(message)
    assert reply is not None
    suggestions = re.findall(r'^- [^"]*"([^"]+)"$', reply, re.MULTILINE)
    assert suggestions
    for suggestion in suggestions:
        assert needs_symbolic_math(suggestion), suggestion
        assert extract_math_intent(suggestion) is not None, suggestion


@pytest.mark.parametrize(
    "message",
    [
        # One letter, or letters alone.
        "x", "X", "a", "xy", "hi", "ok",
        # A number and a unit, a size or a name.
        "4K", "5G", "3D", "A4", "B12", "Y2K", "x86", "x2", "5k", "10k run", "3pm", "5am", "2b",
        "4u", "3a", "4n", "co2", "h2o", "b2b", "1v1", "0x10",
        # A size: "x" between numbers.
        "4x4", "2x4", "3x3", "8x5", "2x4 lumber", "3 x 4",
        # An equation, arithmetic, or a sentence.
        "3x = 12", "1+1", "I am 3x faster",
        # A word beside the maths is an instruction for the maths engine, not a bare expression.
        "integrate x e^x dx", "sin x", "log 2x", "2ab",
        # i and e are numbers: the maths engine answers these.
        "i^2", "what is i^23", "(2+3i)(1-i)", "2e + 1",
    ],
)  # fmt: skip
def test_what_is_not_an_expression_is_not_read_as_one(message: str) -> None:
    assert read_bare_expression(message) is None
    assert bare_expression_reply(message) is None


@pytest.mark.parametrize(
    "prior",
    [
        "Your turn: what do you get when you simplify 2x + x?",
        "Try this one.\n\n```quiz\n{}\n```",
    ],
)
def test_an_answer_to_a_maths_question_is_not_explained(prior: str) -> None:
    """ "3x" after "What is 2x + x?" is the user's answer: the model checks it."""
    assert bare_expression_reply("3x", prior_assistant=prior) is None


def test_after_any_other_question_it_is_explained() -> None:
    assert bare_expression_reply("3x", prior_assistant="Hey bini! How can I help today?") == _3X
