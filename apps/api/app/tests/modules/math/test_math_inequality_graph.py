"""A verified two-variable inequality must shade a region, not disappear."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.math import fence as math_fence
from app.modules.math.schemas import GraphBlockSpec
from app.modules.math.solve.inequality_graph import affine_inequality_graph_spec
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.parametrize(
    "expr,coefficients,comparator",
    [
        ("y < 2x", (-2, 1, 0), "<"),
        ("y <= 2x + 3", (-2, 1, 3), "<="),
        ("2x > y", (2, -1, 0), ">"),
        ("-y >= 2x - 4", (-2, -1, -4), ">="),
        ("2x + 3y <= 6", (2, 3, 6), "<="),
        ("y >= x/2 - 1", (-0.5, 1, -1), ">="),
        (r"y \leq 2x", (-2, 1, 0), "<="),
        ("y ≥ 2x", (-2, 1, 0), ">="),
        ("y - y + x < 3", (1, 0, 3), "<"),
    ],
)
def test_affine_coefficients_preserve_side_and_strictness(
    expr: str, coefficients: tuple[float, float, float], comparator: str
) -> None:
    spec = affine_inequality_graph_spec(expr)
    assert spec is not None
    assert spec.type == "inequality"
    assert (spec.a, spec.b, spec.c) == coefficients
    assert spec.comparator == comparator
    assert spec.points == []
    assert (spec.x_min, spec.x_max, spec.y_min, spec.y_max) == (-10, 10, -10, 10)


@pytest.mark.parametrize(
    "expr",
    [
        "x < 3",
        "y >= 2",
        "y < x**2",
        "x**2 + y**2 <= 4",
        "y < sin(x)",
        "y < x/x",
        "y < x**2/x",
        "y < (x-1)/(x-1)",
        "y < sqrt(x)**2",
        "y < a*x + 2",
        "y < x + z",
        "y = 2x",
        "0 < y < 2x",
        "y < 2x and x < 3",
        "y - y < x - x",
        "y < x/0",
        "y < x + oo",
        "y < I*x",
        "y < x.__class__",
        "y < " + "x" * 256,
    ],
)
def test_non_affine_and_domain_losing_inputs_stay_unsupported(expr: str) -> None:
    assert affine_inequality_graph_spec(expr) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"a": None},
        {"a": 0, "b": 0},
        {"c": float("inf")},
        {"comparator": None},
        {"comparator": "!="},
        {"expr": ""},
        {"y_min": None},
        {"x_min": 2, "x_max": 1},
        {"y_min": float("nan")},
        {"x_min": -1e308, "x_max": 1e308},
    ],
)
def test_region_schema_requires_complete_finite_geometry(changes: dict[str, object]) -> None:
    spec = affine_inequality_graph_spec("y < 2x")
    assert spec is not None
    with pytest.raises(ValidationError):
        GraphBlockSpec.model_validate({**spec.model_dump(), **changes})


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["graph y < 2x", "graph y <= 2x from -4 to 6"])
async def test_live_prompt_builds_verified_region_and_final_fence(query: str) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    graph = verified.canonical_fence
    assert graph is not None
    assert graph["type"] == "inequality"
    assert (graph["a"], graph["b"], graph["c"]) == (-2, 1, 0)
    assert (graph["x_min"], graph["x_max"]) == ((-4, 6) if "from" in query else (-10, 10))
    final = math_fence.validate_math_fences("", verified=verified)
    assert "Couldn't verify" not in final
    assert json.loads(final.split("```graph\n")[1].split("\n```")[0]) == graph


def test_existing_one_variable_graph_keeps_number_line() -> None:
    intent = extract_math_intent("graph x > 3")
    assert intent is not None
    verified = _build_verified_block(intent, Settings())
    assert verified is not None and verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "number_line"


def test_region_fence_replaces_model_curve_without_resampling() -> None:
    intent = extract_math_intent("graph y < 2x")
    assert intent is not None
    verified = _build_verified_block(intent, Settings())
    assert verified is not None and verified.canonical_fence is not None
    wrong_curve = '```graph\n{"type":"function","expr":"2*x","points":[[0,0],[1,2]]}\n```'
    with patch("app.modules.math.solve.sample_function", side_effect=AssertionError("No sampling")):
        final = math_fence.validate_math_fences(wrong_curve, verified=verified)
    assert "Could not render" not in final
    assert final.count("```graph") == 1
    assert json.loads(final.split("```graph\n")[1].split("\n```")[0]) == verified.canonical_fence


def test_truncated_fence_recovers_owned_region_on_timeout_path() -> None:
    spec = affine_inequality_graph_spec("y < 2x")
    assert spec is not None
    final = math_fence.replace_unclosed_graph_fence_safe('```graph\n{"type":', spec.model_dump())
    assert "Could not render" not in final
    assert json.loads(final.split("```graph\n")[1].split("\n```")[0]) == spec.model_dump()


def test_model_only_region_is_not_trusted() -> None:
    spec = affine_inequality_graph_spec("y < 2x")
    assert spec is not None
    content = f"```graph\n{spec.model_dump_json()}\n```"
    assert "```graph" not in math_fence.validate_math_fences(content)


@pytest.mark.parametrize(
    "text",
    [
        "x**2 - 1 > 0",
        "2*x + 3 <= 7",
        "x**2 < 4",
        "x**3 - x >= 0",
        "1/x > 2",
        "abs(x - 2) < 3",
        "sqrt(x) < 2",
        "1 < x <= 3",
        "5 > 2*x + 1 >= -3",
    ],
)
def test_the_number_line_draws_the_answer_cards_set(text: str) -> None:
    """Both read one solve (``solve/inequalities.py``); they were copies that could drift."""
    from app.modules.math.solve.extract_eq import (
        try_extract_compound_inequality_from_text,
        try_extract_inequality_from_text,
    )
    from app.modules.math.solve.graph import (
        _collect_number_line_intervals,
        number_line_spec_from_expr,
    )
    from app.modules.math.solve.inequalities import (
        compound_solution_set,
        inequality_solution_set,
    )

    compound = try_extract_compound_inequality_from_text(text)
    if compound is not None:
        answer_set = compound_solution_set(*compound, "x")
    else:
        single = try_extract_inequality_from_text(text)
        assert single is not None
        lhs, rhs, comparator = single
        answer_set = inequality_solution_set(lhs, rhs, comparator, "x")
    expected: list = []
    assert _collect_number_line_intervals(answer_set, expected)

    spec = number_line_spec_from_expr(text)

    assert spec is not None
    assert spec.intervals == expected
