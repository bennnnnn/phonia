"""What a broad maths battery found: wrong output, missed questions, and answers without working.

Each row runs the real pre-stream path (subject dispatch, extraction, SymPy,
direct reply) with no model call.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.solve.calculus import integrate_expression
from app.modules.math.solve.inequalities import solve_inequality
from app.services.card_value import split_working
from app.services.subjects.dispatch import build_subject_augmentation, maybe_direct_subject_reply
from app.tests.modules.math.card_support import card_with_working


async def _reply(text: str) -> tuple[str | None, str | None]:
    """(canonical answer, direct reply) for one turn."""
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    augmentation = await build_subject_augmentation(text, settings)
    verified = augmentation.verified
    answer = getattr(verified, "canonical_answer", None) if verified is not None else None
    return answer, maybe_direct_subject_reply(verified, text)


@pytest.mark.parametrize(
    ("integrand", "expected"),
    [
        ("1/x", r"\ln\left|x\right|"),
        ("3/x + 2x", r"x^{2} + 3 \ln\left|x\right|"),
        ("tan(x)", r"- \ln\left|\cos{\left(x \right)}\right|"),
        # Always positive, or a log the integrand already had: no bars.
        ("x/(x^2+1)", r"\frac{\ln{\left(x^{2} + 1 \right)}}{2}"),
        ("ln(x)", r"x \left(\ln{\left(x \right)} - 1\right)"),
    ],
)
def test_an_antiderivative_log_takes_absolute_value_bars(integrand: str, expected: str) -> None:
    assert integrate_expression(integrand).latex == expected


@pytest.mark.parametrize(
    ("lhs", "comparator", "expected"),
    [
        ("x^2 - 4x - 5", "<", "-1 < x < 5"),
        ("x^2 - 1", ">", r"x < -1 \text{ or } x > 1"),
        ("(x-2)^2", ">", r"x \ne 2"),
        ("x^2 + 1", "<", r"\text{no solution}"),
        ("x^2", ">=", r"\text{all real } x"),
    ],
)
def test_an_inequality_answer_is_written_as_a_student_writes_it(
    lhs: str, comparator: str, expected: str
) -> None:
    assert solve_inequality(lhs, "0", "x", comparator).solutions_latex == [expected]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("what is 5!", "5! = 5 × 4 × 3 × 2 × 1 = 120"),
        ("probability of getting exactly 2 heads in 4 coin flips", r"\frac{3}{8} = 0.375"),
        (
            "a fair coin is flipped 6 times. what is the probability of exactly 4 heads?",
            r"\frac{15}{64} = 0.234375",
        ),
        (
            "probability of rolling exactly 2 sixes in 5 rolls of a die",
            r"\frac{625}{3888} \approx 0.1608",
        ),
        ("a right triangle has legs 3 and 4, find the hypotenuse", "5"),
    ],
)
async def test_questions_the_battery_missed_are_answered_directly(text: str, answer: str) -> None:
    canonical, reply = await _reply(text)
    assert canonical is not None and canonical.startswith(answer)
    # The card holds the final answer; working such as 5! expanded goes above it.
    working, _final = split_working(answer)
    assert reply is not None
    assert (answer if working is None else card_with_working(answer, text)) in reply


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["I have 5!", "I got 2 heads in 4 flips"])
async def test_ordinary_sentences_stay_ordinary(text: str) -> None:
    canonical, reply = await _reply(text)
    assert canonical is None and reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("solve ln(x) = 2", ["**2. Convert to exponential form**", "$x = e^{2}$"]),
        (
            "solve 2^(x+1) = 32",
            [
                "**1. Write $32$ as a power of $2$**",
                "$2^{x + 1} = 2^{5}$",
                "**2. Equal bases, so equal exponents**",
                "$x + 1 = 5$",
            ],
        ),
        ("solve e^(2x) = 5", ["**1. Take ln of both sides**", r"$2 x = \ln 5$"]),
        (
            "solve x^3 - 6x^2 + 11x - 6 = 0",
            [
                "**1. Factor the left side**",
                r"$\left(x - 1\right) \left(x - 2\right) \left(x - 3\right) = 0$",
            ],
        ),
        (
            "solve x^2 - 4x - 5 < 0",
            [
                "**3. The parabola opens upward, so it is below zero between the roots**",
                "$-1 < x < 5$",
            ],
        ),
        (
            "integrate x^2 from 0 to 3",
            [
                r"$F(x) = \frac{x^{3}}{3}$ — antiderivative",
                "$= 9 - 0 = 9$ — evaluate at the limits",
            ],
        ),
        (
            "integrate sin(x) from 0 to pi",
            [r"$= 1 - \left(-1\right) = 2$ — evaluate at the limits"],
        ),
        (
            "distance between (1, 2) and (4, 6)",
            [r"$= \sqrt{3^2 + 4^2} = \sqrt{25} = 5$"],
        ),
        (
            "slope of the line through (1, 2) and (3, 8)",
            [r"$m = \frac{8 - 2}{3 - 1} = \frac{6}{2} = 3$"],
        ),
        (
            "limit of (x^2 - 1)/(x - 1) as x approaches 1",
            [r"$\lim_{x \to 1} \left(x + 1\right) = 2$ — substitute $x = 1$"],
        ),
        ("limit of sin(x)/x as x approaches 0", ["L'Hôpital's rule"]),
        (
            "integrate sin(x)cos(x)",
            [r"Let $u = \sin{\left(x \right)}$", r"\frac{\sin^{2}{\left(x \right)}}{2} + C"],
        ),
    ],
)
async def test_answers_that_were_bare_now_show_their_working(text: str, lines: list[str]) -> None:
    _, reply = await _reply(text)
    assert reply is not None
    for line in lines:
        assert line in reply


@pytest.mark.asyncio
async def test_a_radical_domain_lists_only_conditions_on_the_unknown() -> None:
    _, reply = await _reply("solve sqrt(x + 3) = 4")
    assert reply is not None
    assert "**1. Domain restrictions**" in reply
    assert r"$x + 3 \ge 0$" in reply
    assert r"4 \ge 0" not in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Find the distance between (0,0) and (3,4) and explain the formula",
        "probability of getting exactly 2 heads in 4 coin flips and explain why",
    ],
)
async def test_an_extra_ask_still_reaches_the_model(text: str) -> None:
    _, reply = await _reply(text)
    assert reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "working", "answer"),
    [
        ("What is the value of 6!/4!?", r"$\frac{6!}{4!} = \frac{720}{24}$", "30"),
        ("calculate 10!/8!", r"$\frac{10!}{8!} = \frac{3628800}{40320}$", "90"),
        ("what is 8!/(3!5!)", r"$\frac{8!}{3!\,5!} = \frac{40320}{6 \times 120}$", "56"),
        ("5! + 3!", "$5! + 3! = 120 + 6$", "126"),
        # Too long to write out: the quotient cancels instead.
        ("what is 100!/98!", r"$\frac{100!}{98!} = 100 \times 99$", "9900"),
    ],
)
async def test_factorial_arithmetic_writes_the_expression_once(
    text: str, working: str, answer: str
) -> None:
    canonical, reply = await _reply(text)
    assert canonical == answer
    assert reply == f"{working}\n\n```answer\n{answer}\n```\n"


@pytest.mark.parametrize(
    ("text", "expr"),
    [
        ("What is the value of 6!/4!?", "6!/4!"),
        ("what is 2+2!", "2+2"),  # one closing ! is still punctuation
        ("5!!", None),
        ("what is 6!!/2", None),
        ("what is 171!/170!", None),
        ("what is (2+3)! + 1", None),
        ("what is 2.5!", None),
    ],
)
def test_bare_arithmetic_reads_factorials(text: str, expr: str | None) -> None:
    from app.modules.math.match import bare_arithmetic_expr

    assert bare_arithmetic_expr(text) == expr


@pytest.mark.parametrize(
    ("expr", "tex"),
    [
        ("5!/3!/2!", r"\frac{5!}{3!} \div 2! = \frac{120}{6} \div 2"),
        ("2(3!)", r"2\,\left(3!\right) = 2 \times \left(6\right)"),
        ("20!+1", None),
        ("6/4", None),
        ("6!^2", None),
    ],
)
def test_factorial_working_line(expr: str, tex: str | None) -> None:
    from app.modules.math.solve.factorial_working import factorial_working

    working = factorial_working(expr)
    assert (working.tex if working is not None else None) == tex


# A second battery: wrong answers it found, and the working that replaced them.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "working", "answer"),
    [
        # Read as 2*1/2 + 1*3/4 = 7/4 and shown as "21 ÷ 2 + 13 ÷ 4".
        (
            "2 1/2 + 1 3/4",
            r"$2\frac{1}{2} + 1\frac{3}{4} = \frac{5}{2} + \frac{7}{4} = \frac{10}{4} + \frac{7}{4}$",
            r"\frac{17}{4} = 4\frac{1}{4}",
        ),
        (
            "1 1/2 divided by 3/4",
            r"$1\frac{1}{2} \div \frac{3}{4} = \frac{3}{2} \div \frac{3}{4} = \frac{3}{2} \times \frac{4}{3}$",
            "2",
        ),
        (
            "3/4 divided by 2/5",
            r"$\frac{3}{4} \div \frac{2}{5} = \frac{3}{4} \times \frac{5}{2}$",
            r"\frac{15}{8}",
        ),
        ("what is 2/3 of 60", r"$\frac{2}{3} \times 60 = \frac{2 \times 60}{3}$", "40"),
        # Solved for "f" as if f(x) meant f times x.
        (
            "if f(x) = 2x^2 - 3, find f(4)",
            r"$f(4) = 2 \left(4\right)^{2} - 3 = 32 - 3$",
            "29",
        ),
        (
            "if f(x) = x + 1 and g(x) = x^2, find f(g(2))",
            "$g(2) = \\left(2\\right)^{2} = 4$  \n$f(g(2)) = f(4) = 4 + 1$",
            "5",
        ),
        # Answered "x = 4".
        (
            "evaluate 2x^2 - 3 when x = 4",
            r"$2 x^{2} - 3 = 2 \left(4\right)^{2} - 3 = 32 - 3$",
            "29",
        ),
        (
            "find the derivative of x^2 at x = 3",
            "$\\frac{dy}{dx} = 2 x$  \n$\\left.\\frac{dy}{dx}\\right|_{x = 3} = 2 \\left(3\\right)$",
            "6",
        ),
    ],
)
async def test_battery_two_writes_the_working_once_then_the_answer(
    text: str, working: str, answer: str
) -> None:
    canonical, reply = await _reply(text)
    assert canonical == answer
    assert reply == f"{working}\n\n```answer\n{answer}\n```\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # 20% off 48 (38.4) answers a different question: the 48 is already reduced.
        ("after a 20% discount a shirt costs 48, what was the original price", "60"),
        ("the sale price is 60 after 25% off. find the original price", "80"),
        ("after a 15% increase the price is 230, what was the original price", "200"),
        ("a jacket costs 80 with a 25% discount, what is the sale price", "60"),
        ("what is the percentage increase from 40 to 50", "25"),
        # Read as 0 to 360 radians: about 115 answers.
        ("solve 2sin(x) = 1 for 0 <= x <= 360", r"x = 30^\circ,\;150^\circ"),
        ("solve cos(x) = -0.5 for -180 <= x <= 180", r"x = -120^\circ,\;120^\circ"),
        ("solve sin(x) = 0.3 for 0 <= x <= 360", r"x \approx 17.46^\circ,\;162.54^\circ"),
        # Answered with the point of contact, (3, 9).
        ("find the equation of the tangent to y = x^2 at x = 3", "y = 6 x - 9"),
        (
            "find the equation of the normal to y = x^2 at x = 1",
            r"y = - \frac{1}{2} x + \frac{3}{2}",
        ),
        # Solved the curve for x in terms of y.
        (
            "find the stationary points of y = x^3 - 3x",
            r"\left(-1, 2\right)\ \text{maximum},\; \left(1, -2\right)\ \text{minimum}",
        ),
        ("find the stationary points of y = x^3", r"\left(0, 0\right)\ \text{point of inflection}"),
        # The first derivative's value (32) was given for the second.
        ("Find the second derivative of x^4 at x=2", "48"),
        ("f(x) = x^2, find f'(3)", "6"),
        ("differentiate (x^2 + 1)/(x - 1)", r"\frac{x^{2} - 2 x - 1}{\left(x - 1\right)^{2}}"),
        ("2.5 * 4.2", "10.5"),
    ],
)
async def test_battery_two_answers_are_right(text: str, answer: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "f(x) = 2x + 3",
        "f(x) = 2x + 3, find f(4) and explain the graph",
        "solve f(x) = 0 where f(x) = x^2 - 4",
    ],
)
async def test_function_notation_is_never_solved_for_the_function_name(text: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical is None or "f" not in canonical


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "unit"),
    [("a car travels 150 km in 2.5 hours, what is its average speed", r"\mathrm{km/h}")],
)
async def test_a_speed_unit_is_written_in_symbols(text: str, unit: str) -> None:
    _, reply = await _reply(text)
    assert reply is not None and unit in reply and "hours" not in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "rows"),
    [
        ("perimeter of a rectangle 8 by 5", [r"$l = 8\,\mathrm{units}$", r"$P = 2(8 + 5) = 26$"]),
        (
            "circumference of a circle with diameter 10",
            ["**Circle circumference formula**  \n$C = \\pi d$"],
        ),
        ("area of a circle with diameter 10", ["**Circle area formula**  \n$A = \\pi r^2$"]),
        (
            "solve sin(x) = 0 for 0 <= x <= 360",
            [r"$x = 180^\circ k$ — substitute the angle", r"$0^\circ \le x \le 360^\circ$"],
        ),
    ],
)
async def test_battery_two_layout_slips(text: str, rows: list[str]) -> None:
    _, reply = await _reply(text)
    assert reply is not None
    for row in rows:
        assert row in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Each went to the model unverified, or was claimed by the wrong subject.
        ("find the 6th term of the geometric sequence 2, 6, 18", "486"),
        ("sum of the first 5 terms of the geometric series 3, 6, 12", "93"),
        ("magnitude of the vector (3, 4)", "5"),
        ("dot product of (1, 2, 3) and (4, 5, 6)", "32"),
        ("(2 + 3i)(1 - i)", "5 + i"),
        ("how many ways can 5 people sit in a row", "5! = 5 × 4 × 3 × 2 × 1 = 120"),
        ("in how many ways can a committee of 3 be chosen from 10 people", "120"),
        ("how many ways can 3 of 7 runners finish first, second and third", "210"),
        ("probability of rolling a sum of 7 with two dice", r"\frac{1}{6} \approx 0.1667"),
        ("probability of drawing a king from a standard deck", r"\frac{1}{13} \approx 0.07692"),
        ("probability of drawing a heart from a deck of cards", r"\frac{1}{4} = 0.25"),
        ("a right triangle has hypotenuse 13 and one leg 5, find the other leg", "12"),
        ("sum of interior angles of a hexagon", r"720^\circ"),
        ("find each interior angle of a regular octagon", r"135^\circ"),
        ("what is each exterior angle of a regular pentagon", r"72^\circ"),
        ("area under y = x^2 between x = 1 and x = 2", r"\frac{7}{3}"),
        ("area under y=x^2 from 0 to 1", r"\frac{1}{3}"),
        ("find the area under the curve y = 3x^2 + 1 from x = 0 to x = 2", "10"),
        ("cube root of 27", "3"),
        ("square root of 50", r"5\sqrt{2} \approx 7.071"),
        ("convert 3/8 to a percentage", r"37.5\%"),
        ("what is 2/3 as a percentage", r"\frac{200}{3}\% \approx 66.67\%"),
        ("write 0.00045 in standard form", r"4.5 \times 10^{-4}"),
        ("sum of the first 20 natural numbers", "210"),
        ("complete the square x^2 + 6x + 5", r"\left(x + 3\right)^{2} - 4"),
        ("complete the square 2x^2 + 8x + 3", r"2\left(x + 2\right)^{2} - 5"),
        ("in triangle ABC, a = 7, b = 9, C = 60 degrees, find c", r"\sqrt{67} \approx 8.185"),
    ],
)
async def test_battery_two_gaps_are_verified(text: str, answer: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "working"),
    [
        ("5C2", r"${}^{5}C_{2} = \frac{5!}{2!\,3!} = \frac{5 \times 4}{2 \times 1}$"),
        ("7P3", r"${}^{7}P_{3} = \frac{7!}{4!} = 7 \times 6 \times 5$"),
        ("magnitude of the vector (3, 4)", r"$|\vec{v}| = \sqrt{3^2 + 4^2} = \sqrt{25}$"),
        (
            "(2 + 3i)(1 - i)",
            r"$(2 + 3i)(1 - i) = 2 - 2i + 3i - 3i^{2} = 2 + i + 3$ — using $i^2 = -1$",
        ),
        (
            "probability of rolling a sum of 7 with two dice",
            r"$P = \frac{6}{36}$ — favourable over all outcomes",
        ),
        (
            "write 0.00045 in standard form",
            r"$0.00045 = 4.5 \times 10^{-4}$ — move the decimal point 4 places right",
        ),
    ],
)
async def test_battery_two_gaps_show_their_working(text: str, working: str) -> None:
    _, reply = await _reply(text)
    assert reply is not None and working in reply


@pytest.mark.parametrize(
    "text",
    [
        "I have 5 people coming over",
        "the first 5 terms are fine",
        "how many ways are there to say hello",
    ],
)
def test_ordinary_sentences_are_not_counting_questions(text: str) -> None:
    from app.modules.math.match.discrete import combinatorics_signal

    assert combinatorics_signal(text) is None


def test_rms_is_a_word_not_the_end_of_terms() -> None:
    from app.modules.physics.extract import needs_physics

    assert not needs_physics("sum of the first 5 terms of the geometric series 3, 6, 12")
    assert needs_physics("what is the rms voltage of a 170 V peak supply")


# A third battery, geometry and calculus.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Wrong before: a whole circle, a radius of 31.4, no answer, all three angles.
        ("area of a semicircle with radius 4", r"8\pi \approx 25.13"),
        ("find the radius of a circle with circumference 31.4", r"\approx 5.00"),
        ("diagonal of a cube with side 2", r"2\sqrt{3} \approx 3.46"),
        ("a triangle has sides 7, 8 and 9, find the largest angle", r"\approx 73.4^\circ"),
        (
            "find the center and radius of x^2 + y^2 - 4x + 6y - 3 = 0",
            r"\text{centre } (2, -3),\ r = 4",
        ),
        # Gaps before.
        ("area of a square with diagonal 10", "50"),
        ("area of a rhombus with diagonals 6 and 8", "24"),
        ("find the circumference of a circle with area 50", r"\approx 25.07"),
        ("area of an equilateral triangle with side 6", r"9\sqrt{3} \approx 15.59"),
        ("volume of a hemisphere with radius 3", r"18\pi \approx 56.55"),
        ("two angles of a triangle are 50 and 60 degrees, find the third angle", r"70^\circ"),
        ("an isosceles triangle has a base angle of 70 degrees, find the apex angle", r"40^\circ"),
        ("find the supplement of 35 degrees", r"145^\circ"),
        (
            "how many sides does a regular polygon have if each interior angle is 140 degrees",
            "9",
        ),
        ("in triangle ABC, A = 40 degrees, B = 60 degrees, a = 10, find b", r"\approx 13.47"),
        (
            "in a right triangle the opposite side is 5 and the hypotenuse is 10, find the angle",
            r"30^\circ",
        ),
        (
            "a right triangle has an angle of 30 degrees and hypotenuse 12, find the opposite side",
            "6",
        ),
        (
            "a 10 m ladder leans against a wall with its foot 6 m from the wall, "
            "how high up the wall does it reach",
            r"8\ \mathrm{m}",
        ),
        (
            "equation of a circle with center (2, -3) and radius 4",
            r"\left(x - 2\right)^2 + \left(y + 3\right)^2 = 16",
        ),
        ("gradient of a line perpendicular to y = 2x + 1", r"- \frac{1}{2}"),
        ("equation of the perpendicular bisector of (1, 2) and (5, 6)", "y = -x + 7"),
        ("area of a triangle with vertices (0, 0), (4, 0) and (0, 3)", "6"),
    ],
)
async def test_battery_three_geometry(text: str, answer: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


# "°" is not a word character, so an angle that ended in "°" never met the word boundary
# after it: the supplement of 35° had no reading, and the complement of 28° was read as a
# probability and declined. A probability complement keeps its own reading.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("find the supplement of 35°", r"145^\circ"),
        ("What is the complement of 28°?", r"62^\circ"),
        ("the complementary angle to 28 °", r"62^\circ"),
        ("find the complement of 28° angle", r"62^\circ"),
        ("find the supplement of 35° please", r"145^\circ"),
        ("Find the supplement of 35 degrees and explain why", r"145^\circ"),
        ("Find the complement of 28 degrees step by step", r"62^\circ"),
        ("supplement of 35.5°.", r"144.5^\circ"),
        ("find the complement of 28 degrees", r"62^\circ"),
        ("complement of 0.3", "0.7"),
        ("find the complement of event A if P(A) = 0.3", "0.7"),
    ],
)
async def test_an_angle_with_a_degree_sign_is_read(text: str, answer: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Wrong before: the point (2, 8), the meeting points, "o p t u" in the series.
        ("find the gradient of the curve y = x^3 at x = 2", "12"),
        ("find the area enclosed by y = x^2 and y = 4", r"\frac{32}{3}"),
        ("area between y = x and y = x^2", r"\frac{1}{6}"),
        ("find the taylor series of e^x up to x^3", r"1 + x + \frac{x^{2}}{2} + \frac{x^{3}}{6}"),
        (
            "maclaurin series of cos(x) to 4 terms",
            r"1 - \frac{x^{2}}{2} + \frac{x^{4}}{24} - \frac{x^{6}}{720}",
        ),
        ("volume of revolution of y = x from 0 to 2 about the x-axis", r"\frac{8 \pi}{3}"),
        # Gaps before.
        ("find dy/dx if x^2 + y^2 = 25", r"- \frac{x}{y}"),
        ("where is f(x) = x^3 - 3x increasing", r"x < -1 \text{ or } x > 1"),
        ("find the point of inflection of y = x^3 - 6x^2", r"\left(2, -16\right)"),
        ("average value of x^2 on [0, 3]", "3"),
        ("two numbers add to 20, find the maximum product", "100"),
        ("a ball's height is h = 20t - 5t^2, find the maximum height", "20"),
        ("solve dy/dx = 2x with y(0) = 1", "y = x^{2} + 1"),
        # Display: e - 1, arctan.
        ("integrate e^x from 0 to 1", "e - 1"),
        ("integrate 1/(x^2 + 1)", r"\arctan{\left(x \right)} + C"),
    ],
)
async def test_battery_three_calculus(text: str, answer: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "row"),
    [
        # Maths numbers each move: the rule is the step, its working the line under it.
        (
            "integrate x^3",
            "**1. Power rule on $x^{3}$** — Power rule: "
            "$\\int x^n \\, dx = \\frac{x^{n+1}}{n+1} + C$  \n"
            "$\\int x^{3}\\,dx = \\frac{x^{3 + 1}}{3 + 1}$",
        ),
        (
            "limit of (3x^2 + 1)/(x^2 - 2) as x approaches infinity",
            r"$= \frac{3 + 0}{1 - 0}$",
        ),
        ("integrate e^x from 0 to 1", "$= e - 1$ — evaluate at the limits"),
        (
            "solve dy/dx = 2x with y(0) = 1",
            r"$y(0) = \left(0\right)^{2} + C = 1 \Rightarrow C = 1$ — use the initial value",
        ),
        ("surface area of a cube with side 3", "Cube surface area"),
    ],
)
async def test_battery_three_working(text: str, row: str) -> None:
    _, reply = await _reply(text)
    assert reply is not None and row in reply


@pytest.mark.parametrize(
    "text",
    [
        "complement of 0.3",
        "the radius of the earth is 6371 km",
        "complement of event A",
        "P(A') if P(A) = 0.3",
        # A temperature, not an angle: the degree sign once met a boundary before the letter.
        "complement of 28°F",
        "the supplement of 35°C",
        # A noun after the angle: no angle question ("28 degrees weather" was 62°).
        "What drink is a good complement to 35° weather?",
        "What snack is a good complement to 28 degrees weather at the beach?",
        "A crisp white wine is the perfect complement to 30° days",
        "What's a light lunch that's a good supplement for 35° summer days?",
    ],
)
def test_geometry_measures_leave_other_questions_alone(text: str) -> None:
    from app.modules.math.tools.school.geometry_measures import extract_geometry_measure_intent

    assert extract_geometry_measure_intent(text) is None


# A letter beside x and y leaves no numeric centre or radius. "= z" compared z with 0,
# which raised a TypeError no solver catches, and the turn was logged as a failure.
@pytest.mark.parametrize(
    "text",
    [
        "Centre and radius of the circle y^2 + x^2 = z.",
        "centre and radius of x^2 + y^2 = r^2",
        "center and radius of x^2 + y^2 + z = 4",
        "find the centre and radius of x^2 + y^2 + 2kx = 4 - k^2",
        "centre and radius of the circle x^2 + y^2 = I",
    ],
)
def test_a_circle_without_a_numeric_radius_declines_quietly(
    text: str, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    from app.modules.math.tools.block import _build_verified_block
    from app.modules.math.tools.extract import extract_math_intent

    intent = extract_math_intent(text)
    assert intent is not None
    assert intent.school_op == "geometry_measure:circle_centre_radius"
    with caplog.at_level(logging.WARNING):
        assert _build_verified_block(intent, Settings(math_tools_enabled=True)) is None
    assert [record.getMessage() for record in caplog.records] == []


# The triangle laws, computed once (ES-10). The two-sides-and-an-angle cosine rule knew exact
# cosines only from a hand table of 60°, 120° and 90°; SymPy knows 30°, 45° and 150° too.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Pinned before the move.
        ("in triangle ABC, a = 6, b = 10, C = 72 degrees, find c", "9.946"),
        ("in triangle ABC, a = 3, b = 4, C = 90 degrees, find c", "5"),
        ("a triangle has sides 7, 8 and 9, find the smallest angle", r"\approx 48.2^\circ"),
        ("area of a triangle with sides 5, 6 and 7", "14.6969"),
        (
            "find the angles of a triangle with sides 5, 6 and 7",
            r"\approx 44.4°, \approx 57.1°, \approx 78.5°",
        ),
        ("draw a triangle with angles 120, 40 and 20", "120°, 40°, 20°"),
        # Decimals before: exact surds now.
        (
            "in triangle ABC, a = 5, b = 8, C = 30 degrees, find c",
            r"\sqrt{89 - 40 \sqrt{3}} \approx 4.44",
        ),
        (
            "in triangle ABC, a = 4, b = 6, C = 45 degrees, find c",
            r"\sqrt{52 - 24 \sqrt{2}} \approx 4.25",
        ),
        (
            "in triangle ABC, a = 3, b = 5, C = 150 degrees, find c",
            r"\sqrt{34 + 15 \sqrt{3}} \approx 7.745",
        ),
        (
            "in triangle ABC, b = 4, c = 6, A = 135 degrees, find a",
            r"\sqrt{52 + 24 \sqrt{2}} \approx 9.27",
        ),
        # \sqrt{75} and \sqrt{8} before: the surd is simplified.
        ("in triangle ABC, a = 5, b = 5, C = 120 degrees, find c", r"5 \sqrt{3} \approx 8.66"),
        ("in triangle ABC, a = 2, b = 2, C = 90 degrees, find c", r"2 \sqrt{2} \approx 2.828"),
        # "\approx" before an exact angle or side.
        ("a triangle has sides 3, 5 and 7, find the largest angle", r"120^\circ"),
        ("a triangle has sides 3, 4 and 5, find the largest angle", r"90^\circ"),
        ("in triangle ABC, A = 30 degrees, B = 90 degrees, a = 5, find b", "10"),
        (
            "in triangle ABC, A = 45 degrees, B = 30 degrees, a = 8, find b",
            r"4\sqrt{2} \approx 5.66",
        ),
    ],
)
async def test_triangle_laws_answer(text: str, answer: str) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # No answer before: the readers matched a lowercase "find" only.
        (
            "In triangle ABC, a = 5 cm, b = 8 cm and angle C = 30°. Find c.",
            r"\sqrt{89 - 40 \sqrt{3}} \approx 4.44",
        ),
        (
            "In triangle ABC, a = 7, b = 9 and C = 60°. Calculate the length of c.",
            r"\sqrt{67} \approx 8.185",
        ),
        ("In triangle ABC, a = 7, b = 9 and C = 60°. Determine c.", r"\sqrt{67} \approx 8.185"),
        ("In triangle ABC, A = 40°, B = 60° and a = 10. Find b.", r"\approx 13.47"),
        (
            "In triangle ABC, A = 40°, B = 60° and a = 10. Calculate the length of side b.",
            r"\approx 13.47",
        ),
        # B is the angle given, not the side b: still no answer.
        ("In triangle ABC, a = 10, A = 40° and B = 60°. Find B.", None),
    ],
)
async def test_triangle_laws_read_a_capitalised_verb(text: str, answer: str | None) -> None:
    canonical, _ = await _reply(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "row"),
    [
        ("in triangle ABC, a = 7, b = 9, C = 60 degrees, find c", "$c^2 = 49 + 81 - 63 = 67$"),
        # Was "9 + 16 - 1.46958e-15": cos 90° read from the float, not the table.
        ("in triangle ABC, a = 3, b = 4, C = 90 degrees, find c", "$c^2 = 9 + 16 - 0 = 25$"),
        (
            "in triangle ABC, a = 5, b = 8, C = 30 degrees, find c",
            r"$c^2 = 25 + 64 - 40 \sqrt{3} = 89 - 40 \sqrt{3}$",
        ),
        # Was "9 + 25 - -25.9808": an obtuse angle's negative cosine adds.
        (
            "in triangle ABC, a = 3, b = 5, C = 150 degrees, find c",
            r"$c^2 = 9 + 25 + 15 \sqrt{3} = 34 + 15 \sqrt{3}$",
        ),
        ("in triangle ABC, a = 3, b = 5, C = 100 degrees, find c", "$c^2 = 9 + 25 + 5.20945"),
        # Was -68/175: the float's nearest small fraction, written as if exact.
        (
            "a triangle has sides 2.31, 3.77 and 5.13, find the largest angle",
            r"$C = \cos^{-1}\left(\frac{-67679}{174174}\right)$",
        ),
    ],
)
async def test_triangle_laws_working(text: str, row: str) -> None:
    _, reply = await _reply(text)
    assert reply is not None and row in reply


@pytest.mark.asyncio
async def test_triangle_laws_decline_impossible_sides() -> None:
    canonical, _ = await _reply("a triangle has sides 1, 1 and 10, find the largest angle")
    assert canonical is None
