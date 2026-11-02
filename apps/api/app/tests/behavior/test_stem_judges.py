"""The STEM sweep's judges pass a right card and fail a wrong one."""

from __future__ import annotations

from typing import Any

import pytest

from app.tests.behavior.stem_math_judge import judge_check
from app.tests.behavior.stem_sweep import Entry, card_values, check_answer, same_quantity


@pytest.mark.parametrize(
    ("check", "card", "right"),
    [
        (("num", "16"), "12 + 6 ÷ 3 × 2 = 16", True),
        (("num", "16"), "12 + 6 ÷ 3 × 2 = 12", False),
        (("num", "25/pi"), r"\approx 7.96", True),
        (("num", "5"), r"\left(0, 5\right)", True),
        (("num", "5"), r"\left(0, 6\right)", False),
        (("nums", ["2", "-3"]), r"\left(2, -3\right)\ \text{minimum}", True),
        (("nums", ["160", "200"]), "160:200", True),
        (("nums", ["160", "200"]), "180:180", False),
        (("nums", ["176", "2"]), "1234 ÷ 7 = 176 R2", True),
        (("nums", ["176", "2"]), "1234 ÷ 7 = 176 R3", False),
        (("num", "10.95"), r"\$10.95", True),
        (("num", "10.95"), r"\$11.95", False),
        (("expr", "(1-log(x))/x**2"), r"\frac{1 - \ln{\left(x \right)}}{x^{2}}", True),
        (("expr", "5 - x/2"), r"y = -\frac{1}{2}x + 5", True),
        (("expr", "5 - x/2"), r"y = -2x + 11", False),
        (("anti", "tan(x)"), r"\tan{\left(x \right)} + C", True),
        (("anti", "tan(x)"), r"\sec^{2}{\left(x \right)} + C", False),
        (("set", "Interval.open(4, oo)"), "x > 4", True),
        (("set", "Interval.open(4, oo)"), r"x \ge 4", False),
        (
            ("set", "Union(Interval(-oo, -4), Interval(3, oo))"),
            r"x \le -4 \text{ or } x \ge 3",
            True,
        ),
        (("set", "Interval(3, oo)"), r"\left[3, \infty\right)", True),
        (
            ("matrix", [["2", "1"], ["4", "3"]]),
            r"\left[\begin{matrix}2 & 1\\4 & 3\end{matrix}\right]",
            True,
        ),
        (
            ("matrix", [["2", "1"], ["4", "3"]]),
            r"\left[\begin{matrix}1 & 2\\3 & 4\end{matrix}\right]",
            False,
        ),
        (("regex", r"2\s*:\s*3"), "2 : 3", True),
        # An odd root of a negative number is read as real, as a student reads it.
        (("num", "-2"), r"\sqrt[3]{-8}", True),
        (("num", "1 - sqrt(2)"), r"- \sqrt[3]{5 \sqrt{2} - 7}", True),
        (("num", "sqrt(2) - 1"), r"- \sqrt[3]{5 \sqrt{2} - 7}", False),
    ],
)
def test_math_judge_reads_the_card(check: tuple[str, Any], card: str, right: bool) -> None:
    assert judge_check(check, card, "") is right


@pytest.mark.parametrize(
    ("card", "want", "abs_tol", "right"),
    [
        # Rounded to the inputs' significant figures: 0.2 mol for 0.204 is right.
        ("n = 0.2 mol", (0.204, "mol"), None, True),
        ("n = 0.3 mol", (0.204, "mol"), None, False),
        ("m = 4.40 g CO₂", (4.40, "g"), None, True),
        ("N = 2.41 × 10²⁴ molecules", (2.41e24, ""), None, True),
        ("M(CuSO₄·5H₂O) = 249.68 g/mol", (249.677, "g/mol"), None, True),
        ("pH = 2.60", (2.602, ""), 0.02, True),
        ("pH = 2.70", (2.602, ""), 0.02, False),
        ("ΔT = 2.05 °C", (2.048, "delta_degC"), None, True),
        ("P = 248 kPa", (2.45, "atm"), None, True),
    ],
)
def test_chemistry_card_matches_the_worked_answer(
    card: str, want: tuple[float, str], abs_tol: float | None, right: bool
) -> None:
    reply = f"```answer\nverified: true\nnotation: chemistry\n{card}\n```"
    entry = Entry("t", "t", "t", "answer", answers=(want,), abs_tol=abs_tol)
    _got, problems = check_answer(entry, "chemistry", reply)
    assert (not problems) is right, problems


def test_a_tiny_physics_value_is_still_compared() -> None:
    """1.6e-17 J against 1.92e-17 J is 20% off, however small both are."""
    assert not same_quantity((1.6e-17, "J"), (1.922e-17, "J"))[0]
    assert same_quantity((1.6e-17, "J"), (1.602e-17, "J"))[0]


def test_card_values_skip_marker_lines() -> None:
    reply = "```answer\nverified: true\nnotation: chemistry\nn = 0.500 mol\n```"
    assert card_values(reply) == [(0.5, "mol", "0.500")]


def test_a_text_answer_ignores_subscripts_and_arrows() -> None:
    entry = Entry("t", "t", "t", "answer", text=("2H2 + O2 -> 2H2O",))
    reply = "```answer\n2 H₂ + O₂ → 2 H₂O\n```"
    assert check_answer(entry, "chemistry", reply)[1] == []
