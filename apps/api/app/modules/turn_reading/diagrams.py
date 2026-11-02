"""Whether a message asks for a diagram, and of which kind."""

from __future__ import annotations

import re

from app.modules.turn_reading.chart import is_chart_question
from app.modules.turn_reading.visuals import is_html_ui_question
from app.services.diagram_kinds import names_diagram_kind

_SEQUENCE_CUE = re.compile(r"\bsequence\s+diagram\b", re.IGNORECASE)


_FLOWCHART_CUE = re.compile(
    r"(?:\bflow[\s-]?chart\b|```mermaid\b)",
    re.IGNORECASE,
)


_MERMAID_WORD = re.compile(r"\bmermaid\b", re.IGNORECASE)


_MERMAID_RENDER_CUE = re.compile(
    r"\b(?:draw|show|make|create|render|diagram)\b",
    re.IGNORECASE,
)


_DRAW_CUE = re.compile(
    r"\b(?:draw|sketch|show|make|create|render|generate|build|design|map\s+out)\b",
    re.IGNORECASE,
)


_HOW_DO_I = re.compile(r"\bhow\s+(?:to|(?:do|can|should)\s+(?:i|you|we))\b", re.IGNORECASE)


def is_sequence_diagram_question(text: str) -> bool:
    """True when the user asked for a sequence diagram specifically."""
    cleaned = text.strip()
    return bool(cleaned and _SEQUENCE_CUE.search(cleaned))


def is_mermaid_question(text: str) -> bool:
    """True when the user asked for a Mermaid/flowchart/sequence diagram."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if is_sequence_diagram_question(cleaned) or is_diagram_kind_question(cleaned):
        return True
    if _FLOWCHART_CUE.search(cleaned):
        return True
    return bool(_MERMAID_WORD.search(cleaned) and _MERMAID_RENDER_CUE.search(cleaned))


def is_diagram_kind_question(text: str) -> bool:
    """True for "draw a state machine", "make a mind map": a named diagram to draw.
    "What is a decision tree?" and "how do I make a mind map?" are not."""
    return (
        names_diagram_kind(text)
        and _DRAW_CUE.search(text) is not None
        and _HOW_DO_I.search(text) is None
    )


def asks_for_a_visual(query_text: str | None) -> bool:
    """A chart, a diagram or a web page to preview: the turn gets the visual hints."""
    if not query_text or not query_text.strip():
        return False
    return (
        is_chart_question(query_text)
        or is_mermaid_question(query_text)
        or is_html_ui_question(query_text)
    )
