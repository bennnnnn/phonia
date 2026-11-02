"""A numeric chart turn: what reads as one, and the one chart contract.

The phone draws a ```chart fence with Vega-Lite whose data is written inline
(``apps/mobile/lib/chartSpec.ts``); anything else shows the chart's data as a table
instead. ``CHART_FORMAT_HINT`` names only the shapes it draws. Their examples are
``chart_shapes.json``, and the phone's tests draw every one of them
(``apps/mobile/lib/__tests__/chartShapes.test.ts``), so the hint cannot promise a
shape the phone leaves blank. A curve y = f(x) is not one of them: the server samples
it with SymPy (``modules/math/chart_formula.py``).
"""

import json
from pathlib import Path

CHART_SHAPES: dict[str, dict[str, object]] = json.loads(
    Path(__file__).with_name("chart_shapes.json").read_text(encoding="utf-8")
)


def _shape_lines() -> str:
    return "\n".join(
        f"{name}:\n```chart\n{json.dumps(spec, separators=(',', ':'), ensure_ascii=False)}\n```"
        for name, spec in CHART_SHAPES.items()
    )


CHART_FORMAT_HINT = (
    "This turn is a numeric chart. Recall renders Vega-Lite in the bubble — "
    "you CAN draw this chart. NEVER say you cannot draw / cannot literally "
    "draw a chart. NEVER substitute a markdown table, mermaid, or ASCII bars.\n"
    "Lead with a ```chart fence of Vega-Lite JSON. At most one short sentence "
    "before the fence. No joke setup. No leftover bare numbers and no "
    "```answer / ```result fence.\n"
    "If they gave numbers, use those as data.values in that order. "
    "If they asked for an example or a generic chart with no series, a short "
    "labelled sample is fine — say it is sample data in that one sentence. "
    "If they asked to chart their real/my data and gave no numbers, ask ONE "
    "question for the values. Do not invent a sample and treat that as the answer.\n"
    "If they also asked for a statistic or explanation, put that after the fence. "
    "Do not stop immediately after the chart unless they only asked for the drawing.\n"
    "The app draws only these shapes; use the one asked for and keep its structure:\n"
    '- bar: named categories (months, items) on y with "sort": null (horizontal bars) '
    "so labels stay visible; grouped series dodge with yOffset.\n"
    '- line or area: x in data order ("sort": null on a named x), one line per series '
    "by color.\n"
    "- scatter: mark point, x and y quantitative. A best-fit or trend line is a second "
    "layer with the regression transform: the app fits it to the data, so never compute "
    "or write the line's points yourself.\n"
    '- histogram: the raw values as data.values, x with "bin", y '
    '{"aggregate": "count"}. Never pre-bin the values, never "bin": "binned".\n'
    "- pie: mark arc, theta is the number, color is the category.\n"
    "- box plot: mark boxplot over the raw values as data.values, one row per value; a "
    "category on x gives one box per group, no x gives one box. Never compute the "
    "quartiles or whiskers yourself.\n"
    "Every chart: first key "
    '"$schema": "https://vega.github.io/schema/vega-lite/v5.json"; every value inline '
    "in data.values (no url, no data.sequence, no column computed from a formula); "
    "no tooltip; one complete JSON object with nothing after its closing brace; never "
    "Chart.js or another format.\n"
    "A curve y = f(x) is not data: never sample or compute its points. Write it as "
    '```chart {"type":"function","series":[{"name":"y = sin(x)","fn":"sin(x)"}],'
    '"domain":[0,6.2832]} (one or two series) and Recall draws it from the formula.\n'
    f"{_shape_lines()}"
)


def with_chart_followup(layout: str | None, data: str | None) -> str | None:
    """The chart hint, with the earlier message whose numbers "graph it" draws. "Yes" to a
    chart the last reply offered has no layout of its own, so it gets the chart hint."""
    if data is None or layout not in (None, CHART_FORMAT_HINT):
        return layout
    if not data:
        return CHART_FORMAT_HINT
    return (
        f"{CHART_FORMAT_HINT}\n"
        f"The numbers to chart are in the user's earlier message: «{data}». Use them "
        "as data.values; do not ask for the values or which function to graph."
    )
