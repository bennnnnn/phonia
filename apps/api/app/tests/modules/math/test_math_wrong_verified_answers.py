"""Answers a sweep found shown as server-verified although they were wrong.

Every row is a real prompt from the October 2026 STEM sweep (or a phrasing of
one). The rule for each family is the same: the server either answers the
question that was asked, correctly, or verifies nothing and leaves the turn to
the model. A green answer card that answers a different question is never an
option.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.math.followup import answer_claim_problem, pronoun_math_problem
from app.modules.math.request_consumption import request_consumption_complete
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.key_steps import equation_key_steps
from app.modules.math.solve.parse import parse_expression
from app.modules.math.solve.work_check import check_work
from app.modules.math.tools.block.work import format_work_check_reply
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import needs_symbolic_math
from app.services.subjects.dispatch import build_subject_augmentation, maybe_direct_subject_reply
from app.tests.behavior.cases import Case, Expect
from app.tests.behavior.harness import route_case

_NON_FINITE = re.compile(r"\\tilde\{\\infty\}|\bNaN\b|\bnan\b|\bzoo\b")


async def _verified(text: str) -> tuple[str | None, str | None]:
    """(canonical answer, direct reply) for one turn with no model call."""
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    augmentation = await build_subject_augmentation(text, settings)
    verified = augmentation.verified
    answer = getattr(verified, "canonical_answer", None) if verified is not None else None
    return answer, maybe_direct_subject_reply(verified, text)


def _history(*turns: str) -> tuple[tuple[str, str], ...]:
    roles = ("user", "assistant")
    return tuple((roles[index % 2], text) for index, text in enumerate(turns))


# --- A. "find the X of <equation>" is not "solve for x" -------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("find the vertex of y = x^2 - 6x + 5", r"\left(3, -4\right)"),
        ("find the vertex of the parabola y = 2x^2 + 8x - 1", r"\left(-2, -9\right)"),
        # The stationary-point rule already answers this one, and says which kind.
        ("what is the turning point of y = x^2 + 4x + 1", r"\left(-2, -3\right)\ \text{minimum}"),
        ("find the axis of symmetry of y = 2x^2 - 8x + 3", "x = 2"),
        ("find the y-intercept of y = 3x + 2", r"\left(0, 2\right)"),
        ("find the y-intercept of y = x^2 - 6x + 5", r"\left(0, 5\right)"),
        ("find the x-intercept of 2x + 3y = 6", r"\left(3, 0\right)"),
        ("find the x-intercepts of y = x^2 - 5x + 6", r"\left(2, 0\right),\ \left(3, 0\right)"),
        # Both axes: "show the intercepts" was no maths at all, "find the intercepts" unsolved.
        (
            "show the intercepts of y = x^2 - 5x + 6",
            r"\text{x-intercepts } \left(2, 0\right),\ \left(3, 0\right);\ "
            r"\text{y-intercept } \left(0, 6\right)",
        ),
        (
            "what are the intercepts of y=x^2-5x+6",
            r"\text{x-intercepts } \left(2, 0\right),\ \left(3, 0\right);\ "
            r"\text{y-intercept } \left(0, 6\right)",
        ),
        (
            "find the x- and y-intercepts of 2x + 3y = 6",
            r"\text{x-intercept } \left(3, 0\right);\ \text{y-intercept } \left(0, 2\right)",
        ),
        ("show the vertex of y = x^2 - 4x + 3", r"\left(2, -1\right)"),
        ("find the discriminant of 3x^2+2x+1=0", r"b^{2} - 4ac = -8"),
        ("discriminant of 3x^2 + 2x + 1", r"b^{2} - 4ac = -8"),
        ("what is the sum of the roots of x^2 - 5x + 6 = 0", r"x_{1} + x_{2} = 5"),
        ("find the sum of the roots of 2x^2 - 7x + 3 = 0", r"x_{1} + x_{2} = \frac{7}{2}"),
        ("what is the product of the roots of x^2 - 5x + 6 = 0", r"x_{1} x_{2} = 6"),
        (
            "find k so that x^2 + kx + 9 = 0 has exactly one solution",
            r"k = -6 \text{ or } k = 6",
        ),
        (
            "find the equation of the line parallel to y = 3x + 1 through (2, 5)",
            "y = 3x - 1",
        ),
        (
            "find the equation of the line perpendicular to y = 2x + 1 passing through (4, 3)",
            r"y = -\frac{1}{2}x + 5",
        ),
        ("what is the slope of the line 2x + 3y = 6", r"m = -\frac{2}{3}"),
        ("find the gradient of y = 4x - 3", "m = 4"),
        ("find the gradient of the line joining (-1, 4) and (3, -4)", "-2"),
    ],
)
async def test_a_feature_of_an_equation_is_answered_not_solved_for_x(
    text: str, answer: str
) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        # No vertex, no single intercept, no one solution: never the roots in x.
        "find the vertex of y = x^3 - 3x",
        "find the axis of symmetry of y = 4x + 1",
        "find the sum of the roots of x^2 + 2x + 1 = 0",
        "find k so that kx^2 + 4x + 1 = 0 has exactly one solution",
        "find the y-intercept of x = 4",
        # No real x-intercept: both axes are not verified, never half of them.
        "find the intercepts of y = x^2 + 1",
        "what is the domain of the solution of x^2 = 4",
    ],
)
async def test_a_feature_it_cannot_read_is_left_unverified(text: str) -> None:
    canonical, reply = await _verified(text)
    assert canonical is None
    assert reply is None


@pytest.mark.parametrize(
    "text",
    [
        "find the vertex of y = x^3 + 1",
        "find the y-intercept of y = 2^x",
        "what is the discriminant of x^2 + x + 1 = 0",
        "find the gradient of y = x^2",
        "find the line perpendicular to y = x through (1, 1)",
        "find c so that x^2 + 6x + c = 0 has equal roots",
    ],
)
def test_the_audit_refuses_solving_an_equation_when_a_feature_was_asked(text: str) -> None:
    solved = MathIntent(kind="equation", lhs="y", rhs="x^2 + 1", operation="solve")
    assert not request_consumption_complete(text, solved)


def test_the_audit_still_lets_a_plain_solve_through() -> None:
    solved = MathIntent(kind="equation", lhs="x^2 - 5x + 6", rhs="0", operation="solve")
    assert request_consumption_complete("solve x^2 - 5x + 6 = 0", solved)
    assert request_consumption_complete("find the roots of x^2 - 5x + 6 = 0", solved)


# --- B. a student's answer is checked, never certified ---------------------------------


@pytest.mark.parametrize("text", ["x = 6", "x=6", "6 = x", "x = -2.5", "y = 3/4"])
def test_an_equation_already_solved_for_its_variable_is_not_solved_again(text: str) -> None:
    assert extract_math_intent(text) is None


def test_a_list_of_given_values_is_not_a_system_to_solve() -> None:
    assert extract_math_intent("x = 3, y = 1") is None


@pytest.mark.parametrize(
    ("query", "history", "problem"),
    [
        (
            "check my answer: x = 6",
            _history("Solve 4x - 7 = 21", "```answer\nx = 7\n```"),
            "check my work:\n4x - 7 = 21\nx = 6",
        ),
        (
            "x = 6",
            _history("give me a practice problem", "Try this one: solve $4x - 7 = 21$."),
            "check my work:\n4x - 7 = 21\nx = 6",
        ),
        (
            "my answer is x = 6",
            _history(
                "give me a practice problem", "Here's one to try:\n\n**Solve:** $4x - 7 = 21$"
            ),
            "check my work:\n4x - 7 = 21\nx = 6",
        ),
        (
            "is x = 7 right?",
            _history("Solve 4x - 7 = 21", "```answer\nx = 7\n```"),
            "check my work:\n4x - 7 = 21\nx = 7",
        ),
    ],
)
def test_a_claimed_answer_is_checked_against_the_open_problem(
    query: str, history: tuple[tuple[str, str], ...], problem: str
) -> None:
    recent = [{"role": role, "content": text} for role, text in history]
    assert answer_claim_problem(query, recent) == problem


@pytest.mark.parametrize(
    ("query", "history"),
    [
        # No problem open, a different variable, or several equations to choose from.
        ("x = 6", ()),
        ("x = 6", _history("what's the weather like", "Sunny and 24 degrees.")),
        ("y = 6", _history("Solve 4x - 7 = 21", "```answer\nx = 7\n```")),
        ("x = 6", _history("solve x + y = 3 and x - y = 1", "```answer\nx = 2, y = 1\n```")),
        ("x = everything I want in life lol", _history("solve 2x = 4", "```answer\nx = 2\n```")),
    ],
)
def test_a_claim_with_no_single_open_problem_is_not_checked(
    query: str, history: tuple[tuple[str, str], ...]
) -> None:
    recent = [{"role": role, "content": text} for role, text in history]
    assert answer_claim_problem(query, recent) is None


@pytest.mark.asyncio
async def test_a_wrong_claimed_answer_gets_the_right_one(thread_sympy_executor: None) -> None:
    route = await route_case(
        Case(
            "claim",
            "math",
            "check my answer: x = 6",
            Expect(),
            "",
            history=_history("Solve 4x - 7 = 21", "```answer\nx = 7\n```"),
        )
    )
    assert route.solved
    assert "Verified result: x = 7" in route.system_prompt
    assert "Verified result: x = 6" not in route.system_prompt
    assert "does not satisfy" in route.system_prompt


@pytest.mark.asyncio
async def test_a_bare_claim_with_no_problem_is_left_to_the_model(
    thread_sympy_executor: None,
) -> None:
    route = await route_case(Case("bare", "math", "x = 6", Expect(), ""))
    assert not route.solved
    assert "```answer" not in route.instant_text


# --- C. "it" is a pronoun, never i times t --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "simplify it",
        "can you simplify it?",
        "factor it",
        "expand it",
        "now differentiate it",
        "integrate it",
        "now integrate it",
        "differentiate it with respect to x",
    ],
)
def test_it_is_never_read_as_an_expression(text: str) -> None:
    assert extract_math_intent(text) is None
    assert not needs_symbolic_math(text)


@pytest.mark.parametrize(
    ("query", "history", "problem"),
    [
        (
            "simplify it",
            _history("(x^2-1)/(x-1)", "That is a rational expression in x."),
            "simplify (x^2-1)/(x-1)",
        ),
        (
            "factor it",
            _history("what about x^2 - 9", "That is a difference of squares."),
            "factor x^2 - 9",
        ),
        (
            "now integrate it",
            _history("expand (x+1)^2", "```answer\nx^{2} + 2 x + 1\n```"),
            "integrate (x+1)^2",
        ),
        (
            "integrate it",
            _history("what is x^2 + 3x", "It's an expression."),
            "integrate x^2 + 3x",
        ),
        (
            "now differentiate it",
            _history("expand (x+1)^2 + x^2", "```answer\n2 x^{2} + 2 x + 1\n```"),
            "differentiate (x+1)^2 + x^2",
        ),
    ],
)
def test_it_resolves_to_the_expression_in_the_thread(
    query: str, history: tuple[tuple[str, str], ...], problem: str
) -> None:
    recent = [{"role": role, "content": text} for role, text in history]
    assert pronoun_math_problem(query, recent) == problem


@pytest.mark.parametrize(
    ("query", "history"),
    [
        ("simplify it", ()),
        (
            "can you simplify it?",
            _history(
                "Here is my essay intro: The industrial revolution changed everything.",
                "Nice intro! It reads well.",
            ),
        ),
        ("expand it", _history("my business plan has 3 sections", "Sounds good.")),
        ("factor it into the budget", _history("the trip costs $400", "Got it.")),
        ("integrate it into the report", _history("here is a chart of q3 sales", "Looks good.")),
        ("simplify it", _history("solve 2x + 5 = 17", "```answer\nx = 6\n```")),
        # x^3 or its derivative 3x^2? Either reading is a guess.
        ("now integrate it", _history("derivative of x^3", "```answer\n3 x^{2}\n```")),
        ("integrate that", _history("differentiate x^3", "```answer\n3 x^{2}\n```")),
    ],
)
def test_it_with_no_expression_in_the_thread_stays_unresolved(
    query: str, history: tuple[tuple[str, str], ...]
) -> None:
    recent = [{"role": role, "content": text} for role, text in history]
    assert pronoun_math_problem(query, recent) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "history", "result"),
    [
        (
            "simplify it",
            _history("(x^2-1)/(x-1)", "That is a rational expression in x."),
            "Verified result: x + 1",
        ),
        (
            "now integrate it",
            _history("expand (x+1)^2", "```answer\nx^{2} + 2 x + 1\n```"),
            r"Verified result: x \left(\frac{x^{2}}{3} + x + 1\right) + C",
        ),
        (
            "now differentiate it",
            _history("expand (x+1)^2 + x^2", "```answer\n2 x^{2} + 2 x + 1\n```"),
            "Verified result: 4 x + 2",
        ),
    ],
)
async def test_it_in_a_thread_is_solved_from_that_expression(
    query: str,
    history: tuple[tuple[str, str], ...],
    result: str,
    thread_sympy_executor: None,
) -> None:
    route = await route_case(Case("it", "math", query, Expect(), "", history=history))
    assert route.solved
    assert result in route.system_prompt
    assert "i t" not in route.system_prompt


# --- D. the whole percent or arithmetic request, thousands commas included -------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("7.5% of 1,200", "90"),
        ("what is 20% of 1,000", "200"),
        ("15% of 2,500", "375"),
        ("mean of 1,200, 1,500 and 1,800", "1500"),
        ("what is 25% of 80 plus 10", "30"),
        ("what is 25% of 80 minus 5", "15"),
        ("what is 10% of 10% of 500", "5"),
        # A number taken from or added to the percent before it is said: it used to verify 20.
        ("what is obtained by subtracting 5 from 25% of 80", "15"),
        ("subtract 5 from 25% of 80", "15"),
        ("take 5 away from 25% of 80", "15"),
        ("what is 5 less than 25% of 80", "15"),
        ("what is 5 subtracted from 25% of 80", "15"),
        ("add 5 to 25% of 80", "25"),
        # A number alone before the percent is its setting.
        ("in 2024, what was 25% of 80", "20"),
        ("what is 5 more than 25% of 80", "25"),
        ("solve 2x = 1,000", "x = 500"),
        # Unchanged neighbours.
        ("what is 25% of 80", "20"),
        ("7.5% of 1200", "90"),
        ("mode of 2,4,4,5,7,7,7,9", "7"),
        ("1,200 + 800", "2000"),
    ],
)
async def test_a_percent_or_arithmetic_request_is_read_whole(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "what is 15% of 80 plus tax of 8%",
        "what is 20% of 80 and then double it",
        "what is 5 + 20% of 80",
        # Before the percent: an operation with no number, a second term, another number.
        "subtract 25% of 80 from the total",
        "subtract 5 from 25% of 80 plus 10",
        "what is twice 25% of 80",
        "what is 5 times 25% of 80",
        # Not a percent at all, and no other reader takes "from" in either order.
        "subtract 5 from the total",
        "take bus 5 from stop 25 and get off after 2 stops",
    ],
)
async def test_a_percent_request_it_cannot_read_whole_is_not_verified(text: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical is None


@pytest.mark.asyncio
async def test_a_run_that_reads_as_a_list_stays_a_list() -> None:
    # "100,200,300" could be one number or three; the mean of one number is
    # not a question anyone asks, so it stays three values.
    canonical, _reply = await _verified("mean of 100,200,300")
    assert canonical == "200"


# --- E. undefined is undefined, never NaN or complex infinity ---------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    ["what is 0/0", "what is 5/0", "5/0", "what is 1/0", "tan 90°", "log(0)", "ln(0)", "cot 0°"],
)
async def test_a_non_finite_result_is_never_shown_as_an_answer(text: str) -> None:
    canonical, reply = await _verified(text)
    assert canonical in (None, r"\text{undefined}")
    for shown in (canonical or "", reply or ""):
        assert not _NON_FINITE.search(shown)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["what is 5/0", "tan 90°", "log(0)"])
async def test_division_by_zero_says_undefined(text: str) -> None:
    canonical, reply = await _verified(text)
    assert canonical == r"\text{undefined}"
    assert reply is not None and "undefined" in reply


# --- F. pi, several given values, and powers of i ---------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("find the area of a circle with circumference 10π", r"25\pi \approx 78.54"),
        ("find the radius of a circle with circumference 10π", "5"),
        ("area of a circle with circumference 31.4 cm", r"\approx 78.46\ \mathrm{cm}^{2}"),
        ("if x = 3 and y = -2 find x^2 - 2xy + y^2", "25"),
        ("evaluate x^2 - 2xy + y^2 when x = 3 and y = -2", "25"),
        ("if x = 2 find 3x + 1", "7"),
        ("simplify i^23", "- i"),
        ("what is i^23", "- i"),
        ("i^2", "-1"),
    ],
)
async def test_pi_given_values_and_powers_of_i(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


# --- G. "1.8 x 10^-5" is a number --------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Find the pH of 0.10 M CH₃COOH, Ka = 1.8 x 10^-5",
        "whats the ph of 0.10 M acetic acid, Ka = 1.8 x 10^-5",
        "percent ionization of 0.10 M acetic acid, Ka = 1.8 x 10^-5",
        "Ka = 1.8 x 10^-5",
    ],
)
def test_scientific_notation_is_not_an_unknown_x(text: str) -> None:
    assert extract_math_intent(text) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("1.8 x 10^-5 * 2", r"3.6 \cdot 10^{-5}"),
        ("3 x 10^4 + 2 x 10^3", "32000"),
        ("solve 3x + 10 = 4", "x = -2"),
        # Every spelling of the power of ten, with the superscript minus folded first.
        ("1.8·10⁻⁵ divided by 3", r"6.0 \cdot 10^{-6}"),
        ("1.8 × 10⁻⁵ / 3", r"6.0 \cdot 10^{-6}"),
        (r"1.8 \times 10^{-5} / 3", r"6.0 \cdot 10^{-6}"),
    ],
)
async def test_scientific_notation_reads_as_a_number(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


@pytest.mark.asyncio
async def test_scientific_notation_in_words_is_right_or_unverified() -> None:
    canonical, _reply = await _verified("what is 1.8 x 10^-5 times 2")
    assert canonical in (None, r"3.6 \cdot 10^{-5}")


# --- H. check my work grades the answer against the problem ---------------------------


@pytest.mark.parametrize(
    ("lines", "verdicts", "slip_line"),
    [
        (["4x+2=10", "4x=12", "x=2"], ("given", "wrong", "ok"), 2),
        (["2x+4=10", "2x=14", "x=3"], ("given", "wrong", "ok"), 2),
        (["2x+3=11", "2x=14", "x=7"], ("given", "wrong", "carried"), 2),
        (["2x+3=11", "2x=14", "x=6"], ("given", "wrong", "off"), 2),
    ],
)
def test_a_right_final_answer_is_marked_right_after_a_slip(
    lines: list[str], verdicts: tuple[str, ...], slip_line: int
) -> None:
    check = check_work(lines, "x")
    assert check is not None
    assert check.verdicts == verdicts
    assert check.mistake is not None and check.mistake.line == slip_line


def test_the_reply_says_the_answer_is_right_but_names_the_slip() -> None:
    check = check_work(["4x+2=10", "4x=12", "x=2"], "x")
    assert check is not None
    reply = format_work_check_reply(check)
    assert "$x=2$ — \u2713" in reply
    assert "Line 2:" in reply
    assert "final answer is right" in reply


@pytest.mark.asyncio
async def test_a_hint_for_fully_correct_work_says_it_is_right() -> None:
    text = "check my work: 2x+4=10, 2x=6, x=3. Just a hint please"
    _canonical, reply = await _verified(text)
    assert reply is not None
    assert "Every step checks out" in reply
    assert "Identify one reversible operation" not in reply


# --- I. every working line is true ------------------------------------------------------


def _steps(lhs: str, rhs: str, variable: str = "x") -> list[str]:
    left = parse_expression(lhs, [variable, "y"], real=True)
    right = parse_expression(rhs, [variable, "y"], real=True)
    return [step.formula for step in equation_key_steps(left, right, variable)]


def test_a_multi_term_is_subtracted_in_brackets() -> None:
    formulas = _steps("2*x + 3*y + 5", "0")
    assert formulas[0] == r"2 x + 3 y + 5 - \left(3 y + 5\right) = 0 - \left(3 y + 5\right)"


def test_a_negative_term_is_added_not_subtracted_twice() -> None:
    formulas = _steps("2*x - 3*y", "4")
    assert formulas[0] == "2 x - 3 y + 3 y = 4 + 3 y"


def test_every_shown_step_is_a_true_equation() -> None:
    from sympy import Symbol, nsimplify, simplify, solve

    x = Symbol("x", real=True)

    def side(tex: str) -> Any:
        return parse_expression(tex, ["x", "y"], real=True)

    for lhs, rhs in [("2*x + 3*y + 5", "0"), ("0.4*x + 1.2", "2"), ("5 - 3*y - 2*x", "y")]:
        expected = solve(side(lhs) - side(rhs), x)
        for formula in _steps(lhs, rhs):
            left, right = re.sub(r"\\cancel\{([^{}]*)\}", r"\1", formula).split(" = ")
            got = solve(side(left) - side(right), x)
            assert len(got) == len(expected) == 1, formula
            assert simplify(nsimplify(got[0] - expected[0])) == 0, formula


@pytest.mark.asyncio
async def test_a_decimal_equation_ends_on_its_value() -> None:
    canonical, reply = await _verified("solve for x: 0.4x + 1.2 = 2")
    assert canonical == "x = 2"
    assert reply is not None
    assert r"\frac{0.4 x}{0.4} = \frac{0.8}{0.4}$  " + "\n$x = 2$" in reply


# --- J. a maths verb needs a maths object --------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "differentiate between weather and climate",
        "how do I integrate Slack with Notion",
        "factor in the cost of shipping too",
        "expand on that",
        "simplify this paragraph for a 10 year old",
        "simplify my morning routine",
        "x factor auditions near me",
        "factor it into the budget",
        "integrate it into the report",
        "can you expand on your last point",
    ],
)
def test_a_maths_verb_alone_is_not_maths(text: str) -> None:
    assert not needs_symbolic_math(text)


@pytest.mark.parametrize(
    "text",
    [
        "differentiate x^2 sin x",
        "integrate x^2",
        "integrate sin x",
        "factor x^2 + 5x + 6",
        "expand (x+1)(x+2)",
        "simplify 2x + 3x",
        "simplify √50",
        "differentiate y with respect to x",
        "derivative of ln x",
        "integrate e^x",
        "d/dx (x^2 e^x)",
        "∫ x^2 dx",
    ],
)
def test_a_maths_verb_with_a_maths_object_is_maths(text: str) -> None:
    assert needs_symbolic_math(text)


# --- A rounded large value and a claim with no unknown ----------------------------------


def test_a_large_rounded_product_keeps_scientific_notation() -> None:
    from sympy import Float

    from app.modules.math.solve.display import format_verified_latex

    assert format_verified_latex(Float(6.02e23) * 2) != "1203999999999999857393664"
    assert "10^{24}" in format_verified_latex(Float(6.02e23) * 2)
    assert format_verified_latex(Float(2.0)) == "2"


@pytest.mark.parametrize(
    "prompt",
    ["15% of 80 = 12?", "is 15% of 80 = 12?", "50% of 10 = 5", "sqrt(16) = 4?"],
)
def test_a_numeric_claim_is_not_solved_as_an_equation(prompt: str) -> None:
    # It used to get a verified "no solution" or "all real numbers".
    from app.modules.math.tools.extract import extract_math_intent

    intent = extract_math_intent(prompt)
    assert intent is None or intent.kind != "equation"


def test_solve_still_reads_a_contradiction() -> None:
    from app.modules.math.tools.extract import extract_math_intent

    intent = extract_math_intent("solve 0 = 1")
    assert intent is not None and intent.kind == "equation"


# --- K. letters that are not unknowns: units, a defined E, e-notation, subscripts ---------
# The ES-09 capture of every test string found each of these verified wrong. Reading the
# multiplication sign and ``\times`` like the letter x reached two of them more often.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        # A unit after a number is part of a quantity, never letters to solve for.
        "m/q = 1.25 × 10^-6 kg/C",  # C = 1.25·10⁻⁶ gkq/m
        "m/q = 1.25 x 10^-6 kg/C",
        "v = 3 × 10⁸ m/s",  # m = sv/300000000
        "v = 3 x 10^8 m/s",
        "v = 20 m/s",
        "a = 9.8 m/s^2",
        "t = 2.02 s",  # s = 0.495 t
        "m = 16.0 g",
        "T = 300 K",
        "I = 1 A",  # A = i
        "N = 49.1 N",  # N = 0
        "V = 22 L",
        "d = 1.96 g/L",
        "i = 3.92 × 10^-7 A",
        "E = 0.40 V",  # V = e/0.4
        "Find the half-life when k = 0.2 s^-1",
        r"q = 1.6 \times 10^{-19} C, V = 100 V, find the energy",
        "Find the volume of a cube side 3 cm in m3",  # 27 cm³, asked in m³
        # A subscript names one quantity: not P·1, P² or v·0.
        "P2 = 2.0",
        "K2 = 17.5",
        "M1V1 = M2V2",
        "Use Boyle's law: P1 = 2, V1 = 3, V2 = 6, find P2",  # no solution
        "Use Charles's law: V1 = 2 L, T1 = 300, T2 = 600 K, find V2",
        "1234 ÷ 7 = 176 R2",
        "back to the hand: no height, t = 2v0/g",
        "m(O2) = 64 g",
        # A formula asks nothing, and a number past any float is not one a student means.
        "E = mc^2",
        "1e-1000000",
        # Lines of working, chains and alternatives are not one equation or a system.
        r"$c = \sqrt{3^2 + 4^2} = 5$",  # c = s
        r"$d = 4\sqrt{2} = 5.6569$",  # no solution
        "**Answer**\n2x + 3 - 3 = 7 - 3\nx = 3",  # x = 4/3
        "**Given**  \n$2 x + 3 y = 12$  \n$x - y = 1$",
        r"x = 2 \pi k + \frac{\pi}{6} \text{ or } x = 2 \pi k + \frac{5 \pi}{6}",
        r"x < -1 \text{ or } x > 1",  # x < -1
        "```answer\n-2 < x < 2\n```\n",  # x < 2
        "0 < y < 2x",  # no solution
        r"\frac{1}{y}\,dy = 1\,dx",
        r"\frac{2}{3} > \frac{3}{5}",  # all real x
        "Solve over the complex numbers",
        "imaginary",
    ],
)
async def test_letters_that_are_not_unknowns_are_never_solved_for(text: str) -> None:
    canonical, reply = await _verified(text)
    assert canonical is None
    assert reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("E = 2 + 3", "E = 5"),
        # E on its own side is the quantity, not Euler's number: f = e/6.6261·10⁻³⁴ before.
        (r"E = 6.6261 \times 10^{-34} \cdot f", r"f = 1.50918338087261 \cdot 10^{33} E"),
        ("E = 2x + 3", r"x = \frac{E}{2} - \frac{3}{2}"),
        ("E = mc^2, m = 2, c = 3", "E = 18, c = 3, m = 2"),
        (
            r"E = \frac{6.6261 \times 10^{-34} \cdot 3 \times 10^{8}}{5 \times 10^{-7}} + 0.3 - 4186",
            "E = -4185.7",
        ),
        ("1e-5 * 3", r"3.0 \cdot 10^{-5}"),
        ("3e+8/2", "150000000"),
        ("1.5E+3 + 2", "1502"),
        ("simplify 1e999", r"1.0 \cdot 10^{999}"),
        (
            "solve for x: x^2 / (0.10 - x) = 1.8e-5",
            r"x = -0.00135067097307797 \text{ or } x = 0.00133267097307797",
        ),
        ("solve 5x - 7 = 3x + 9. my work: 5x - 3x = 9 - 7, so 2x = 2, so x = 1", "x = 8"),
        # Look-alikes keep their answers.
        ("solve 2m + 3 = 7", "m = 2"),
        ("x2 + 3 = 5", r"x = \pm \sqrt{2}"),
        ("solve x^2 = 9, is it x = 3 or x = -3?", r"x = \pm 3"),
        ("solve 1 < x < 5", "1 < x < 5"),
        ("modulus of 3 + 4i", "5"),
    ],
)
async def test_a_defined_e_and_e_notation_read_as_written(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


# --- L. a mixed number is one number ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Read as 2 * 1/2, these verified x = 4 and x = 10.
        ("solve x + 2 1/2 = 5", r"x = \frac{5}{2}"),
        ("solve 2 1/2 x = 10", "x = 4"),
        ("solve x - 1 3/4 = 2", r"x = \frac{15}{4}"),
        # A power's digit starts no mixed number: x^2 times a half.
        ("solve x^2 1/2 = 8", r"x = \pm 4"),
        # As a glyph or from the maths keyboard: these verified 7/4 and x = 4.
        ("what is 2½ + 1¾", r"\frac{17}{4}"),
        ("solve x + 2½ = 5", r"x = \frac{5}{2}"),
        (r"what is $2\frac{1}{2} + 1\frac{3}{4}$", r"\frac{17}{4}"),
        (r"solve $x + 2\frac{1}{2} = 5$", r"x = \frac{5}{2}"),
        # A coefficient on a fraction with an unknown stays a product.
        (r"solve $2\frac{x}{3} = 4$", "x = 6"),
    ],
)
async def test_a_mixed_number_in_an_equation_is_one_number(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


# --- M. a logarithm is never dropped from its equation -----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        # These verified x = 2 for (x+1) = 3 and x = 1/2 for 2(x+1) = 3; the answer is 7.
        "solve log base 2 of (x+1) = 3",
        "solve log_(2)(x+1)=3",
        "solve log _2(x+1)=3",
    ],
)
async def test_an_equation_without_its_logarithm_is_not_verified(text: str) -> None:
    canonical, reply = await _verified(text)
    assert canonical is None
    assert reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("solve log_2(x+1)=3", "x = 7"),
        ("solve log2(x+1)=3", "x = 7"),
        ("solve log(x) + log(x-3) = 1", "x = 5"),
    ],
)
async def test_a_logarithm_the_reader_keeps_is_still_solved(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


# --- N. a follow-up's own sum is verified like the first -----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # The app's own follow-up under "2½ + 1¾": the model answered it unverified
        # ("3 2/2 = 4").
        ("What if 2½ + 1½ instead?", "4"),
        ("what about 7 × 8?", "56"),
        ("How about 3/4 + 1/8?", r"\frac{7}{8}"),
        ("what if 12 ÷ 4 instead", "3"),
    ],
)
async def test_a_follow_up_sum_is_verified(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "what if I invest 500 at 5%?",
        "what about tomorrow?",
        "how about 5 minutes?",
        "what if 3 instead?",
        "what about the 2 o'clock meeting?",
    ],
)
async def test_a_follow_up_that_is_not_a_sum_is_not_verified(text: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical is None
