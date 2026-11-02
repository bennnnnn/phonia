"""A ```chart the phone cannot draw becomes the table it holds, or goes."""

from __future__ import annotations

import json

import pytest

from app.modules.chat.chart_sanitize import chart_is_drawable, sanitize_chart_fences

# Live: "whats 72 fahrenheit in celsius" got this above the answer, and the phone
# showed "Could not render that chart".
_LIVE = (
    '```chart\ntype: scatter\ntitle: "Temperature Conversion"\ndata: |\n'
    "  Fahrenheit (°F) | Celsius (°C)\n  --------------- | ------------\n"
    "  32              | 0\n  72              | 22.2\n```\n\n"
    "$C = \\frac{5}{9}(72 - 32) \\approx 22.2^\\circ\\text{C}$."
)


@pytest.mark.parametrize(
    "spec",
    [
        # Vega-Lite, Vega, a layered chart, Chart.js and a series chart all draw.
        {"$schema": "vl", "mark": "bar", "data": {"values": [{"x": "a", "y": 1}]}},
        {"data": [{"name": "t", "values": [{"x": 1}]}], "marks": []},
        {"layer": [{"mark": "line", "data": {"values": [{"x": 1, "y": 2}]}}]},
        {"type": "bar", "data": {"labels": ["a"], "datasets": [{"data": [1]}]}},
        {"type": "line", "series": [{"name": "s", "points": [[0, 1]]}]},
    ],
)
def test_a_chart_with_its_data_inline_is_kept(spec: dict[str, object]) -> None:
    text = f"Here:\n\n```chart\n{json.dumps(spec)}\n```\n\nDone."
    assert chart_is_drawable(json.dumps(spec))
    assert sanitize_chart_fences(text) == text


def test_a_broken_chart_becomes_the_table_it_holds() -> None:
    assert sanitize_chart_fences(_LIVE) == (
        "| Fahrenheit (°F) | Celsius (°C) |\n|---|---|\n| 32 | 0 |\n| 72 | 22.2 |\n\n"
        "$C = \\frac{5}{9}(72 - 32) \\approx 22.2^\\circ\\text{C}$."
    )


@pytest.mark.parametrize(
    "body",
    [
        '{"mark": "line", "data": {"url": "data.csv"}}',
        '{"mark": "line", "data": {"sequence": {"start": 0, "stop": 10}}}',
        '{"mark": "line", "data": {"values": []}}',
        "type: bar\nvalues: 1, 2, 3",
        "",
    ],
)
def test_a_chart_with_nothing_to_draw_goes(body: str) -> None:
    assert (
        sanitize_chart_fences(f"Look:\n\n```chart\n{body}\n```\n\nThe end.") == "Look:\n\nThe end."
    )


def test_other_fences_are_left_alone() -> None:
    text = "```python\nprint('a | b')\n```\n\n```mermaid\ngraph TD; A-->B\n```\n"
    assert sanitize_chart_fences(text) == text


def test_a_chart_written_as_loose_text_is_rewritten_as_json_the_phone_draws() -> None:
    """Qwen wrote "make that a bar chart" as YAML; it was dropped and the reply saved empty."""
    loose = "type: bar\ntitle: Rainfall\ndata:\n  - label: Jan\n    value: 15\n  - label: Feb\n    value: 30"
    kept = sanitize_chart_fences(f"Here it is:\n\n```chart\n{loose}\n```\n\nFeb is wetter.")
    before, body, after = kept.split("```")
    assert (before, after) == ("Here it is:\n\n", "\n\nFeb is wetter.")
    assert body.startswith("chart\n") and chart_is_drawable(body.removeprefix("chart\n"))
    assert json.loads(body.removeprefix("chart\n"))["data"][1] == {"label": "Feb", "value": 30}


@pytest.mark.parametrize("body", ['{"mark": "line", "data": {"url": "data.csv"}}', "nothing here"])
def test_a_reply_that_is_only_an_undrawable_chart_stays_as_written(body: str) -> None:
    """Dropped, it was saved empty while the phone kept the chart it had streamed."""
    reply = f"```chart\n{body}\n```"
    assert sanitize_chart_fences(reply) == reply


def test_a_rewritten_chart_in_a_list_item_keeps_its_indent() -> None:
    """At the margin, the JSON line ended the list item and left an empty chart."""
    reply = (
        "1. Rainfall by month:\n\n   ```chart\n   type: bar\n   data:\n     - label: Jan\n"
        "       value: 15\n     - label: Feb\n       value: 30\n   ```\n\n2. Jul is wettest."
    )
    kept = sanitize_chart_fences(reply).splitlines()
    assert kept[2] == "   ```chart"
    assert kept[3].startswith('   {"type": "bar"') and chart_is_drawable(kept[3])
    assert kept[4:] == ["   ```", "", "2. Jul is wettest."]


def test_a_mended_chart_in_a_list_item_keeps_one_indent() -> None:
    """The mended body came back with its own indent, and the fence's was added again."""
    body = (
        '{"mark":"bar","data":{"values":[{"a":"x","b":1}]},'
        '"encoding":{"x":{"field":"a"},{"y":{"field":"b"}}}}'
    )
    reply = f"1. The chart:\n\n   ```chart\n   {body}\n   ```\n\n2. Done."
    kept = sanitize_chart_fences(reply).splitlines()
    assert kept[2] == "   ```chart" and kept[4:] == ["   ```", "", "2. Done."]
    assert kept[3].startswith("   {") and not kept[3].startswith("    ")
    assert chart_is_drawable(kept[3])


def test_a_chart_that_breaks_the_readers_goes_without_an_error() -> None:
    """A bad YAML tag raised a ValueError, and brackets nested deep a RecursionError."""
    reply = "Here:\n\n```chart\ntype: bar\ndata:\n  Jan: !!float abc\n  Feb: 2\n```\n\nDone."
    assert sanitize_chart_fences(reply) == "Here:\n\nDone."
    assert not chart_is_drawable("[" * 19999)
