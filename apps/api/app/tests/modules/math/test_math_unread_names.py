"""A card that restates the question is no answer (2026-11-01 live baseline).

"Find the cube root of 27a^3 + 54a^2b + 36ab^2 + 8b^3." went to the model reader, which wrote
``cube_root(27a^3 + …)``. The parser read ``cube_root`` as one symbol times the polynomial,
"simplified" that to itself, and the checked card was the question (right: 3a + 2b). A name
the parser does not know as a function or as one-letter variables declines, and a card that
is an expression the question states, or a root of one, compared as SymPy trees, is no
answer.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.restated import card_restates
from app.modules.math.tool import SympyAdapter
from app.modules.math.tools import prompt as math_prompt
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.llm_extract import LLMMathExtract
from app.services.solving import SolveServiceError

_CUBE = "27a^3 + 54a^2b + 36ab^2 + 8b^3"


@pytest.mark.parametrize(
    "expr",
    [
        f"cube_root({_CUBE})",
        "cuberoot(8)",
        "nthroot(8, 3)",
        "foo(x)",
        "fog(x)",
        "speed + 2",
        "velocity*3",
        "area*2",
        "xx + 1",
        "cube*2",
    ],
)
def test_a_name_the_parser_does_not_know_declines(expr: str) -> None:
    with pytest.raises(SolveServiceError):
        math_solve.parse_expression(expr)


@pytest.mark.parametrize(
    "expr",
    [
        _CUBE,
        "a^3 + b^3 + c^3 - 3abc",
        "2xy + 3xz",
        "ab(a+b)",
        "3abc(2a - b + c)",
        "xyz(x + y + z)",
        "2abcd + 3abcd",
        "12pqrs/(4pq)",
        "lwh",
        "nRT",
        "sinx + cosx",
        "log2(8)",
        "theta + 1",
        "x_1 + x_2",
        "factorial(5)",
        "binomial(5, 2)",
        "sqrt(x) + exp(x) + Abs(x)",
        "cbrt(27) + root(8, 3)",
        "max(1, 2)",
        "pi*r^2",
        "oo",
        "2e5 + x",
    ],
)
def test_functions_constants_and_letters_written_together_still_parse(expr: str) -> None:
    math_solve.parse_expression(expr)


_ROOT = "(27*a^3 + 54*a^2*b + 36*a*b^2 + 8*b^3)^(1/3)"


@pytest.mark.parametrize(
    ("question", "expr", "kept"),
    [
        # The card would be the question's expression with the root still on it.
        (f"Find the cube root of {_CUBE}.", _ROOT, False),
        # Its terms in any order (Claude review): the card prints them in SymPy's.
        (f"Find the cube root of {_CUBE}.", "(8*b^3 + 36*a*b^2 + 54*a^2*b + 27*a^3)^(1/3)", False),
        ("simplify sqrt(x^2 + 1)", "sqrt(x^2 + 1)", False),
        # Already simplest is an answer: its excluded value is stated beside it.
        ("simplify (x+1)/(x-1)", "(x+1)/(x-1)", True),
        # A fraction is matched whole, never inside the question's terms (Claude review).
        ("simplify (x+1)/(x-1) - x/(x-1)", "(x+1)/(x-1) - x/(x-1)", True),
        # A rewrite the student asked for keeps its card.
        ("Simplify x^-2", "x^-2", True),
        ("Simplify -(-x)", "-(-x)", True),
        ("simplify (x^2-1)/(x-1)", "(x^2-1)/(x-1)", True),
        ("simplify 2x + 3x", "2x + 3x", True),
    ],
)
def test_a_card_is_kept_only_when_it_says_something_new(
    question: str, expr: str, kept: bool
) -> None:
    intent = MathIntent(kind="calculus", operation="simplify", expr=expr, variable="x")
    intent._request_text = question
    block = _build_verified_block(intent, Settings())
    assert (block is not None and block.canonical_answer is not None) is kept


@pytest.mark.parametrize(
    ("given", "card"),
    [
        ("5", "5"),
        ("3/4", r"\frac{3}{4}"),
        ("x", "x"),
        ("2*x + 3", "x = 2"),
        ("x^2 + 1", "x^{2} + 1"),
    ],
)
def test_a_number_a_letter_or_an_equation_never_restates(given: str, card: str) -> None:
    """A median, the option a comparison picks, a letter or a solved equation is an answer."""
    assert not card_restates(card, (given,))


@pytest.mark.asyncio
async def test_the_model_readers_cube_root_gets_no_card(monkeypatch: pytest.MonkeyPatch) -> None:
    """The live turn: the regex readers miss, the model reader writes ``cube_root(…)``."""
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def reader(**_kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(
            found=True, kind="calculus", operation="simplify", expr=f"cube_root({_CUBE})"
        )

    monkeypatch.setattr(litellm_gateway, "complete_structured", reader)
    settings = Settings(math_tools_enabled=True, math_llm_extract_enabled=True)
    _note, verified = await math_prompt.build_math_augmentation(
        f"Find the cube root of {_CUBE}.", settings, needs_math=True
    )
    assert verified is None


@pytest.mark.asyncio
async def test_the_sympy_tool_certifies_no_restated_expression(thread_sympy_executor: None) -> None:
    """The model's own simplify call on a root of the whole expression repeats the question."""
    adapter = SympyAdapter(Settings())
    root = "(27*a**3 + 54*a**2*b + 36*a*b**2 + 8*b**3)**(1/3)"
    same = await adapter._action_expr_op({"action": "simplify", "expr": root})
    assert not (same.data or {}).get("canonical_answer")
    assert "Do NOT claim" in same.content
    changed = await adapter._action_expr_op({"action": "simplify", "expr": "2*x + 3*x"})
    assert (changed.data or {}).get("canonical_answer") == "5 x"
