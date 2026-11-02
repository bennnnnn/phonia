"""A ```chart the phone cannot draw never reaches it.

The format rules every turn gets name the ```chart fence, but only a turn that asks for
a visual is told its shape (Vega-Lite JSON, data inline). "What's 72 fahrenheit in
celsius" got a chart nobody asked for, written as YAML around a pipe table, and the phone
showed "Could not render that chart" above the answer. What the phone draws is
``chart_bodies``' to say, judged against the same bodies the phone's tests draw. A body
written as loose text (YAML, a mermaid-like block) is read into JSON the phone draws
(``chart_loose``); any other becomes the table it holds, or goes. A reply that was only
an undrawable chart stays as written: dropping it saved an empty reply while the phone
kept showing the chart it streamed. A formula chart is turned into a verified ```graph
earlier (``formula_charts``).
"""

from __future__ import annotations

import re

from app.modules.chat.chart_bodies import chart_body_draws
from app.modules.chat.chart_loose import loose_chart_json
from app.services.md_fence_scan import Fence, block_end, map_fence_blocks

# The langs the phone draws as a chart (``lib/fenceRegistry.ts``).
CHART_LANGS = frozenset({"chart", "vega", "vega-lite", "plot"})


def chart_is_drawable(body: str) -> bool:
    """A body the phone draws: a dialect it reads, or JSON with its data inline."""
    return chart_body_draws(body)


def _table_in(body: str) -> str:
    """The pipe table a broken chart holds, as a markdown table; "" when it holds none."""
    rows = [line.strip().strip("|").strip() for line in body.splitlines() if "|" in line]
    # Rows of two cells or more: YAML's "data: |" holds a pipe and no row.
    cells = [cells for row in rows if len(cells := [c.strip() for c in row.split("|")]) >= 2]
    data = [row for row in cells if not all(set(cell) <= set("-: ") for cell in row)]
    if len(data) < 2 or len({len(row) for row in data}) != 1 or len(data[0]) < 2:
        return ""
    header, *rest = data
    lines = [f"| {' | '.join(header)} |", f"|{'---|' * len(header)}"]
    lines.extend(f"| {' | '.join(row)} |" for row in rest)
    return "\n".join(lines) + "\n"


def sanitize_chart_fences(text: str) -> str:
    """Each chart the phone can draw as written or read from loose text; any other becomes
    its table, or goes, unless nothing of the reply would be left."""

    def replace(fence: Fence, body: str) -> str:
        if fence.lang not in CHART_LANGS or chart_is_drawable(body):
            return text[fence.start : block_end(text, fence)]
        if (read := loose_chart_json(body)) is not None:
            # The fence's indent or quote markers carry onto its line: in a list item, a
            # line at the margin ended the item and the fence.
            closer = text[fence.body_end : block_end(text, fence)]
            return f"{text[fence.start : fence.body_start]}{fence.opener.prefix}{read}\n{closer}"
        return _table_in(body)

    if not any(lang in text for lang in CHART_LANGS):
        return text
    kept = map_fence_blocks(text, replace)
    if kept == text:
        return text
    kept = re.sub(r"\n{3,}", "\n\n", kept).strip()
    return kept or text
