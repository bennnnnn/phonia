""" "What if the coefficient was 2?" rebuilds the last equation for the verified solver."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.modules.math.followup import restated_math_problem
from app.modules.math.followup_what_if import is_part_change
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation


def _history(prior: str) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(role="user", content=prior),
        SimpleNamespace(role="assistant", content="x = ..."),
    ]


@pytest.mark.parametrize(
    ("query", "prior", "rebuilt"),
    [
        ("What if coefficient was 2?", "3x+5=0", "2x + 5 = 0"),
        ("what if the coefficient of x was 4", "3x+5=0", "4x + 5 = 0"),
        ("what if the constant was 7", "3x+5=0", "3x + 7 = 0"),
        ("what if the right side was 10", "3x+5=0", "3x + 5 = 10"),
        ("what if it was 5?", "3x+3=3", "3x + 3 = 5"),
        ("what if it equalled 9", "2x+1=5", "2x + 1 = 9"),
        # A whole new equation is still a restatement.
        ("what if it was 2x + 5 = 21?", "3x+5=0", "2x + 5 = 21"),
    ],
)
def test_a_part_change_rebuilds_the_last_equation(query: str, prior: str, rebuilt: str) -> None:
    assert restated_math_problem(query, _history(prior)) == rebuilt


@pytest.mark.parametrize(
    ("query", "prior"),
    [
        # A quadratic has two coefficients; "the coefficient" does not say which.
        ("what if the coefficient was 2", "x^2-5x+6=0"),
        # No y in the equation.
        ("what if the coefficient of y was 2", "3x+5=0"),
        # No equation before it.
        ("What if coefficient was 2?", "what is the capital of france"),
    ],
)
def test_a_part_change_with_nothing_to_change_is_left_alone(query: str, prior: str) -> None:
    assert restated_math_problem(query, _history(prior)) is None


@pytest.mark.asyncio
async def test_the_rebuilt_equation_gets_the_verified_lesson() -> None:
    query = "What if coefficient was 2?"
    assert is_part_change(query)
    problem = restated_math_problem(query, _history("3x+5=0"))
    assert problem is not None
    _, verified = await build_math_augmentation(problem, Settings(math_tools_enabled=True))
    reply = maybe_direct_math_reply(verified, query, verified_request_text=problem)
    assert reply is not None
    assert "**1. Subtract 5 from both sides** — Subtraction property of equality" in reply
    assert reply.count("```answer") == 1


# Live (2026-10-29): the follow-up chip "What if I convert 10 miles instead?" after
# "convert 5 miles to km" went to the model and came back as a bare "Answer:" line.
@pytest.mark.parametrize(
    ("query", "rebuilt"),
    [
        ("What if I convert 10 miles instead?", "convert 10 miles to km"),
        ("what about 10 miles?", "convert 10 miles to km"),
        ("and 12 miles", "convert 12 miles to km"),
    ],
)
def test_a_new_amount_of_the_problems_unit_is_the_same_problem(query: str, rebuilt: str) -> None:
    assert restated_math_problem(query, _history("convert 5 miles to km")) == rebuilt


@pytest.mark.parametrize(
    "query",
    [
        # A unit the problem has no amount of, or none it has at all.
        "how about 3 km",
        "what about 10 kg?",
        "What if I had 10 friends?",
    ],
)
def test_an_amount_the_problem_does_not_have_is_left_alone(query: str) -> None:
    assert restated_math_problem(query, _history("convert 5 miles to km")) is None


@pytest.mark.parametrize(
    ("query", "prior", "rebuilt"),
    [
        # The whole quantity is replaced, its sign included.
        (
            "what about 10 celsius",
            "convert -5 celsius to fahrenheit",
            "convert 10 celsius to fahrenheit",
        ),
        (
            "what about -10 celsius",
            "convert 5 celsius to fahrenheit",
            "convert -10 celsius to fahrenheit",
        ),
        # The same unit written another way.
        ("what about 3 feet", "convert 5 ft to m", "convert 3 feet to m"),
        ("what about 3 inches", "convert 5 inch to cm", "convert 3 inches to cm"),
        ("what about 3 hours", "convert 5 hr to minutes", "convert 3 hours to minutes"),
    ],
)
def test_the_whole_amount_is_replaced_in_any_spelling_of_its_unit(
    query: str, prior: str, rebuilt: str
) -> None:
    assert restated_math_problem(query, _history(prior)) == rebuilt


# Review (2026-10-29): each of these was rewritten into a different problem the solver
# then verified ("-5" read as "5" kept its minus, "1/2" became "1/3").
@pytest.mark.parametrize(
    ("query", "prior"),
    [
        ("what about 3 miles", "convert 1/2 mile to feet"),
        ("what about 3 miles", "convert 5 1/2 miles to km"),
        ("what about 5 miles", "convert 1,000 miles to km"),
        ("what about negative 10 celsius", "convert 5 celsius to fahrenheit"),
        ("and another 3 apples", "I have 5 apples and eat 2. How many are left?"),
        ("and not 10 miles", "convert 5 miles to km"),
        ("what about 3 ms", "convert 5 m to cm"),
        ("what about 3 m", "convert 5 ms to s"),
        ("what about 3 mb", "convert 5 MB to KB"),
        ("what about 10 m", "convert 5 m/s to km/h"),
    ],
)
def test_a_line_that_is_not_just_a_new_amount_of_the_same_unit_is_left_alone(
    query: str, prior: str
) -> None:
    assert restated_math_problem(query, _history(prior)) is None
