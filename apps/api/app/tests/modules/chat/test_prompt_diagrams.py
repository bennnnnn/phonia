"""A named diagram ("a state machine", "an org chart") gets the Mermaid hint for it."""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants import (
    DIAGRAM_KIND_HINT,
    MERMAID_FORMAT_HINT,
    SEQUENCE_FORMAT_HINT,
    mermaid_format_hint,
)
from app.modules.turn_reading.chart import is_chart_question


@pytest.mark.parametrize(
    "text, hint",
    [
        ("Draw a decision tree for choosing a first programming language", DIAGRAM_KIND_HINT),
        ("Draw a state machine for a traffic light", DIAGRAM_KIND_HINT),
        ("make a state-machine diagram for a vending machine", DIAGRAM_KIND_HINT),
        ("Make a mind map of renewable energy sources", DIAGRAM_KIND_HINT),
        ("create a mindmap of my week", DIAGRAM_KIND_HINT),
        ("Draw an org chart for a small startup: CEO, CTO, two engineers", DIAGRAM_KIND_HINT),
        ("sketch our family tree: grandparents, parents and three kids", DIAGRAM_KIND_HINT),
        ("show the ER diagram for a library app", DIAGRAM_KIND_HINT),
        ("make a gantt chart for a 4-week launch", DIAGRAM_KIND_HINT),
        ("Draw a flowchart for deciding whether to bring an umbrella", MERMAID_FORMAT_HINT),
        ("draw a sequence diagram of OAuth login", SEQUENCE_FORMAT_HINT),
        # Named, but not asked to be drawn.
        ("What is a decision tree in machine learning?", None),
        ("how do I make a decision tree in sklearn", None),
        ("How do I make a mind map?", None),
        ("implement a state machine in python", None),
        ("draw a tree in autumn", None),
        ("make a treasure map", None),
        ("", None),
    ],
)
def test_mermaid_format_hint_names_the_diagram(text: str, hint: str | None) -> None:
    assert mermaid_format_hint(text) == hint


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Draw an org chart for a small startup", False),
        ("make a gantt chart for my project", False),
        ("Make a bar chart of this data: Mon 12, Tue 19", True),
        # An idea's curve is a chart with sample data; a formula's is maths'.
        ("draw the learning curve for a new language", True),
        ("draw a growth curve for my startup", True),
        ("draw the curve y = x^2", False),
        ("draw a winding mountain road with sharp curves", False),
        ("draw a chart of my sales by month", True),
    ],
)
def test_is_chart_question_leaves_named_diagrams_to_mermaid(text: str, expected: bool) -> None:
    assert is_chart_question(text) is expected
