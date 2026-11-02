"""A model's reading of a problem is no verified answer unless it is the user's own maths.

SymPy checks the arithmetic of the equations it is given, not that they say what the problem
says (2026-11-01 live baseline). "The polynomial f(x) = A(x - 1)^2 + B(x + 2)^2 is divided by
x + 1 and x - 2. The remainders are 3 and -15" was read by the model as 9B = 3 and
A + 16B = -15, and the checked card said A = -61/3, B = 1/3 (right: A = 1, B = -1). "If this
process continues without end, find the total tax" was summed over three rounds, 3920 Birr
for 5000. A model's extraction is certified only when its equation or expression is one the
user wrote; a word problem's translation never is (the model gets it as an unchecked setup to
check against the words), and a process that never ends gets no setup at all. A setup the
server's own templates read keeps its card.
"""

from __future__ import annotations

import pickle
from concurrent.futures.process import BrokenProcessPool
from typing import Any

import pytest

from app.core import sympy_executor
from app.core.config import Settings
from app.gateways import litellm_gateway
from app.modules.math.schemas import MathImageExtract, MathIntent
from app.modules.math.schemas.word_problem import WordProblemSetup
from app.modules.math.tool_check import intent_in_user_text, tool_call_matches_user_text
from app.modules.math.tools import prompt as math_prompt
from app.modules.math.tools.block.word import UNCHECKED_SETUP_RULE
from app.modules.math.tools.llm_extract import LLMMathExtract
from app.modules.math.tools.model_readings import unchecked_setup
from app.modules.math.tools.word_problem import _ENDLESS, word_problem_intent
from app.modules.math.tools.word_templates import word_template_setup

REMAINDERS = (
    "The polynomial f(x) = A(x - 1)^2 + B(x + 2)^2 is divided by x + 1 and x - 2. The "
    "remainders are 3 and -15 respectively. Find the values of A and B."
)
ENDLESS_TAX = (
    "Suppose you earn Birr 10,000.00 per month and pay 20% tax and spend 60% of it. Again the "
    "recipient of the money spent by you pays 20% tax and spends 60% of it. If this process "
    "continues without end, find the total amount that will be paid for the tax."
)
AGES = (
    "Maria is three times as old as her son. Together their ages add up to 48. How old is her son?"
)
AGES_SETUP: dict[str, Any] = {
    "found": True,
    "unknowns": [
        {"symbol": "m", "meaning": "Maria's age now", "unit": "years"},
        {"symbol": "s", "meaning": "her son's age now", "unit": "years"},
    ],
    "equations": [
        {"equation": "m = 3*s", "source": "Maria is three times as old as her son"},
        {"equation": "m + s = 48", "source": "Together their ages add up to 48"},
    ],
    "targets": [{"expr": "s", "meaning": "her son's age", "unit": "years"}],
    "whole_numbers": True,
    "positive": True,
}
CONSECUTIVE = "Three consecutive integers add up to 72. Find the integers."


def _settings() -> Settings:
    return Settings(math_tools_enabled=True, math_llm_extract_enabled=True)


def _models(*, setup: dict[str, Any] | None = None, extract: LLMMathExtract | None = None) -> Any:
    """The structured calls: the word-problem translation and the maths extraction."""

    async def fake(*, schema: type, **_kwargs: Any) -> Any:
        if schema is WordProblemSetup:
            return None if setup is None else WordProblemSetup.model_validate(setup)
        return extract

    return fake


@pytest.mark.asyncio
async def test_a_translated_word_problem_is_an_unchecked_setup(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    monkeypatch.setattr(litellm_gateway, "complete_structured", _models(setup=AGES_SETUP))
    note, verified = await math_prompt.build_math_augmentation(AGES, _settings())
    assert verified is None
    assert note is not None
    assert "read by a model (not checked against the problem)" in note
    assert '(from "Together their ages add up to 48")' in note
    assert "SymPy's solution of these equations: m = 36, s = 12" in note
    assert UNCHECKED_SETUP_RULE in note


@pytest.mark.asyncio
async def test_a_setup_the_templates_read_keeps_its_card(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    async def no_call(**_kwargs: Any) -> Any:
        raise AssertionError("a template reads this problem without a model")

    monkeypatch.setattr(litellm_gateway, "complete_structured", no_call)
    _note, verified = await math_prompt.build_math_augmentation(CONSECUTIVE, _settings())
    assert verified is not None and verified.canonical_answer is not None


@pytest.mark.asyncio
async def test_the_models_reading_of_a_remainder_problem_gets_no_card(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    misread = LLMMathExtract(
        found=True,
        kind="system",
        equations=[("9*B", "3"), ("A + 16*B", "-15")],
        variables=["A", "B"],
    )
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)
    monkeypatch.setattr(litellm_gateway, "complete_structured", _models(extract=misread))
    _note, verified = await math_prompt.build_math_augmentation(REMAINDERS, _settings())
    assert verified is None


@pytest.mark.asyncio
async def test_a_process_without_end_gets_no_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_call(**_kwargs: Any) -> Any:
        raise AssertionError("an endless process is not translated")

    monkeypatch.setattr(litellm_gateway, "complete_structured", no_call)
    assert await word_problem_intent(ENDLESS_TAX, _settings()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "certified"),
    [("Integrate x^2 please", True), ("Integrate x squared", False)],
)
async def test_the_models_extraction_is_certified_only_as_the_users_own_maths(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None, text: str, certified: bool
) -> None:
    read = LLMMathExtract(found=True, kind="calculus", operation="integrate", expr="x^2")
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)
    monkeypatch.setattr(litellm_gateway, "complete_structured", _models(extract=read))
    _note, verified = await math_prompt.build_math_augmentation(text, _settings())
    assert (verified is not None) is certified


def test_a_models_json_cannot_mark_its_setup_read_from_the_text() -> None:
    forged = WordProblemSetup.model_validate({**AGES_SETUP, "_read_from_text": True})
    assert not forged.read_from_text
    template = word_template_setup(CONSECUTIVE)
    assert template is not None and template.read_from_text
    # The SymPy pool gets the setup pickled: the mark goes with it.
    assert pickle.loads(pickle.dumps(template)).read_from_text  # noqa: S301 - our own object


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("equations", "source", "certified"),
    [
        # The vision model's setup of a photographed remainder problem: not on the page.
        ([("9*B", "3"), ("A + 16*B", "-15")], REMAINDERS, False),
        ([("2*x + 3", "7")], "Solve 2x + 3 = 7", True),
    ],
)
async def test_a_photos_equations_are_certified_only_as_they_are_on_the_page(
    thread_sympy_executor: None,
    equations: list[tuple[str, str]],
    source: str,
    certified: bool,
) -> None:
    variables = sorted({ch for pair in equations for side in pair for ch in side if ch.isalpha()})
    photo = MathImageExtract(
        kind="system" if len(equations) > 1 else "equation",
        lhs=equations[0][0],
        rhs=equations[0][1],
        equations=equations if len(equations) > 1 else None,
        variables=variables,
        source_text=source,
    )
    _note, verified = await math_prompt.build_math_augmentation(
        "solve this", _settings(), has_image_attachment=True, image_math_extract=photo
    )
    assert (verified is not None) is certified


@pytest.mark.parametrize(
    ("args", "text", "matches"),
    [
        # A bound is written with its sign: -1 is not "between 1 and 2".
        ({"lower": "-1", "upper": "2"}, "the definite integral of x^2 between 1 and 2", False),
        ({"lower": "1", "upper": "2"}, "the definite integral of x^2 between 1 and 2", True),
        ({"lower": "-1", "upper": "1"}, "integrate x^2 from -1 to 1", True),
        ({"lower": "-oo", "upper": "0"}, "the integral of x^2 between 0 and infinity", False),
        ({"lower": "0", "upper": "oo"}, "the integral of x^2 between 0 and infinity", True),
        # The keypad's \infty, and a unicode minus (Claude review).
        ({"lower": "0", "upper": "oo"}, r"\int_{0}^{\infty} x^2 dx", True),
        # A bound after a subscript mark is written (Claude review).
        ({"lower": "1", "upper": "2"}, "int_1^2 x^2 dx", True),
        ({"lower": "1", "upper": "2"}, "\u222b_1^2 x^2 dx", True),
        ({"lower": "-oo", "upper": "0"}, "integrate x^2 from \u2212\u221e to 0", True),
    ],
)
def test_a_bound_is_the_users_with_its_sign(args: dict[str, str], text: str, matches: bool) -> None:
    call = {"action": "integrate", "expr": "x^2", **args}
    assert tool_call_matches_user_text(call, [text]) is matches


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        (
            r"evaluate \int_{1}^{2} \frac{1}{x} dx",
            MathIntent(
                kind="calculus",
                operation="integrate",
                expr="1/x",
                integral_lower="1",
                integral_upper="2",
            ),
        ),
        (
            r"\frac{d}{dx} \frac{x^{2}+1}{x}",
            MathIntent(kind="calculus", operation="differentiate", expr="(x^2+1)/x"),
        ),
        (
            r"simplify \frac{x^{2}-1}{x-1}",
            MathIntent(kind="calculus", operation="simplify", expr="(x^2-1)/(x-1)"),
        ),
    ],
)
def test_maths_the_keypad_types_is_the_users_own(text: str, intent: MathIntent) -> None:
    assert intent_in_user_text(intent, text)


@pytest.mark.parametrize(
    "text",
    [
        "Ana buys Forever stamps at 73 cents each and postcard stamps at 56 cents each. She "
        "buys 20 stamps for $13.62. How many Forever stamps did she buy?",
        "An endless supply of 20% acid is mixed with 50 L of 60% acid. How much is needed for "
        "40% acid?",
        "Without an end-of-year bonus, Sara earns $3000 a month. How much does she earn in 5 "
        "months?",
    ],
)
def test_a_story_word_is_no_endless_process(text: str) -> None:
    assert _ENDLESS.search(text) is None


@pytest.mark.asyncio
async def test_a_broken_pool_keeps_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise BrokenProcessPool("a worker died")

    monkeypatch.setattr(sympy_executor, "run_sympy", broken)
    note = await unchecked_setup(WordProblemSetup.model_validate(AGES_SETUP), _settings())
    # No setup: the turn keeps its honesty note and goes on.
    assert note is None
