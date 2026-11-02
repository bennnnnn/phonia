"""The server judges each chart body as the phone draws it.

``docs/fixtures/chart_bodies.json`` holds bodies models wrote (and ones the phone cannot
draw); the phone's ``chartBodies.test.ts`` draws each with the vendored Vega. A body the
server passes and the phone cannot read drew "Could not render that chart." with nothing
under it; one the phone reads and the server refused was swapped for a table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.chat.chart_sanitize import chart_is_drawable, sanitize_chart_fences

_FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "chart_bodies.json"
_BODIES: list[dict[str, object]] = json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", _BODIES, ids=[str(entry["name"]) for entry in _BODIES])
def test_the_server_draws_what_the_phone_draws(entry: dict[str, object]) -> None:
    assert chart_is_drawable(str(entry["body"])) is entry["draws"]


def test_a_body_the_phone_cannot_draw_never_reaches_it() -> None:
    body = '{"type":"bar","labels":["A","B","C"],"series":[{"name":"n","values":[1,2]}]}'
    reply = f"Here are the counts.\n\n```chart\n{body}\n```\n\nA leads."
    assert "```chart" not in sanitize_chart_fences(reply)


def test_a_body_the_phone_recovers_stays_a_chart() -> None:
    """A stray brace after the JSON: the phone drops it and draws; it was swapped for a table."""
    body = '{"data":{"values":[{"a":1}]},"mark":"bar","encoding":{"x":{"field":"a"}}}}'
    reply = f"```chart\n{body}\n```"
    assert sanitize_chart_fences(reply) == reply


def test_nan_is_no_json_on_the_phone_either() -> None:
    """Python reads ``NaN``; the phone's ``JSON.parse`` does not, and drew a blank card."""
    assert not chart_is_drawable('{"data":{"values":[{"a":NaN}]},"mark":"bar"}')
