"""A shape question whose numbers are not its measures as printed.

The shape readers take the number after each measure's name. A question that states a
measure through another ("height 4 cm more than its radius", "twice the radius", "3 times
its base"), changes one ("if the radius is doubled", "the length is increased by 2 cm"),
or combines shapes ("subtract the area of a square", "inner radius 3 cm, outer radius
5 cm", "the sum of their areas") is not one shape at its printed numbers: its card would
answer another question, so the reading is declined wherever the relation stands.

A solid's surface area is worked closed and whole. A lateral, curved or open one is
another surface, so that card is declined too.
"""

from __future__ import annotations

import re

_COMPARATIVE = (
    r"(?:more|less|longer|shorter|greater|smaller|larger|bigger|taller|wider|narrower"
    r"|higher|lower|thicker|thinner|fewer)"
)
_MEASURE_NOUN = (
    r"(?:areas?|volumes?|perimeters?|surface|radius|radii|height|sides?|length|width"
    r"|diameter|circumference|dimensions?)"
)
_RELATION = re.compile(
    # One measure through another.
    rf"\b{_COMPARATIVE}\s+than\b|%\s*{_COMPARATIVE}\b"
    r"|\b(?:twice|thrice|half|halved|halving|double[ds]?|doubling|triple[ds]?|tripling"
    r"|quadruple[ds]?)\b(?!-)"
    r"|\btimes\b(?!\s*\d)"
    # A measure changed.
    r"|\b(?:increase[ds]?|decrease[ds]?|reduce[ds]?|enlarge[ds]?|scaled|multiplied|divided"
    r"|stretched|shrunk|extended|changed|becomes|instead|original)\b"
    rf"|\bnew\s+{_MEASURE_NOUN}\b"
    # Shapes combined.
    r"|\b(?:subtract(?:s|ed|ing)?|minus|plus|remove[ds]?|cut\s+(?:out|off|away)|hollow"
    r"|shaded|inner|outer|outside|inscribed|circumscribed|combined|together|similar"
    r"|difference)\b"
    r"|\bin\s+the\s+ratio\b|\b(?:areas|volumes|perimeters|circumferences)\b"
    # The same, said as an operator: "3 * its base", "7 cm - the area of a circle".
    r"|[*\u00d7\u00b7]\s*(?:the|its|their|that|this)\b|\s[-+]\s+(?:the|its|their|that|this|an?)\s",
    re.IGNORECASE,
)
_OTHER_SURFACE = re.compile(
    r"\b(?:lateral|curved|side|slant|outer|inner|exposed|wetted|painted|external|internal)"
    r"\s+(?:surface\s+)?area\b",
    re.IGNORECASE,
)
_OPEN_SOLID = re.compile(
    r"\bopen\b|\b(?:lidless|topless|uncovered)\b"
    r"|\b(?:without|no)\s+(?:a\s+|the\s+|its\s+|any\s+)?(?:lid|top|base|bottom|cover|ends?)\b",
    re.IGNORECASE,
)


def measures_not_as_printed(text: str) -> bool:
    """A measure stated through another, changed, or combined with another shape's."""
    return _RELATION.search(text) is not None


def surface_not_closed_total(text: str, *, asks_surface: bool) -> bool:
    """A lateral or curved surface, or an open solid's surface: not the closed total."""
    if _OTHER_SURFACE.search(text) is not None:
        return True
    return asks_surface and _OPEN_SOLID.search(text) is not None
