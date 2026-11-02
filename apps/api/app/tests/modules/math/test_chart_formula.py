"""A model's chart of a formula is drawn by SymPy; the phone never evaluates one."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.math.chart_formula import (
    CHART_FAIL_NOTE,
    formula_charts_to_graphs,
    has_formula_chart,
    read_formula_chart,
)

SETTINGS = Settings(math_tools_enabled=True)


def _fence(spec: Mapping[str, object], lang: str = "chart") -> str:
    return f"```{lang}\n{json.dumps(spec)}\n```\n"


def _graph(reply: str) -> dict[str, object]:
    body = reply.split("```graph\n", 1)[1].split("\n```", 1)[0]
    return json.loads(body)


def _series(reply: str) -> list[dict[str, Any]]:
    body = reply.split("```chart\n", 1)[1].split("\n```", 1)[0]
    return json.loads(body)["series"]


def test_two_formula_series_become_one_two_curve_graph() -> None:
    # The c-graph reply: a "function" chart the phone drew as a blank card.
    spec = {
        "type": "function",
        "series": [
            {"name": "y = sin(x)", "fn": "sin(x)"},
            {"name": "y = cos(x)", "fn": "cos(x)"},
        ],
        "domain": [0, 6.2832],
    }
    reply = formula_charts_to_graphs("Here:\n\n" + _fence(spec) + "\nDone.", SETTINGS)
    graph = _graph(reply)
    assert (graph["expr"], graph["expr2"]) == ("sin(x)", "cos(x)")
    assert graph["x_min"] == 0 and graph["x_max"] == pytest.approx(6.2832)
    assert graph["points"] and graph["points2"]
    assert reply.startswith("Here:\n\n```graph") and reply.endswith("\nDone.")


@pytest.mark.parametrize(
    "spec, expr, x_max",
    [
        # One formula at the top, a left side, ^, and a bound written with π.
        ({"type": "function", "fn": "y = x^2", "domain": ["-2π", "2π"]}, "x^2", 6.2832),
        # The x range as x_min / x_max on the axis.
        ({"type": "line", "expr": "2*x + 1", "x_axis": {"min": 0, "max": 5}}, "2x + 1", 5.0),
        # Vega-Lite asked to compute the curve: a sequence and a calculate.
        (
            {
                "data": {"sequence": {"start": 0, "stop": 3.14, "step": 0.1, "as": "t"}},
                "transform": [{"calculate": "Math.sin(datum.t)", "as": "y"}],
                "mark": "line",
            },
            "sin(x)",
            3.14,
        ),
    ],
)
def test_one_formula_becomes_a_graph(spec: dict[str, object], expr: str, x_max: float) -> None:
    graph = _graph(formula_charts_to_graphs(_fence(spec), SETTINGS))
    assert graph["expr"] == expr
    assert graph["x_max"] == pytest.approx(x_max, abs=1e-3)


def test_a_formula_beside_data_is_sampled_across_the_data() -> None:
    data: dict[str, Any] = {"name": "Data", "points": [[1, 2.1], [2, 3.9], [5, 10.1]]}
    spec = {"type": "scatter", "series": [data, {"name": "Best fit", "fn": "2x + 0.05"}]}
    series = _series(formula_charts_to_graphs(_fence(spec), SETTINGS))
    assert series[0] == data
    fit = series[1]
    assert fit["name"] == "Best fit" and fit["type"] == "line"
    points = fit["points"]
    assert isinstance(points, list)
    assert points[0] == [1.0, 2.05] and points[-1] == [5.0, 10.05]


def test_more_curves_than_a_graph_holds_stay_a_chart_of_sampled_points() -> None:
    spec = {"series": [{"fn": "x"}, {"fn": "x^2"}, {"fn": "x^3"}], "domain": [0, 2]}
    series = _series(formula_charts_to_graphs(_fence(spec), SETTINGS))
    assert [item["name"] for item in series] == ["y = x", "y = x**2", "y = x**3"]
    assert all(item["type"] == "line" and item["points"] for item in series)


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "function", "fn": "hello world"},
        {"type": "function", "fn": "sin(t) * q"},
    ],
)
def test_a_formula_sympy_cannot_read_leaves_a_note(spec: dict[str, object]) -> None:
    assert formula_charts_to_graphs("x\n" + _fence(spec) + "y", SETTINGS) == (
        f"x\n{CHART_FAIL_NOTE}\ny"
    )


@pytest.mark.parametrize(
    "reply",
    [
        _fence({"mark": "bar", "data": {"values": [{"a": 1, "b": 2}]}}),
        _fence({"type": "line", "series": [{"name": "a", "points": [[1, 2]]}]}),
        # A formula key outside a chart fence is not a chart.
        '```json\n{"fn": "sin(x)"}\n```\n',
        # Not JSON: the phone says it cannot draw it.
        "```chart\nnot json\n```\n",
    ],
)
def test_data_charts_and_other_fences_are_left_alone(reply: str) -> None:
    assert formula_charts_to_graphs(reply, SETTINGS) == reply


def test_the_cheap_check_only_looks_inside_chart_fences() -> None:
    assert has_formula_chart(_fence({"fn": "x"}, lang="vega-lite"))
    assert has_formula_chart(_fence({"data": {"sequence": {"start": 0, "stop": 1}}}))
    assert not has_formula_chart('```json\n{"fn": "x"}\n```\n')
    assert not has_formula_chart(_fence({"mark": "bar", "data": {"values": [{"a": 1}]}}))
    assert read_formula_chart({"mark": "bar", "data": {"values": [{"a": 1}]}}) is None
