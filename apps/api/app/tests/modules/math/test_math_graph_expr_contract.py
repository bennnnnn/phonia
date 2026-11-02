"""The phone resamples a verified plot to the y values SymPy gives.

`docs/fixtures/graph_expr_cases.json` holds plot expressions as the server reads
them, with sample x values and the expected y. This test recomputes each y with
SymPy through the server's own reading of the expression (`parse_expression`,
the parse `sample_function` plots), so the fixture cannot drift from the server.
Each case's `fence` is the text `sample_function` writes into the graph fence;
this test regenerates it and checks the server re-reads it to the same curve.
The phone test (`lib/__tests__/graphExpr.test.ts`) evaluates the raw and fence
text with `lib/math/graphExpr.ts` and must agree within 1e-9.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from sympy import N, Rational, Symbol

from app.modules.math.schemas import GraphSampleInput
from app.modules.math.solve import SolveServiceError, parse_expression, sample_function

FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "graph_expr_cases.json"
CONTRACT: dict[str, Any] = json.loads(FIXTURE.read_text())
VARIABLE: str = CONTRACT["variable"]
# Working precision for each y, well past a double's 17 digits.
_DIGITS = 30


def _id(case: dict[str, Any]) -> str:
    return repr(case["expr"])


def _sympy_y(parsed: Any, x: float) -> float | None:
    """y at an exact x, or None where there is no real, finite value (domain edge or pole)."""
    value = N(parsed.subs(Symbol(VARIABLE), Rational(str(x))), _DIGITS)
    if value.is_real and value.is_finite:
        return float(value)
    return None


def _assert_samples(text: str, case: dict[str, Any]) -> None:
    parsed = parse_expression(text, [VARIABLE])
    assert len(case["y"]) == len(case["x"])
    for x, expected in zip(case["x"], case["y"], strict=True):
        actual = _sympy_y(parsed, x)
        if expected is None:
            assert actual is None, f"x={x}: SymPy gives {actual}, fixture has no value"
        else:
            assert actual is not None, f"x={x}: SymPy gives no real value, fixture has {expected}"
            assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), f"x={x}"


def _fence_text(expr: str) -> str:
    return sample_function(GraphSampleInput(expr=expr, variable=VARIABLE)).expr


@pytest.mark.parametrize("case", CONTRACT["cases"], ids=_id)
def test_graph_expr_contract_matches_sympy(case: dict[str, Any]) -> None:
    if case.get("refused"):
        assert "fence" not in case, "a refused expression has no graph fence"
        with pytest.raises(SolveServiceError):
            parse_expression(case["expr"], [VARIABLE])
        return
    _assert_samples(case["expr"], case)


@pytest.mark.parametrize("case", [c for c in CONTRACT["cases"] if not c.get("refused")], ids=_id)
def test_graph_fence_carries_the_servers_reading(case: dict[str, Any]) -> None:
    """The fence text is what sample_function writes, and it plots the same curve."""
    assert _fence_text(case["expr"]) == case["fence"]
    _assert_samples(case["fence"], case)
    # Densify re-samples a fence from its own text, which must not drift.
    assert _fence_text(case["fence"]) == case["fence"]
