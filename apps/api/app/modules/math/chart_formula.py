"""A model's ```chart that plots a formula, drawn by SymPy instead.

The phone never evaluates a formula. A chart whose series is ``"fn": "sin(x)"``
(the chart contract's way to ask for a curve), or a Vega-Lite ``data.sequence``
with a ``calculate``, becomes the ```graph a "graph y = …" request gets, through the
same builder. Formula series beside data series are sampled into points over the
data's x range, so a best-fit line given as ``"fn": "2x + 0.1"`` still draws. A
formula SymPy cannot read leaves a note where the chart was, never a blank card.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import GraphSampleInput
from app.modules.math.tools.block import verified_curves
from app.services.md_fence_scan import iter_fences

CHART_FENCE_LANGS = ("chart", "vega", "vega-lite", "plot")
CHART_FAIL_NOTE = "*Could not draw that chart.*"
_FORMULA_KEYS = ("fn", "expr", "expression", "function", "formula", "equation")
_DOMAIN_KEYS = ("domain", "x_range", "xRange", "x_domain", "xDomain", "range")
_MAX_GRAPH_CURVES = 2
_SAMPLES = 50
_DEFAULT_SPAN = (-10.0, 10.0)
# Chart types a sampled chart keeps; "function" and the like become a line chart.
_DATA_TYPES = ("line", "scatter", "point", "bar", "area")
# A curve's own name for y ("y =", "f(x) ="), and JavaScript / Vega spellings.
_LEFT_SIDE = re.compile(r"^\s*(?:y|f\s*\(\s*x\s*\))\s*=\s*", re.IGNORECASE)
_SPELLINGS = (
    (re.compile(r"\bMath\.PI\b|\bPI\b"), "pi"),
    (re.compile(r"\bMath\.E\b"), "E"),
    (re.compile(r"\bMath\."), ""),
    # Vega's log is the natural log; a bare log reads as base 10 here.
    (re.compile(r"\blog\("), "ln("),
)


@dataclass(frozen=True)
class _FormulaChart:
    curves: tuple[tuple[str, str], ...]  # (name, expression in x)
    points_series: tuple[dict[str, Any], ...]  # series the model gave as points
    x_min: float | None
    x_max: float | None


def has_formula_chart(content: str) -> bool:
    """Cheap: a chart fence whose text names a formula key or a sequence."""
    for fence in iter_fences(content):
        if fence.closed and fence.lang in CHART_FENCE_LANGS:
            body = content[fence.body_start : fence.body_end]
            if any(f'"{key}"' in body for key in (*_FORMULA_KEYS, "sequence")):
                return True
    return False


def _bound(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        try:
            number = float(math_solve.parse_expression(value.strip(), []))
        except Exception:
            return None
        return number if math.isfinite(number) else None
    return None


def _domain(*holders: object) -> tuple[float | None, float | None]:
    """The first x range a series or the chart names: ``[0, 6.28]``, ``x_min``/``x_max``."""
    for holder in holders:
        if not isinstance(holder, dict):
            continue
        for key in _DOMAIN_KEYS:
            pair = holder.get(key)
            if isinstance(pair, list) and len(pair) == 2:
                low, high = _bound(pair[0]), _bound(pair[1])
                if low is not None and high is not None and low < high:
                    return low, high
        low = _bound(holder.get("x_min", holder.get("xmin", holder.get("min"))))
        high = _bound(holder.get("x_max", holder.get("xmax", holder.get("max"))))
        if low is not None and high is not None and low < high:
            return low, high
    return None, None


def _expression(raw: str, variable: str = "x") -> str:
    """A formula as SymPy reads it: ``Math.sin(datum.t)`` → ``sin(x)``, ``x^2`` → ``x**2``."""
    text = re.sub(rf"\bdatum\.{re.escape(variable)}\b", "x", raw)
    for pattern, spelling in _SPELLINGS:
        text = pattern.sub(spelling, text)
    return _LEFT_SIDE.sub("", text).replace("^", "**").strip()


def _formula(item: dict[str, Any]) -> str | None:
    for key in _FORMULA_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _expression(value)
    return None


def _series_chart(spec: dict[str, Any]) -> _FormulaChart | None:
    series = spec.get("series")
    items = series if isinstance(series, list) else [spec]
    curves: list[tuple[str, str]] = []
    points: list[dict[str, Any]] = []
    x_min = x_max = None
    for item in items:
        if not isinstance(item, dict):
            return None
        formula = _formula(item)
        if formula is None:
            if not isinstance(item.get("points"), list):
                return None
            points.append(item)
            continue
        name = item.get("name") if isinstance(item.get("name"), str) else None
        curves.append((name or f"y = {formula}", formula))
        if x_min is None:
            x_min, x_max = _domain(item)
    if not curves:
        return None
    if x_min is None:
        x_min, x_max = _domain(spec, spec.get("x_axis"), spec.get("xAxis"))
    return _FormulaChart(tuple(curves), tuple(points), x_min, x_max)


def _sequence_chart(spec: dict[str, Any]) -> _FormulaChart | None:
    data = spec.get("data")
    sequence = data.get("sequence") if isinstance(data, dict) else None
    if not isinstance(sequence, dict):
        return None
    named = sequence.get("as")
    # Vega-Lite names a sequence's field "data" unless it says otherwise.
    variable = named if isinstance(named, str) else "data"
    transform = spec.get("transform")
    steps: list[Any] = transform if isinstance(transform, list) else []
    curves = tuple(
        (str(step.get("as") or "y"), _expression(step["calculate"], variable))
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("calculate"), str)
    )
    if not curves:
        return None
    return _FormulaChart(curves, (), _bound(sequence.get("start")), _bound(sequence.get("stop")))


def read_formula_chart(spec: dict[str, Any]) -> _FormulaChart | None:
    """The curves a chart spec plots as formulas, or None when it plots data only."""
    return _sequence_chart(spec) or _series_chart(spec)


def _point_x(point: object) -> float | None:
    x = point[0] if isinstance(point, list) and point else None
    if isinstance(point, dict):
        x = point.get("x")
    return float(x) if isinstance(x, int | float) and not isinstance(x, bool) else None


def _data_x_range(series: tuple[dict[str, Any], ...]) -> tuple[float, float] | None:
    xs = [x for item in series for point in item["points"] if (x := _point_x(point)) is not None]
    return (min(xs), max(xs)) if xs and min(xs) < max(xs) else None


def _sampled_chart(spec: dict[str, Any], chart: _FormulaChart) -> str | None:
    """The chart with each formula series sampled into points: across the data's x
    range beside data series, else across the chart's domain."""
    span = _data_x_range(chart.points_series)
    if span is None and chart.x_min is not None and chart.x_max is not None:
        span = (chart.x_min, chart.x_max)
    low, high = span or _DEFAULT_SPAN
    sampled: list[dict[str, Any]] = []
    for name, expr in chart.curves:
        try:
            sample = math_solve.sample_function(
                GraphSampleInput(expr=expr, variable="x", x_min=low, x_max=high, n=_SAMPLES)
            )
        except Exception:
            return None
        sampled.append({"name": name, "type": "line", "points": sample.points})
    out = {key: value for key, value in spec.items() if key not in ("series", *_FORMULA_KEYS)}
    out["type"] = out.get("type") if out.get("type") in _DATA_TYPES else "line"
    out["series"] = [*chart.points_series, *sampled]
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False)


def _redraw(spec: dict[str, Any], settings: Settings) -> str | None:
    """The fence to put in this chart's place, or None to leave the chart as it is.

    One or two curves alone are a ```graph (the phone's function plot); curves beside
    data, or more than two, stay a chart whose curve points SymPy sampled.
    """
    chart = read_formula_chart(spec)
    if chart is None:
        return None
    if not chart.points_series and len(chart.curves) <= _MAX_GRAPH_CURVES:
        exprs = tuple(expr for _name, expr in chart.curves)
        graph = verified_curves(exprs, chart.x_min, chart.x_max, settings)
        if graph is not None:
            return f"```graph\n{json.dumps(graph, separators=(',', ':'))}\n```\n"
        return f"{CHART_FAIL_NOTE}\n"
    sampled = _sampled_chart(spec, chart)
    return f"```chart\n{sampled}\n```\n" if sampled else f"{CHART_FAIL_NOTE}\n"


def _chart_json(body: str) -> dict[str, Any] | None:
    start = body.find("{")
    if start == -1:
        return None
    try:
        value, _end = json.JSONDecoder().raw_decode(body[start:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def formula_charts_to_graphs(content: str, settings: Settings) -> str:
    """Every chart fence that plots a formula, redrawn from SymPy's samples."""
    pieces: list[str] = []
    cursor = 0
    for fence in iter_fences(content):
        if not fence.closed or fence.lang not in CHART_FENCE_LANGS:
            continue
        spec = _chart_json(content[fence.body_start : fence.body_end])
        replacement = _redraw(spec, settings) if spec is not None else None
        if replacement is None:
            continue
        pieces.append(content[cursor : fence.start])
        pieces.append(replacement)
        cursor = fence.end
    pieces.append(content[cursor:])
    return "".join(pieces)
