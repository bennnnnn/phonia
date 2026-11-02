"""A power or factorial no student means is refused before SymPy builds it.

``graph 2y = 9^9^8 + x`` held the event loop for 56 s while the graph reader's parse built a
41-million-digit integer, then raised from ``str()``.
"""

from __future__ import annotations

import time

import pytest

from app.modules.math.solve.parse import parse_expression
from app.modules.math.tools.extract import extract_math_intent
from app.services.solving import SolveServiceError


@pytest.mark.wall_clock
@pytest.mark.parametrize(
    "expr",
    ["9^9^8", "9**9**9", "2^(10^8)", "2^(-10^8)", "x^(9^9^9)", "(10^6)!", "10^20000", "3 * 7^7^7"],
)
def test_a_number_past_the_limit_is_refused(expr: str) -> None:
    start = time.perf_counter()
    with pytest.raises(SolveServiceError, match="out of range"):
        parse_expression(expr, ["x"])
    assert time.perf_counter() - start < 0.5


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("2^10", "1024"),
        ("9^9^2", str(9**81)),
        ("x^2 + 3", "x**2 + 3"),
        ("2^x", "2**x"),
        ("5!", "120"),
        ("1.5^2", "2.25000000000000"),
    ],
)
def test_ordinary_powers_still_parse(expr: str, expected: str) -> None:
    assert str(parse_expression(expr, ["x"])) == expected


def test_a_hundred_factorial_is_within_the_limit() -> None:
    assert len(str(parse_expression("100!"))) == 158


@pytest.mark.wall_clock
def test_the_graph_reader_declines_a_power_tower_at_once() -> None:
    start = time.perf_counter()
    intent = extract_math_intent("graph 2y = 9^9^8 + x")
    assert time.perf_counter() - start < 0.5
    # No y = f(x) was found, so no verified graph is drawn from it.
    assert intent is None or not intent.expr or "9**9**8" in intent.expr
