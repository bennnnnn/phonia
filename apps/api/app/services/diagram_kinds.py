"""Diagrams the app draws itself as a ```mermaid card, by the names people give them.

Images reads this so "draw a decision tree" is never an AI picture, whose labels come
out garbled; chat reads it to lead the reply with the right Mermaid diagram, and so an
org chart is never mistaken for a numeric chart.
"""

from __future__ import annotations

import re
from itertools import pairwise

# Named by two words, the second of which alone can be a fair picture ("draw a tree").
DIAGRAM_KIND_PAIRS = frozenset(
    {
        ("decision", "tree"),
        ("family", "tree"),
        ("org", "chart"),
        ("organization", "chart"),
        ("organizational", "chart"),
        ("process", "map"),
        ("mind", "map"),
        ("concept", "map"),
        ("journey", "map"),
        ("state", "machine"),
        ("state", "diagram"),
        ("class", "diagram"),
        ("er", "diagram"),
        ("entity", "relationship"),
        ("gantt", "chart"),
    },
)
# Named by one word.
DIAGRAM_KIND_WORDS = frozenset({"mindmap", "mindmaps", "erd"})

_WORD = re.compile(r"[a-z]+")


def names_diagram_kind(text: str) -> bool:
    """True when the text names one of these diagrams ("a state-machine", "an ERD")."""
    words = _WORD.findall(text.lower())
    return any(word in DIAGRAM_KIND_WORDS for word in words) or any(
        pair in DIAGRAM_KIND_PAIRS for pair in pairwise(words)
    )


# Words that end the first noun group of a drawing: "a road with sharp curves" draws a road.
_GROUP_ENDS = frozenset(
    {"with", "of", "at", "in", "on", "for", "and", "by", "from", "to", "along", "across",
     "around", "over", "under", "that", "which", "where", "while"}
)  # fmt: skip
# "The curve y = x^2", "f(x) = sin x": a function's curve is maths', drawn from its formula.
_FORMULA = re.compile(r"\bf\s*\(\s*x\s*\)|\by\s*=", re.IGNORECASE)


def names_idea_curve(phrase: str) -> bool:
    """The thing to draw is a curve of an idea: "the learning curve for…", "a growth curve".

    Drawn as a chart, never a picture. Only the phrase's first noun group counts ("a
    mountain road with sharp curves" is a picture), and a formula's curve is maths'.
    """
    if _FORMULA.search(phrase):
        return False
    for word in _WORD.findall(phrase.lower())[:5]:
        if word in _GROUP_ENDS:
            return False
        if word in ("curve", "curves"):
            return True
    return False
