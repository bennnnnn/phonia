"""Every worked step names its rule, and typed number work gets its own step."""

import pytest

from app.core.config import Settings
from app.modules.math.solve.key_steps import written_side
from app.modules.math.solve.step_rules import (
    evaluate_powers,
    step_rule,
    with_powers_evaluated,
)
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.parametrize(
    ("label", "rule"),
    [
        ("Subtract 25 from both sides", "Subtraction property of equality"),
        ("Add $3x$ to both sides", "Addition property of equality"),
        ("Divide both sides by 3", "Division property of equality"),
        ("Multiply both sides by -1", "Multiplication property of equality"),
        ("Take the square root of both sides", "Square root property"),
        ("Expand", "Distributive property"),
        ("Set each factor equal to zero", "Zero product property"),
        ("Quadratic formula", "Quadratic formula"),
        ("Evaluate the power", "Exponent"),
        ("Multiply the numbers", "Multiply before adding"),
    ],
)
def test_step_rule_names_the_property_a_move_uses(label: str, rule: str) -> None:
    named = step_rule(label)
    assert named is not None and named.startswith(rule)


@pytest.mark.parametrize("label", ["Simplify", "Solve", "Calculate"])
def test_step_rule_leaves_plain_arithmetic_unnamed(label: str) -> None:
    assert step_rule(label) is None


def test_step_rule_on_an_inequality_is_a_property_of_inequality() -> None:
    assert step_rule("Divide both sides by -3", r"x \le -2") == "Division property of inequality"


def test_evaluate_powers_shows_repeated_multiplication_for_one_power() -> None:
    left = written_side("3x^2 + 5^2", ["x"])
    assert left is not None
    assert evaluate_powers(left[0]) == ("Evaluate the power", r"5^{2} = 5 \cdot 5 = 25")
    plain = written_side("3x^2 + 25", ["x"])
    assert plain is not None and evaluate_powers(plain[0]) is None


def test_evaluate_powers_lists_several_powers_on_one_line() -> None:
    left = written_side("13^2 + x", ["x"])
    right = written_side("3^2", ["x"])
    assert left is not None and right is not None
    assert evaluate_powers(left[0], right[0]) == (
        "Evaluate the powers",
        r"13^{2} = 169,\quad 3^{2} = 9",
    )


def test_with_powers_evaluated_keeps_the_typed_brackets_and_order() -> None:
    side = written_side("2(x+3^2)", ["x"])
    assert side is not None
    assert with_powers_evaluated(side[1], side[0]) == r"2 \left(x + 9\right)"


@pytest.mark.asyncio
async def test_a_typed_power_is_its_own_step_before_the_inverse_moves() -> None:
    query = "3x^2+5^2=25"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    steps = [line for line in reply.splitlines() if line.startswith("**") and ". " in line]
    assert steps[0].startswith("**1. Evaluate the power** — Exponent")
    assert steps[1].startswith("**2. Subtract 25 from both sides** — Subtraction property")
    assert "$3 x^{2} + 25 = 25$" in reply
    assert r"$x = \pm \sqrt{0}$" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "labels"),
    [
        ("2(x+3^2)=24", ["Evaluate the power", "Expand", "Subtract 18 from both sides"]),
        ("x^2+2^3*3=33", ["Evaluate the power", "Multiply the numbers", "Subtract 24"]),
    ],
)
async def test_no_number_work_is_skipped_before_the_inverse_moves(
    query: str, labels: list[str]
) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    for number, label in enumerate(labels, start=1):
        assert f"**{number}. {label}" in reply


async def _lesson(query: str) -> str:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    return reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "solve 3x^2+5^2=25 and check",
        "solve 2(x+3)=14, prove your answer",
        "verify 3x+1=7",
        "x^2-5x+6=0 and verify",
    ],
)
async def test_a_check_step_is_added_only_when_asked(query: str) -> None:
    assert "**Check**" not in await _lesson(
        query.split(" and ")[0].split(",")[0].replace("verify ", "")
    )
    assert "Check** — Substitute back into the original equation" in await _lesson(query)


@pytest.mark.asyncio
async def test_the_check_substitutes_into_the_equation_as_typed() -> None:
    reply = await _lesson("solve 2(x+3)=14 and check")
    assert r"$2 \left(4 + 3\right) = 14$" in reply
    assert r"$14 = 14 \quad \text{(true)}$" in reply
    both = await _lesson("x^2-5x+6=0 and verify")
    assert r"$\text{For } x = 2:$" in both and r"$\text{For } x = 3:$" in both
    assert r"$\left(2\right)^{2} - 5 \left(2\right) + 6 = 0$" in both


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "label"),
    [
        ("show steps log(x)+log(2)=1", "Divide both sides by 2"),
        ("show steps sqrt(x+3)=4", "Subtract 3 from both sides"),
        ("show steps |2x-1|=5", "Add 1 to both sides (second equation)"),
        ("show steps 1/x+1/2=1", "Subtract 2 from both sides"),
    ],
)
async def test_a_reached_equation_is_solved_move_by_move(query: str, label: str) -> None:
    reply = await _lesson(query)
    assert label in reply
    assert "Solve the resulting equation" not in reply
    assert "Solve both linear equations" not in reply
    assert "**2. Calculate**" not in reply


@pytest.mark.parametrize(
    ("label", "formula", "rule"),
    [
        ("Product rule with $u$ and $v$", "", "Product rule"),
        ("Quotient rule with $u$ and $v$", "", "Quotient rule"),
        ("Chain rule with inside $x^2$", "", "Chain rule"),
        ("Power rule on $x^5$", r"\frac{d}{dx} x^5", r"Power rule: $\frac{d}{dx}"),
        ("Power rule on $x^2$", r"\int x^2 \, dx", r"Power rule: $\int"),
        ("Apply integration by parts", "", "Integration by parts"),
        ("Solve equation (1) for x", "", "Isolate one variable"),
        ("Substitute into equation (2)", "", "Substitution method"),
        ("Domain restrictions", "", "Domain"),
    ],
)
def test_step_rule_covers_calculus_systems_and_domains(label: str, formula: str, rule: str) -> None:
    named = step_rule(label, formula)
    assert named is not None and named.startswith(rule)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "solve 2x + 3 = 11; no check",
        "solve 2x+3=11 without checking",
        "skip the verification, 3x=6",
    ],
)
async def test_a_negated_check_request_adds_no_check(query: str) -> None:
    reply = await _lesson(query)
    assert "Check**" not in reply
    assert "```answer" in reply


@pytest.mark.asyncio
async def test_each_absolute_value_branch_ends_at_its_own_root() -> None:
    reply = await _lesson("show steps |2x-1|=5")
    first = reply.split("(first equation)", 1)[1].split("(second equation)", 1)[0]
    second = reply.split("(second equation)")[-1].split("Both solutions", 1)[0]
    assert "x = 3" in first and "x = -2" not in first
    assert "x = -2" in second and "x = 3" not in second
    # The combined roots are their own closing step, matching the answer card.
    assert "Both solutions**" in reply
