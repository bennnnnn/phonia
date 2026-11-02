"""A ```chart body written as loose text, read into JSON the phone draws.

Qwen3.7 Flash, the free plan's everyday model, does not keep to the chart format it is
given. Six replies to "make that a bar chart" after a month-by-month rainfall list
(2026-10-24) wrote Chart.js JSON, YAML with a ``data`` list of label/value pairs, YAML
with an ``xAxis`` list and ``series``, a mermaid-like block (``bar``, ``title "…"``, then
``Jan: 15`` lines) and JavaScript object literals (``{label: "Jan", value: 15}``). The
phone draws JSON only, so each but the first showed "Could not render that chart", and
the server dropped it, leaving an empty reply when the chart was all of it.

Each holds the same labels and numbers. Read as YAML, once its header word and its
``key "value"`` lines are written as YAML keys, it becomes the label/series JSON
``chart_bodies`` already reads, and only a body that check passes replaces the text.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

import yaml

from app.modules.chat.chart_bodies import chart_body_draws, parse_chart_body

# A first line naming the chart alone: "bar", "pie chart", "xychart-beta".
_HEADER = re.compile(
    r"^(?P<kind>bar|column|line|area|pie|donut|doughnut|scatter|histogram)"
    r"(?:\s*(?:charts?|graphs?|plots?))?\s*:?$|^xychart(?:-beta)?$",
    re.IGNORECASE,
)
# ``title "Monthly rainfall"``, ``y-axis "mm" 0 --> 300``: a key and its quoted value.
_KEY_QUOTED = re.compile(r"""^(\s*)([A-Za-z][\w-]*)\s+("[^"\n]*"|'[^'\n]*')(?:\s.*)?$""")
# ``data [``, ``x-axis [Jan, Feb]``, ``bar [15, 30]``: a key and a list or mapping.
_KEY_OPENS = re.compile(r"^(\s*)([A-Za-z][\w-]*)\s+([\[{].*)$")
_AXIS_SPELLINGS = ("{}Axis", "{}-axis", "{}_axis", "{}axis", "{}AxisLabel", "{}_axis_label")
_MARK_KEYS = ("bar", "line", "area")
_LABEL_KEYS = ("labels", "categories", "x")
# A chart's text is a few hundred characters; past this it is not one to read (PyYAML
# took a third of a second on 20,000 characters of brackets, on the event loop).
_MAX_CHARS = 6_000
# Chart data nests a few brackets deep; PyYAML's time grew with the square of the depth.
_MAX_DEPTH = 20


# PyYAML ships no type stubs here, so its SafeLoader reads as Any to mypy.
class _Loader(yaml.SafeLoader):  # type: ignore[misc]
    """YAML whose plain words stay words: a chart's labels are names ("No", "2024-01",
    "1:30"), never YAML 1.1's yes/no booleans, dates or base-60 numbers. No aliases:
    ``*a`` repeats a node by reference, and written out as JSON a few lines grew without
    bound."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("a chart has no aliases")
        return super().compose_node(parent, index)


_Loader.yaml_implicit_resolvers = {
    first: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag.rsplit(":", 1)[-1] not in {"bool", "int", "float", "timestamp"}
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^[-+]?(?:0|[1-9][0-9]*)$"), list("-+0123456789")
)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(
        r"^[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?$|^[-+]?[0-9]+[eE][-+]?[0-9]+$"
    ),
    list("-+.0123456789"),
)


def _yaml_text(body: str) -> tuple[str, str | None]:
    """The body as YAML, and the chart kind its header line named."""
    lines = body.strip("\n").splitlines()
    kind: str | None = None
    if lines and (header := _HEADER.match(lines[0].strip())):
        kind = (header.group("kind") or "").lower() or None
        rest = [line for line in lines[1:] if line.strip()]
        indent = min((len(line) - len(line.lstrip()) for line in rest), default=0)
        lines = [line[indent:] if line[:indent].isspace() else line for line in lines[1:]]
    written = []
    for line in lines:
        match = _KEY_QUOTED.match(line) or _KEY_OPENS.match(line)
        written.append(f"{match[1]}{match[2]}: {match[3]}" if match else line)
    return "\n".join(written), kind


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _labels(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, str | int) for v in value)


def _reshaped(spec: dict[str, Any], kind: str | None) -> dict[str, Any]:
    """Loose keys as ``chart_bodies`` reads them: labels, series and label/value rows."""
    out = dict(spec)
    if kind and "type" not in out:
        out["type"] = kind
    for axis in ("x", "y"):
        named = [out[key.format(axis)] for key in _AXIS_SPELLINGS if key.format(axis) in out]
        # ``y_axis "Rainfall (mm)"``: the axis's title, which the phone reads as ``yLabel``.
        title = next((value for value in named if isinstance(value, str)), None)
        if title and f"{axis}Label" not in out:
            out[f"{axis}Label"] = title
        # ``xAxis: [Jan, Feb]``: the labels.
        labels = next((value for value in named if _labels(value)), None)
        if axis == "x" and labels and not any(isinstance(out.get(k), list) for k in _LABEL_KEYS):
            out["labels"] = labels
    # Mermaid's xychart: ``bar [15, 30]``, ``line [12, 25]``, one series each.
    marks = [k for k in _MARK_KEYS if isinstance(out.get(k), list) and all(map(_number, out[k]))]
    if marks and "series" not in out:
        out["series"] = [{"name": key, "data": out.pop(key)} for key in marks]
        out.setdefault("type", marks[0])
    for key in ("data", "values"):
        rows = out.get(key)
        # ``data:`` then ``Jan: 15`` lines: one row per label.
        if isinstance(rows, dict) and len(rows) >= 2 and all(map(_number, rows.values())):
            out[key] = [{"label": str(label), "value": value} for label, value in rows.items()]
    return out


def loose_chart_json(body: str) -> str | None:
    """JSON the phone draws for a body written as loose text, or None. Never raises: it
    runs in the finalize pass, on whatever the model wrote.

    A body that already parses as JSON is the JSON checks' to judge, never rewritten. JSON
    with a stray brace is mended; anything else is read as YAML.
    """
    if len(body) > _MAX_CHARS or parse_chart_body(body) is not None:
        return None
    try:
        return _read(body)
    # YAML's own errors, an explicit tag with a bad value ("!!float abc" is a ValueError,
    # "!!bool maybe" a KeyError), an integer too long for a float, brackets nested past
    # Python's stack: each is a body with no chart in it.
    except Exception:
        return None


def _too_deep(text: str) -> bool:
    depth = 0
    for char in text:
        if char in "[{":
            depth += 1
            if depth > _MAX_DEPTH:
                return True
        elif char in "]}":
            depth = max(0, depth - 1)
    return False


def _without_stray_braces(body: str) -> str | None:
    """JSON with a brace opened where a key belongs, and its closing brace, taken out, or
    None when it has none. Live: ``"encoding": {"x": {…}, {"y": {…}}}`` drew nothing."""
    out: list[str] = []
    # "{" and "[" as written; "~" a stray brace, whose keys belong to the object around it.
    stack: list[str] = []
    last = ""  # the last character outside a string, spaces aside
    in_string = escaped = stray = False
    for char in body:
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == "{" and stack and stack[-1] in "{~" and last in "{,":
            stack.append("~")
            stray = True
            continue
        if char in "}]" and stack and stack.pop() == "~":
            continue
        if char in "{[":
            stack.append(char)
        in_string = char == '"'
        out.append(char)
        last = last if char.isspace() else char
    return "".join(out) if stray else None


def _no_repeated_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _value in pairs]
    if len(set(keys)) < len(keys):
        raise ValueError("a key twice")
    return dict(pairs)


def _one_line(text: str) -> str | None:
    """Mended JSON on one line, or None when it does not parse or an object holds a key
    twice: a forgotten "layer": [ merged two marks, and the last one drew alone."""
    try:
        return json.dumps(json.loads(text, object_pairs_hook=_no_repeated_keys), ensure_ascii=False)
    except ValueError:
        return None


def _read(body: str) -> str | None:
    if _too_deep(body):
        return None
    unnested = _without_stray_braces(body)
    if unnested is not None and (mended := _one_line(unnested)) and chart_body_draws(mended):
        return mended
    text, kind = _yaml_text(body)
    loaded = yaml.load(text, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
    if isinstance(loaded, list):
        loaded = {"data": loaded}
    if not isinstance(loaded, dict):
        return None
    spec = json.dumps(_reshaped(loaded, kind), ensure_ascii=False)
    return spec if chart_body_draws(spec) else None
