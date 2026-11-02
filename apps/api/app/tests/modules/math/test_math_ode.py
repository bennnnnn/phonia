"""Linear ODEs, and the guard that stops algebra inventing an answer for one.

``solve y'' + y = 0`` used to reach the algebra extractor, which dropped the
``y''`` term, solved the remnant ``+ y = 0``, and published a *verified*
``y = 0``. The prompt tells the model to use verified numbers and not
recompute, so a wrong answer arrived with full confidence — the worst result
this pipeline can produce.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math import school as math_school
from app.modules.math.ode import solve_ode
from app.modules.math.tools import _build_verified_block, extract_math_intent
from app.modules.math.tools.direct import maybe_direct_math_reply


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_math_intent(text)
    if intent is None:
        return None
    block = _build_verified_block(intent, _settings())
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    "text, expected_terms",
    [
        ("solve y'' + y = 0", ("\\sin", "\\cos")),
        ("solve y'' - y = 0", ("e^{- x}", "e^{x}")),
        ("solve y'' + 4y = 0", ("\\sin", "2 x")),
        ("solve y'' + 3y' + 2y = 0", ("e^{- x}",)),
        ("solve dy/dx = 2y", ("e^{2 x}",)),
        ("solve y' = 3y", ("e^{3 x}",)),
    ],
)
def test_linear_odes_solve_through_dsolve(text: str, expected_terms: tuple[str, ...]) -> None:
    answer = _answer(text)
    assert answer is not None, f"{text} produced no verified answer"
    for term in expected_terms:
        assert term in answer, f"{term!r} missing from {answer!r}"


@pytest.mark.parametrize(
    "text",
    ["solve y'' + y = 0", "solve y'' - y = 0", "solve y'' + 4y = 0", "solve y'' + 3y' + 2y = 0"],
)
def test_second_order_ode_never_answers_y_equals_zero(text: str) -> None:
    """The specific regression: the dropped-term remnant solved to y = 0."""
    answer = _answer(text)
    assert answer != "y = 0"
    intent = extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "calculus"


def test_algebra_does_not_claim_an_equation_with_a_leftover_derivative() -> None:
    """Guard in its own right: even if dsolve declines, algebra must not step in.

    A fourth-order ODE is past what solve_ode handles, so the model answers it
    unverified. What must never happen is algebra silently dropping y'''' and
    certifying the remnant.
    """
    assert _answer("solve y'''' + y = 0") != "y = 0"


def test_derivative_ask_is_not_mistaken_for_an_ode() -> None:
    """`Find dy/dx if y = x^2` has an English word between the mark and the `=`."""
    intent = extract_math_intent("Find dy/dx if y = x^2")
    assert intent is not None
    assert intent.operation == "differentiate"
    assert _answer("Find dy/dx if y = x^2") == "2 x"


def test_solve_ode_rejects_an_equation_with_no_derivative() -> None:
    with pytest.raises(math_school.SolveServiceError):
        solve_ode("y + 1 = 0")


def test_first_order_growth_ode_uses_verified_separation_steps() -> None:
    query = "Solve y’ = y with y(0)=1. Show the steps."
    intent = extract_math_intent(query)
    assert intent is not None
    block = _build_verified_block(intent, _settings())
    assert block is not None and block.canonical_answer is not None
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None
    assert "separate variables" in reply
    assert r"\frac{1}{y}\,dy = 1\,dx" in reply
    assert "use the initial condition" in reply
    assert block.canonical_answer in reply


def test_answer_only_overrides_a_builder_worked_reply() -> None:
    query = "Solve y'=y with y(0)=1. Just the answer."
    intent = extract_math_intent(query)
    assert intent is not None
    block = _build_verified_block(intent, _settings())
    assert block is not None and block.canonical_answer is not None
    assert maybe_direct_math_reply(block, query) == (f"```answer\n{block.canonical_answer}\n```\n")
