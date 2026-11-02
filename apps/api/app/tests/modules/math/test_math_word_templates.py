"""Classic word problems read without a model, and anything else left to the translator."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools.prompt import build_math_augmentation, needs_symbolic_math
from app.modules.math.tools.school.arithmetic import _extract_arithmetic_intent
from app.modules.math.tools.school.interest import _extract_interest_intent
from app.modules.math.tools.school.shopping import extract_change_intent
from app.modules.math.tools.word_templates import word_template_setup


@pytest.mark.parametrize(
    ("text", "equations", "targets"),
    [
        (
            "the sum of three consecutive integers is 72. find them",
            ["n + (n + 1) + (n + 2) = 72"],
            ["n", "n + 1", "n + 2"],
        ),
        (
            "Find three consecutive even integers whose sum is 78",
            ["n + (n + 2) + (n + 4) = 78"],
            ["n", "n + 2", "n + 4"],
        ),
        (
            "two consecutive odd integers add up to 56. what is the largest one?",
            ["n + (n + 2) = 56"],
            ["n + 2"],
        ),
        (
            "Sam is 4 years older than Ana. the sum of their ages is 30. how old is Ana",
            ["s = a + 4", "s + a = 30"],
            ["a"],
        ),
        (
            "Tom is 6 years younger than Lily and their ages add up to 40. how old are they?",
            ["t = l - 6", "t + l = 40"],
            ["t", "l"],
        ),
        (
            "tickets cost $8 for adults and $5 for kids. 40 tickets were sold for $260. "
            "how many adult tickets",
            ["a + c = 40", "8*a + 5*c = 260"],
            ["a"],
        ),
        (
            "how many liters of 20% acid solution must be mixed with 10 L of 50% solution to "
            "get a 30% solution",
            ["0.2*x + 0.5*10 = 0.3*(x + 10)"],
            ["x"],
        ),
        (
            "A recipe needs 3 cups of flour for 12 cookies. How many cups for 30 cookies?",
            ["x/30 = 3/12"],
            ["x"],
        ),
        (
            "a recipe uses 2 cups of flour for 12 cookies. how much flour for 30 cookies",
            ["x/30 = 2/12"],
            ["x"],
        ),
        (
            "If 3 cups of flour make 12 cookies, how many cups would I need to bake 30 cookies?",
            ["x/30 = 3/12"],
            ["x"],
        ),
        (
            "It takes 2 eggs to make 8 pancakes. How many eggs for 20 pancakes?",
            ["x/20 = 2/8"],
            ["x"],
        ),
        (
            "A car uses 8 litres of fuel for 100 km. How many litres for 250 km?",
            ["x/250 = 8/100"],
            ["x"],
        ),
    ],
)
def test_word_template_setup_reads_classic_shapes(
    text: str, equations: list[str], targets: list[str]
) -> None:
    setup = word_template_setup(text)
    assert setup is not None
    assert [item.equation for item in setup.equations] == equations
    assert [target.expr for target in setup.targets] == targets


@pytest.mark.parametrize(
    "text",
    [
        # No odd answer: three odd integers cannot sum to 72.
        "the sum of three consecutive odd integers is 72. find them",
        # No whole answer.
        "the sum of three consecutive integers is 73",
        # Four values need more targets than a reply shows.
        "the sum of four consecutive integers is 74. find them",
        # Half years.
        "Sam is 4 years older than Ana. the sum of their ages is 31. how old is Ana",
        # The person asked about is not in the problem.
        "Sam is 4 years older than Ana. the sum of their ages is 30. how old is Ben",
        # No whole number of tickets fits.
        "tickets cost $8 for adults and $5 for kids. 40 tickets were sold for $261. "
        "how many adult tickets",
        # The target strength is not between the two.
        "how many liters of 20% acid solution must be mixed with 10 L of 50% solution to "
        "get a 60% solution",
        # Different units.
        "how many liters of 20% acid solution must be mixed with 10 ml of 50% solution to "
        "get a 30% solution",
        # Something more rides along.
        "the sum of three consecutive integers is 72 and their product is even. find them",
        "my 3 kids are 4 years apart, the sum of their ages is 30",
        # Workers and days scale inversely; drivers round up.
        "A job takes 12 days for 4 workers. How many days for 6 workers?",
        "A tour needs 2 drivers for 40 passengers. How many drivers for 90 passengers?",
        # Something other than the stated amount is asked, or for something else.
        "A recipe needs 3 cups of flour for 12 cookies. How many eggs for 30 cookies?",
        "A recipe needs 3 cups of flour for 12 cookies. How many cups for 30 muffins?",
        "A recipe needs 3 cups of flour for 12 cookies. How many cups of sugar for 30 cookies?",
        # No question to scale.
        "A recipe needs 3 cups of flour for 12 cookies, is that a lot?",
    ],
)
def test_word_template_setup_declines_what_it_cannot_read(text: str) -> None:
    assert word_template_setup(text) is None


@pytest.mark.parametrize(
    ("text", "operands"),
    [
        (
            "I bought 3 notebooks at $2.40 each and a pen for $1.85. I paid with a $20 bill. "
            "how much change do i get",
            ["20", "3*2.40", "1.85"],
        ),
        (
            "Maria buys two pizzas at $12 each, and a drink for $3. She pays with $50. "
            "how much change does she get back?",
            ["50", "2*12", "3"],
        ),
        # prepare() drops "$...$" as an inline-maths span.
        (
            "I bought 3 notebooks at 2.40 each and a pen for 1.85. I paid with a 20 bill. "
            "how much change do i get",
            ["20", "3*2.40", "1.85"],
        ),
    ],
)
def test_extract_change_intent_reads_purchases_and_payment(text: str, operands: list[str]) -> None:
    intent = extract_change_intent(text)
    assert intent is not None
    assert intent.school_op == "change_from_payment"
    assert intent.arithmetic_operands == operands


@pytest.mark.parametrize(
    "text",
    [
        # "for $2.40" could be the price of all three.
        "I bought 3 notebooks for $2.40 and a pen for $1.85. I paid with a $20 bill. "
        "how much change do i get",
        # Not enough paid.
        "I bought 3 notebooks at $2.40 each. I paid with a $5 bill. how much change do i get",
        "I bought 3 notebooks at $2.40 each and paid with my card",
    ],
)
def test_extract_change_intent_declines_what_it_cannot_read(text: str) -> None:
    assert extract_change_intent(text) is None


@pytest.mark.parametrize(
    ("text", "op", "principal", "rate", "years"),
    [
        ("simple interest on $1200 at 5% per year for 4 years", "simple_interest", 1200, 5, 4),
        (
            "$5000 invested at 4% interest compounded annually for 3 years, how much will i have",
            "compound_amount",
            5000,
            4,
            3,
        ),
        (
            "$5000 invested at 4% interest compounded annually for 3 years, how much interest "
            "will i earn",
            "compound_interest",
            5000,
            4,
            3,
        ),
        ("compound interest on 1000 at 5% for 3 years", "compound_interest", 1000, 5, 3),
    ],
)
def test_extract_interest_intent_reads_everyday_phrasing(
    text: str, op: str, principal: float, rate: float, years: int
) -> None:
    intent = _extract_interest_intent(text, text.lower())
    assert intent is not None
    assert (intent.school_op, intent.percent_base, intent.percent_rate, intent.combo_n) == (
        op,
        principal,
        rate,
        years,
    )


@pytest.mark.parametrize(
    "text",
    [
        "$5000 invested at 4% interest compounded monthly for 3 years, how much will i have",
        "$5000 invested at 4% interest compounded quarterly for 3 years, how much will i have",
        # The simple-interest total is not what the template computes.
        "simple interest on $1200 at 5% per year for 4 years, how much will i have",
        # Two quantities asked at once.
        "$5000 invested at 4% compound interest for 3 years, how much interest and how much "
        "will i have",
    ],
)
def test_extract_interest_intent_declines_other_periods_and_totals(text: str) -> None:
    assert _extract_interest_intent(text, text.lower()) is None


def test_extract_arithmetic_intent_routes_change_before_bare_arithmetic() -> None:
    intent = _extract_arithmetic_intent(
        "I bought 2 pens at $1.50 each. I paid with a $5 bill. how much change do i get"
    )
    assert intent is not None and intent.school_op == "change_from_payment"


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("the sum of three consecutive integers is 72. find them", r"23,\ 24,\ 25"),
        (
            "Sam is 4 years older than Ana. the sum of their ages is 30. how old is Ana",
            r"13\ \text{years}",
        ),
        (
            "tickets cost $8 for adults and $5 for kids. 40 tickets were sold for $260. "
            "how many adult tickets",
            r"20\ \text{tickets}",
        ),
        (
            "how many liters of 20% acid solution must be mixed with 10 L of 50% solution to "
            "get a 30% solution",
            r"20\ \text{litres}",
        ),
        (
            "I bought 3 notebooks at $2.40 each and a pen for $1.85. I paid with a $20 bill. "
            "how much change do i get",
            r"\$10.95",
        ),
        (
            "$5000 invested at 4% interest compounded annually for 3 years, how much will i have",
            "5624.32",
        ),
        ("simple interest on $1200 at 5% per year for 4 years", "240"),
        (
            "A recipe needs 3 cups of flour for 12 cookies. How many cups for 30 cookies?",
            r"\frac{15}{2}\ \text{cups}",
        ),
        (
            "A pancake recipe uses 2 eggs for 8 pancakes. How many eggs for 20 pancakes?",
            r"5\ \text{eggs}",
        ),
    ],
)
@pytest.mark.asyncio
async def test_build_math_augmentation_verifies_word_templates(text: str, answer: str) -> None:
    assert needs_symbolic_math(text)
    settings = Settings(math_tools_enabled=True, mock_llm_enabled=True)
    _, verified = await build_math_augmentation(text, settings)
    assert verified is not None
    assert verified.canonical_answer == answer


@pytest.mark.parametrize(
    "text",
    [
        "I bought 3 shirts and paid with my card, how much change for laundry",
        "my 3 kids and I spent $40 at the fair",
        "our tickets cost $8 each, is that a good deal",
        "how many liters of water should I drink a day",
        "my recipe makes 12 cookies, how many should I bake for the party?",
        "A recipe needs 3 cups of flour for 12 cookies, is that a lot?",
        "I booked 2 rooms for 3 nights. How many towels come with that?",
        "we need 2 pizzas for 6 people, what toppings should we get?",
    ],
)
def test_needs_symbolic_math_keeps_word_template_lookalikes_out(text: str) -> None:
    assert not needs_symbolic_math(text)
