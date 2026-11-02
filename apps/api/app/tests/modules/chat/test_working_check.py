"""The arithmetic in working the model wrote itself is recomputed, never guessed at."""

from __future__ import annotations

import pytest

from app.modules.chat.working_check import is_worked_solution, working_note, wrong_steps


@pytest.mark.parametrize(
    ("reply", "slip"),
    [
        # A slip, with or without units around the numbers.
        ("$3.2 \\times 4.5 = 14.8$", ("3.2 \\times 4.5", "14.8")),
        (
            "$v = 3\\,\\text{m/s}^2 \\times 5\\,\\text{s} = 18\\,\\text{m/s}$",
            ("3\\,\\text{m/s}^2 \\times 5\\,\\text{s}", "18\\,\\text{m/s}"),
        ),
        ("$2(8) + 5 = 22$", ("2(8) + 5", "22")),
        (
            "$6.02 \\times 10^{23} \\times 2 = 1.5 \\times 10^{24}$",
            ("6.02 \\times 10^{23} \\times 2", "1.5 \\times 10^{24}"),
        ),
        ("$1,500 \\times 2 = 3,100$", ("1,500 \\times 2", "3,100")),
        ("$\\frac{12}{4} = 4$", ("\\frac{12}{4}", "4")),
    ],
)
def test_wrong_steps_finds_a_slip(reply: str, slip: tuple[str, str]) -> None:
    steps = wrong_steps(reply)
    assert [(step.left, step.shown) for step in steps] == [slip]


@pytest.mark.parametrize(
    "reply",
    [
        # Right, or rounded as a student would round.
        "$3.2 \\times 4.5 = 14.4$",
        "$9.81 \\times 2.02 = 19.8$",
        "$v = \\sqrt{2 \\times 9.81 \\times 20} = 19.8\\,\\text{m/s}$",
        "$t = \\frac{2 \\times 20}{9.81} \\approx 4.1$",
        "$\\frac{1000}{3} = 333$",
        "$6.02 \\times 10^{23} \\times 2 = 1.204 \\times 10^{24}$",
        "$E = 3.98\\times10^{-19} / 1.602\\times10^{-19} = 2.48$",
        # Not arithmetic: a variable, a unit conversion, a prefix step, a word between.
        "$2x + 5 = 21$",
        "$7200 \\text{ m} = 7.2\\,\\text{km}$",
        "$2 \\times 2.26\\times10^6\\,\\text{J} = 4.5\\,\\text{MJ}$",
        "$mL = 2 \\times 2.26\\times10^6 \\approx 4.5$ MJ",
        "$x = 2 \\text{ and } (3)^{2} - 5 (3) + 6 = 0$",
        "$15\\% \\text{ of } 80 = 12$",
        "$\\sin 30^\\circ = 0.5$",
        "$x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$",
        # A power too big to compute, inline code and a code block.
        "$2^{1000000} = 5$",
        "Type `$2 + 2 = 5$` to see the error.",
        "```python\nprint('$2 + 2 = 5$')\n```",
    ],
)
def test_wrong_steps_leaves_right_or_unreadable_working(reply: str) -> None:
    assert wrong_steps(reply) == []


def test_working_note_names_the_first_slip_in_its_own_units() -> None:
    reply = (
        "**Substitution**\n$a = 3\\,\\text{m/s}^2 \\times 5\\,\\text{s} = 18\\,\\text{m/s}$\n"
        "$s = 18 \\times 2 = 37$\n\n**Answer**\n$s = 37\\ \\text{m}$"
    )
    assert working_note(reply) == (
        "Check this step: $3\\,\\text{m/s}^2 \\times 5\\,\\text{s} = 15\\,\\text{m/s}$, "
        "not $18\\,\\text{m/s}$. The lines after it depend on it."
    )


def test_working_note_rounds_a_tie_up_as_a_class_does() -> None:
    # 0.5 * 0.25 is 0.125: to the two places shown, 0.13, not the 0.12 of ties-to-even.
    assert working_note("$0.5 \\times 0.25 = 0.15$") == (
        "Check this step: $0.5 \\times 0.25 = 0.13$, not $0.15$. The lines after it depend on it."
    )


def test_working_note_is_none_when_the_working_adds_up() -> None:
    assert working_note("**Answer**\n$3 \\times 5 = 15$") is None


@pytest.mark.parametrize(
    ("reply", "worked"),
    [
        ("**Given**\n$m = 2$\n\n**Answer**\n$4$", True),
        ("**1. Subtract 5 from both sides**\n$2x = 12$", True),
        ("Is $3 \\times 4 = 13$? No, it's 12.", False),
    ],
)
def test_is_worked_solution(reply: str, worked: bool) -> None:
    assert is_worked_solution(reply) is worked


# A Grade 10 long-jump answer (2026-10-30): t = 3.5/9.8 = 0.36 s, then 2 x 0.36 = 0.71 s
# with the unrounded 0.357 carried. Flagged "0.72, not 0.71", it told a student a right
# answer was broken.
def test_a_line_built_on_a_rounded_result_carries_its_rounding() -> None:
    reply = "$t = \\frac{3.5}{9.8}$\n$t = 0.36\\ \\text{s}$\n\n$t_{flight} = 2 \\times 0.36 = 0.71$"
    assert wrong_steps(reply) == []


@pytest.mark.parametrize(
    "reply",
    [
        # A given is exact as written: only an earlier result is rounded.
        "$3.2 \\times 4.5 = 14.8$",
        # The earlier result's rounding is not enough to reach a real slip.
        "$t = 0.36$\n$2 \\times 0.36 = 0.75$",
        "$x = 4.5$\n$3.2 \\times 4.5 = 14.8$",
    ],
)
def test_a_slip_beyond_the_carried_rounding_is_still_one(reply: str) -> None:
    assert wrong_steps(reply)


# Review: a given is exact, and so is an exact result; only a rounded one carries slack.
@pytest.mark.parametrize(
    "reply",
    [
        "**Given** $m = 3.2\\ \\text{kg}$ $a = 4.5$ $F = 3.2 \\times 4.5 = 14.8$",
        "**Given** $I = 0.2\\ \\text{A}$ $R = 12 / 0.2 = 55$",
        "$I = 6/30 = 0.2$ then $R = 12/0.2 = 55$",
        "$v = 2.5$ $KE = 0.5 \\times 4 \\times 2.5^2 = 13.0$",
    ],
)
def test_a_given_or_exact_result_carries_no_rounding(reply: str) -> None:
    assert wrong_steps(reply)


def test_a_name_solved_then_rounded_carries_its_rounding() -> None:
    reply = "$t = \\frac{3.5}{9.8}$\n$t = 0.36\\ \\text{s}$\n$t_{f} = 2 \\times 0.36 = 0.71$"
    assert wrong_steps(reply) == []


# Second review: a step is checked against the exact value an earlier rounded result had,
# and a result is rounded only when it is within half its last place of that value.
@pytest.mark.parametrize(
    "reply",
    [
        "$t = \\frac{3.5}{9.8} = 0.357 \\approx 0.36$ then $2 \\times 0.36 = 0.71$",
        "$t = \\frac{3.5}{9.8} = 0.357$\n$= 0.36$ then $2 \\times 0.36 = 0.71$",
    ],
)
def test_a_rounding_chain_carries_its_exact_value(reply: str) -> None:
    assert wrong_steps(reply) == []


@pytest.mark.parametrize(
    "reply",
    [
        # 36 on the shown 0.3, 34.3 on the exact 2/7: 40 is neither.
        "$t = 2/7 = 0.3$ then $d = 120 \\times 0.3 = 40$",
        "$x = 1/3 = 0.3$ then $1000 \\times 0.3 = 349$",
        # A name reused in a later part holds a new value, not a rounding of the old one.
        "$I = \\frac{6}{20}$ $I = 0.3$ part b $I = 0.2$ then $R = 12/0.2 = 55$",
    ],
)
def test_a_slip_on_a_rounded_result_is_still_one(reply: str) -> None:
    assert wrong_steps(reply)


# Third review: only a decimal result is carried, never a whole number or an exponent, and
# a later given with the same digits is that given.
@pytest.mark.parametrize(
    "reply",
    [
        "$n = 9/4 = 2$ then $m = 2\\ \\text{kg}$ $F = 2 \\times 4.5 = 10$",
        "$n = 9/4 = 2$ then $0.5 \\times 4 \\times 3^2 = 23.7$",
        "$t = 1/3 = 0.3$ part b $\\mu = 0.3$ then $0.3 \\times 50 = 16.7$",
    ],
)
def test_a_carried_value_stays_with_its_own_result(reply: str) -> None:
    assert wrong_steps(reply)
