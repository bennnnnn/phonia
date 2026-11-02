"""The graph fence's expression is SymPy's reading, in the phone's plot grammar.

The shared fixture (`test_math_graph_expr_contract.py`) holds the printed text to
the phone. These cases cover what it cannot: the forms the phone has no spelling
for, which keep the raw text, and the printer's own edges.
"""

from __future__ import annotations

from typing import Any

import pytest
from sympy import Float, I, Symbol, log, oo, sec, sign, sin, sqrt

from app.modules.math.schemas import GraphSampleInput
from app.modules.math.solve import sample_function
from app.modules.math.solve.graph_expr_text import graph_expr_text

x = Symbol("x")
t = Symbol("t")


@pytest.mark.parametrize(
    "expr, variable, text",
    [
        (log(x) / log(2), "x", "ln(x)/ln(2)"),
        (3 * log(x) / log(10), "x", "3log(x)"),
        (Float(1e-20) * x, "x", "0.00000000000000000001x"),
        (Float(2.5) * sin(t), "t", "2.5sin(t)"),
        (1 / (2 * x * (x + 1)), "x", "1/(2x*(x + 1))"),
        (1 / sqrt(x + 1), "x", "1/sqrt(x + 1)"),
        (2 * (x + 1) ** 2, "x", "2(x + 1)^2"),
    ],
)
def test_graph_expr_text_prints_the_phone_grammar(expr: Any, variable: str, text: str) -> None:
    assert graph_expr_text(expr, variable) == text


@pytest.mark.parametrize(
    "expr",
    [sec(x), sign(x), x + Symbol("a"), I * x, x + oo, x * Symbol("y")],
    ids=["sec", "sign", "other symbol", "imaginary", "infinity", "two variables"],
)
def test_graph_expr_text_declines_what_the_phone_cannot_write(expr: Any) -> None:
    assert graph_expr_text(expr, "x") is None


def test_graph_expr_text_declines_past_the_fence_limit() -> None:
    long_sum = sum(sin(k * x) for k in range(1, 40))
    assert graph_expr_text(long_sum, "x") is None


@pytest.mark.parametrize("expr", ["sec(x)", "sign(x)"])
def test_sample_function_keeps_the_raw_text_the_phone_cannot_read(expr: str) -> None:
    """The phone refuses ``sec``/``sign`` and draws the server's own samples."""
    sample = sample_function(GraphSampleInput(expr=expr, variable="x", x_min=0.1, x_max=1))
    assert sample.expr == expr
    assert sample.points
