"""A chart written as loose text is read into JSON the phone draws.

Qwen3.7 Flash answered "make that a bar chart" after a rainfall list (2026-10-24) with these
bodies, each a different made-up format around the same months and numbers; the phone
showed "Could not render that chart" for every one, and the server dropped it. The JSON
the server writes for each is in ``docs/fixtures/chart_bodies.json``, which the phone's
tests draw.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.modules.chat.chart_bodies import chart_body_draws
from app.modules.chat.chart_loose import loose_chart_json

_FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "chart_bodies.json"
_DRAWN = {entry["name"]: entry["body"] for entry in json.loads(_FIXTURE.read_text())}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MM = (15, 30, 60, 85, 80, 135, 280, 290, 190, 30, 6, 5)
_TITLE = "Monthly Rainfall in Addis Ababa (mm)"

_LIVE = {
    "a mermaid-like block with label: number lines": (
        f'bar\n  title "{_TITLE}"\n  x_axis "Month"\n  y_axis "Rainfall (mm)"\n  \n  data:\n'
        + "\n".join(f"    {month}: {mm}" for month, mm in zip(_MONTHS, _MM, strict=True))
    ),
    "JavaScript object literals after a header word": (
        f'bar\ntitle "{_TITLE}"\nyAxis "Rainfall (mm)"\ndata [\n'
        + ",\n".join(f'  {{label: "{m}", value: {mm}}}' for m, mm in zip(_MONTHS, _MM, strict=True))
        + "\n]"
    ),
    "YAML with an x-axis list and series": (
        f"type: bar\ntitle: {_TITLE}\nxAxis: [{', '.join(_MONTHS)}]\nyAxis:\n"
        "  label: Rainfall (mm)\n  min: 0\n  max: 350\n  step: 50\nseries:\n  - name: Rainfall\n"
        f"    data: [{', '.join(map(str, _MM))}]\n    color: #4A90E2"
    ),
    "YAML label/value rows": f"type: bar\ntitle: {_TITLE}\ndata:\n"
    + "\n".join(
        f"  - label: {month}\n    value: {mm}" for month, mm in zip(_MONTHS, _MM, strict=True)
    ),
    "mermaid xychart bars and a line": (
        'xychart-beta\n  title "Sales"\n  x-axis [Jan, Feb, Mar]\n  y-axis "Revenue" 0 --> 100\n'
        "  bar [10, 20, 30]\n  line [12, 18, 25]"
    ),
}


@pytest.mark.parametrize("name", list(_LIVE))
def test_a_loose_chart_becomes_json_the_phone_draws(name: str) -> None:
    read = loose_chart_json(_LIVE[name])
    assert read is not None
    assert chart_body_draws(read)
    # The phone's tests draw this exact body.
    assert read == _DRAWN[f"{name} (loose text, as the server writes it)"]


def test_the_months_numbers_and_titles_come_through() -> None:
    read = json.loads(
        loose_chart_json(_LIVE["a mermaid-like block with label: number lines"]) or ""
    )
    assert [row["label"] for row in read["data"]] == list(_MONTHS)
    assert [row["value"] for row in read["data"]] == list(_MM)
    assert (read["type"], read["title"], read["yLabel"]) == ("bar", _TITLE, "Rainfall (mm)")


@pytest.mark.parametrize(
    ("body", "labels"),
    [
        # YAML 1.1 reads these as a boolean, a date and a base-60 number: they are labels.
        ("type: bar\ndata:\n  No: 3\n  Yes: 5", ["No", "Yes"]),
        ("bar\ndata:\n  2024-01: 5\n  2024-02: 7", ["2024-01", "2024-02"]),
        ("type: bar\nlabels: [1:30, 2:00]\ndata: [4, 6]", None),
    ],
)
def test_labels_stay_the_words_written(body: str, labels: list[str] | None) -> None:
    read = json.loads(loose_chart_json(body) or "")
    if labels is None:
        assert read["labels"] == ["1:30", "2:00"]
    else:
        assert [row["label"] for row in read["data"]] == labels


@pytest.mark.parametrize(
    "body",
    [
        # An explicit tag with a bad value, an integer too long for a float: no chart, no
        # error (the finalize pass this runs in must not raise).
        "type: bar\ndata:\n  Jan: !!float abc\n  Feb: 2",
        "Jan: !!int x\nFeb: 2",
        'Jan: !!int ""',
        "Jan: !!bool maybe",
        "Jan: !!timestamp soon",
        "type: bar\ndata:\n  Jan: " + "9" * 400 + "\n  Feb: 2",
        "xychart-beta\n  bar [" + "9" * 400 + ", 2]",
        # JSON is the JSON checks' to judge, drawable or not.
        '{"type": "bar", "data": {"labels": ["a"], "datasets": [{"data": [1]}]}}',
        '{"mark": "line", "data": {"url": "data.csv"}}',
        # Nothing to draw: words, a table as text, a series with no numbers.
        "just some words about rainfall",
        "type: scatter\ndata: |\n  F | C\n  32 | 0\n  72 | 22.2",
        "type: bar\ndata:\n  - label: Jan\n    value: lots",
        "",
        # Aliases repeat a node by reference: written out, they grew without bound.
        "a: &x [1, 2, 3]\nb: [*x, *x, *x]\nc: [*b, *b, *b]",
        "bar\ndata:\n  Jan: 1\n" + "  x: [" * 2000,
    ],
)
def test_what_holds_no_chart_is_not_one(body: str) -> None:
    assert loose_chart_json(body) is None


@pytest.mark.wall_clock
@pytest.mark.parametrize(
    "body",
    ["{" * 5999, "[" * 5999, "bar" + " " * 5990 + "x", "pie chart" + " " * 5980 + ":x"],
)
def test_reading_a_long_body_stays_quick(body: str) -> None:
    """Brackets nested deep took PyYAML a third of a second; spaces after the header word
    were read in quadratic time. Both run in the finalize pass, on the event loop."""
    started = time.perf_counter()
    assert loose_chart_json(body) is None
    assert time.perf_counter() - started < 0.05


# Live, after "yes" to an offered chart: a brace opened where the "y" key belongs.
_STRAY = (
    '{"$schema":"https://vega.github.io/schema/vega-lite/v5.json","data":{"values":'
    '[{"month":"Jan","rain":15},{"month":"Feb","rain":30}]},"mark":"bar","encoding":'
    '{"x":{"field":"rain","type":"quantitative"},{"y":{"field":"month","type":"nominal"}}}}'
)


@pytest.mark.parametrize(
    ("body", "mended"),
    [
        (_STRAY, _STRAY.replace('},{"y"', '},"y"').removesuffix("}")),
        # A doubled brace around the whole spec.
        (
            '{{"mark":"bar","data":{"values":[{"a":"x","b":1}]}}}',
            '{"mark":"bar","data":{"values":[{"a":"x","b":1}]}}',
        ),
        # Braces inside a string are text.
        (
            '{"title":"a \\"q\\" },{ b","mark":"bar","data":{"values":[{"a":"x","b":1}]},'
            '"encoding":{"x":{"field":"a"},{"y":{"field":"b"}}}}',
            '{"title":"a \\"q\\" },{ b","mark":"bar","data":{"values":[{"a":"x","b":1}]},'
            '"encoding":{"x":{"field":"a"},"y":{"field":"b"}}}',
        ),
    ],
)
def test_a_stray_brace_in_the_json_is_mended(body: str, mended: str) -> None:
    read = loose_chart_json(body)
    # On one line, so a fence's indent or quote marker carries onto all of it.
    assert read is not None and "\n" not in read
    assert json.loads(read) == json.loads(mended)
    assert chart_body_draws(read)


def test_an_escaped_quote_in_a_title_is_text() -> None:
    body = _STRAY.replace('"mark":"bar"', '"title":"6\\" pipes","mark":"bar"')
    read = loose_chart_json(body)
    assert read is not None and json.loads(read)["title"] == '6" pipes'


def test_a_mend_that_would_hold_a_key_twice_is_refused() -> None:
    """A forgotten "layer": [ — mended, its two marks merged and only the last one drew."""
    body = (
        '{"data":{"values":[{"m":"a","r":1},{"m":"b","r":2}]},{"mark":"bar","encoding":'
        '{"x":{"field":"m"},"y":{"field":"r"}}},{"mark":"rule","encoding":{"y":{"field":"r"}}}}'
    )
    assert loose_chart_json(body) is None


def test_objects_in_a_list_are_not_stray() -> None:
    body = '{"mark":"bar","data":{"values":[{"a":"x","b":1},{"a":"y","b":2}]'
    # Unclosed, so no JSON; the objects in the list stay as they are, and nothing draws.
    assert loose_chart_json(body) is None
