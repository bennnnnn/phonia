"""The marks and names the math keyboard types are read as a student means them."""

from __future__ import annotations

import pytest

from app.modules.math.match.arithmetic import bare_arithmetic_expr
from app.services.subjects.dispatch import detect_subject
from app.services.symbolic_text import fold_latex_marks


@pytest.mark.parametrize(
    ("typed", "read"),
    [
        ("20\\% of 50", "20% of 50"),
        ("f^{\\prime}(x)", "f'(x)"),
        ("f^{\\prime\\prime}(x)", "f''(x)"),
        ("y\\prime", "y'"),
        ("x^{2} + 1", "x^{2} + 1"),
        ("no latex at all", "no latex at all"),
    ],
)
def test_fold_latex_marks(typed: str, read: str) -> None:
    assert fold_latex_marks(typed) == read


@pytest.mark.parametrize(
    ("text", "expr"),
    [
        ("\\ln(e)", "ln(e)"),
        ("\\sqrt{e}", "sqrt(e)"),
        ("\\ln(e^2)", "ln(e^2)"),
        # A constant alone, or a word, is not arithmetic.
        ("e", None),
        ("pi", None),
        ("pie", None),
        ("I am", None),
    ],
)
def test_keypad_constants_count_as_numbers(text: str, expr: str | None) -> None:
    assert bare_arithmetic_expr(text) == expr


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        ("$\\sec(\\frac{\\pi}{3})$", "math"),
        ("$\\csc(\\frac{\\pi}{6})$", "math"),
        ("$\\cot(\\frac{\\pi}{4})$", "math"),
        ("sec 60", "math"),
        ("cot 45 degrees", "math"),
        ("sec x = 2", "math"),
        # Seconds, a fabric, a moment: not trig.
        ("wait 30 sec", None),
        ("set a timer for 10 sec", None),
        ("a car goes 20 m in 4 sec", None),
        ("the cotton costs 3 dollars", None),
        ("be back in a sec 2 min", None),
        ("give me a sec", None),
    ],
)
def test_reciprocal_trig_is_math_and_seconds_are_not(text: str, subject: str | None) -> None:
    assert detect_subject(text) == subject
