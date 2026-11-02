"""Which words name a diagram the app draws itself."""

from __future__ import annotations

import pytest

from app.services.diagram_kinds import names_diagram_kind, names_idea_curve


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a decision tree for choosing a language", True),
        ("Family Tree of the Tudors", True),
        ("our org chart", True),
        ("a state-machine for a turnstile", True),
        ("a mind map of renewable energy", True),
        ("a MINDMAP", True),
        ("the entity-relationship diagram", True),
        ("an ERD for the library", True),
        ("a gantt chart", True),
        ("a tree in autumn", False),
        ("a treasure map", False),
        ("a map of Ethiopia", False),
        ("the state of the union", False),
        ("a machine learning model", False),
        ("", False),
    ],
)
def test_names_diagram_kind(text: str, expected: bool) -> None:
    assert names_diagram_kind(text) is expected


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("the learning curve for a new language", True),
        ("a growth curve for my startup", True),
        ("a curve of how memory fades", True),
        ("an S-curve of adoption", True),
        ("the demand curve", True),
        # A picture's detail, an adjective, or a function's curve (maths').
        ("a winding mountain road with sharp curves at sunset", False),
        ("a woman with beautiful curves", False),
        ("a curved road at sunset", False),
        ("the curve y = x^2", False),
        ("the curve f(x) = sin x", False),
        ("", False),
    ],
)
def test_names_idea_curve(phrase: str, expected: bool) -> None:
    assert names_idea_curve(phrase) is expected
