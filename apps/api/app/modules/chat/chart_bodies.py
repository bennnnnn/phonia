"""Whether the phone draws a ```chart body: the phone's readers, as the server reads them.

The phone draws Vega-Lite (or Vega) with its data inline and reads three other shapes
models write (``apps/mobile/lib/chartSpec.ts``): a series of points (and a box plot's
series of values), a Chart.js config, and category labels with series of numbers in the
many spellings models use. The server's check used to pass any body with a list in it,
so "labels with values of another length" reached the phone and drew "Could not render
that chart." with nothing under it, and a body the phone recovers from (a stray brace
after the JSON) was swapped for a table. ``docs/fixtures/chart_bodies.json`` holds bodies
both sides judge, so they cannot drift apart.
"""

from __future__ import annotations

import json
import math
from typing import Any

_CHILD_KEYS = ("layer", "hconcat", "vconcat", "concat")
_SPEC_KEYS = ("mark", "layer", "$schema", "marks", "encoding")
_BOX_TYPES = frozenset(
    {"box", "boxplot", "box plot", "box-plot", "box and whisker", "box-and-whisker"}
)
_PIE_TYPES = frozenset({"pie", "donut", "doughnut"})
_LABEL_KEYS = ("labels", "categories", "x")
_AXIS_LABEL_KEYS = ("labels", "categories", "values", "data")
_SERIES_KEYS = ("series", "datasets")
_VALUE_KEYS = ("values", "data", "y")


def _closing_brace(raw: str, open_at: int) -> int:
    depth = 0
    in_string = False
    index = open_at
    while index < len(raw):
        char = raw[index]
        if in_string:
            if char == "\\":
                index += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _no_constant(name: str) -> Any:
    raise ValueError(name)


def _loads(text: str) -> Any:
    """JSON as the phone's ``JSON.parse`` reads it: ``NaN`` and ``Infinity`` are not JSON."""
    try:
        return json.loads(text, parse_constant=_no_constant)
    except (ValueError, RecursionError):  # brackets nested past Python's stack
        return None


def parse_chart_body(raw: str) -> Any:
    """The JSON in a body, as the phone reads it: prose around the object and anything
    after its closing brace are dropped (``chartSeriesSpec.ts parseChartBody``)."""
    whole = _loads(raw)
    if whole is not None:
        return whole
    open_at = raw.find("{")
    if open_at < 0:
        return None
    close = _closing_brace(raw, open_at)
    first = _loads(raw[open_at : close + 1]) if close >= 0 else None
    if first is not None:
        return first
    last = raw.rfind("}")
    return _loads(raw[open_at : last + 1]) if last > open_at else None


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _label(value: Any) -> bool:
    return isinstance(value, str) or _number(value)


def _inline_values(spec: dict[str, Any]) -> bool:
    """Vega-Lite ``data.values``, Vega ``data: [{values}]``, named ``datasets``, children."""
    data = spec.get("data")
    for dataset in data if isinstance(data, list) else [data]:
        if isinstance(dataset, dict) and isinstance(dataset.get("values"), list):
            if dataset["values"]:
                return True
    datasets = spec.get("datasets")
    if isinstance(datasets, dict) and any(
        isinstance(rows, list) and rows for rows in datasets.values()
    ):
        return True
    for key in _CHILD_KEYS:
        children = spec.get(key)
        if isinstance(children, list) and any(
            isinstance(child, dict) and _inline_values(child) for child in children
        ):
            return True
    inner = spec.get("spec")
    return isinstance(inner, dict) and _inline_values(inner)


def _point(value: Any) -> bool:
    pair = (
        value
        if isinstance(value, list)
        else [value.get("x"), value.get("y")]
        if isinstance(value, dict)
        else None
    )
    return pair is not None and len(pair) >= 2 and _number(pair[0]) and _number(pair[1])


def _points_series(spec: dict[str, Any]) -> bool | None:
    """``{"series": [{"points": [[x, y]]}]}`` or a box plot's ``series[].values``."""
    if any(key in spec for key in ("mark", "layer", "$schema", "data")):
        return None
    series = spec.get("series")
    if not isinstance(series, list) or not series:
        return None
    if str(spec.get("type") or "").lower() in _BOX_TYPES:
        count = 0
        for entry in series:
            raw = entry.get("values", entry.get("data")) if isinstance(entry, dict) else None
            if not isinstance(raw, list) or not all(_number(value) for value in raw):
                return None
            count += len(raw)
        return True if count else None
    count = 0
    for line in series:
        if not isinstance(line, dict) or not isinstance(line.get("points"), list):
            return None
        if not all(_point(point) for point in line["points"]):
            return None
        count += len(line["points"])
    return count > 0


def _chart_js(spec: dict[str, Any]) -> bool | None:
    """``{"type", "data": {"labels", "datasets": [{"label", "data"}]}}``."""
    data = spec.get("data")
    if not isinstance(data, dict):
        return None
    datasets = data.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        return None
    count = 0
    for dataset in datasets:
        if not isinstance(dataset, dict) or not isinstance(dataset.get("data"), list):
            return None
        for item in dataset["data"]:
            if item is None:
                continue
            if not (_point(item) or _number(item)):
                return None
            count += 1
    return count > 0


def _first_list(block: Any, keys: tuple[str, ...]) -> list[Any] | None:
    if not isinstance(block, dict):
        return None
    for key in keys:
        if isinstance(block.get(key), list):
            return list(block[key])
    return None


def _axis_block(spec: dict[str, Any], axis: str) -> Any:
    for key in (f"{axis}Axis", f"{axis}_axis", f"{axis}axis"):
        if key in spec:
            return spec[key]
    return None


def _labelled_point(value: Any) -> bool:
    if _point(value):
        return True
    if isinstance(value, list) and len(value) == 2:
        return isinstance(value[0], str) and _number(value[1])
    if not isinstance(value, dict):
        return False
    # The phone's ``??``: the first of these that is set.
    x = next(
        (value[key] for key in ("x", "name", "label", "category") if value.get(key) is not None),
        None,
    )
    y = value["y"] if value.get("y") is not None else value.get("value")
    return _label(x) and _number(y)


def _values_read(values: list[Any], labels: list[Any] | None) -> int | None:
    """How many points one series gives against the labels, or None when it gives none."""
    if any(_number(value) for value in values) and (labels is None or len(labels) != len(values)):
        return None
    count = 0
    for value in values:
        if value is None:
            continue
        if isinstance(value, int | float) and not isinstance(value, bool):
            if not _number(value) or labels is None:
                return None
        elif not _labelled_point(value):
            return None
        count += 1
    return count


def _category_series(spec: dict[str, Any]) -> bool | None:
    """Labels (``labels``, ``categories``, ``x`` or an x-axis block) and series of numbers."""
    if any(key in spec for key in _SPEC_KEYS) or isinstance(spec.get("data"), dict):
        return None
    labels = _first_list(spec, _LABEL_KEYS)
    if labels is None:
        labels = _first_list(_axis_block(spec, "x"), _AXIS_LABEL_KEYS)
    if labels is not None and not all(_label(label) for label in labels):
        return None
    series: list[list[Any]] | None = None
    for key in _SERIES_KEYS:
        items = spec.get(key)
        if not isinstance(items, list) or not items:
            continue
        if not any(isinstance(item, dict) for item in items):
            series = [items]
            break
        series = []
        for item in items:
            values = _first_list(item, _VALUE_KEYS)
            if values is None:
                return None
            series.append(values)
        break
    if series is None:
        top = _first_list(spec, _VALUE_KEYS)
        if top is None:
            return None
        series = [top]
    chart = spec.get("chart")
    chart_type = str(
        spec.get("type") or (chart.get("type") if isinstance(chart, dict) else "") or ""
    ).lower()
    if chart_type in _PIE_TYPES:
        series = series[:1]
    counts = [_values_read(values, labels) for values in series]
    if any(count is None for count in counts) or not sum(c or 0 for c in counts):
        return None
    return True


def chart_body_draws(body: str) -> bool:
    """True when the phone draws ``body``: a dialect it reads, or a spec with inline data."""
    spec = parse_chart_body(body)
    if not isinstance(spec, dict):
        return False
    for reader in (_points_series, _chart_js, _category_series):
        read = reader(spec)
        if read is not None:
            return read
    return _inline_values(spec)
