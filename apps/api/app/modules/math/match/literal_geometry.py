"""Complete literal measurement grammar shared by extraction and direct replies."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from app.modules.math.match.scan import strip_command_lead
from app.modules.math.match.units import solid_length_unit, strip_geometry_length_units

GEOMETRY_DECIMAL = r"(?:[0-9]{1,12}(?:\.[0-9]{1,12})?|\.[0-9]{1,12})"
RIGHT_TRIANGLE_LEGS = re.compile(rf"legs\s+({GEOMETRY_DECIMAL})\s+and\s+({GEOMETRY_DECIMAL})")
_ANGLE_DRAW = re.compile(
    rf"(?:please )?(?:draw|sketch) (?:a |the )?triangle with angles "
    rf"({GEOMETRY_DECIMAL})\s*,\s*({GEOMETRY_DECIMAL})\s*,\s*({GEOMETRY_DECIMAL})(?: degrees|°)?"
)


@dataclass(frozen=True)
class NamedRectangleRequest:
    """A complete rectangle calculation written with named dimensions."""

    width: float
    length: float
    unit: str
    quantity: str
    given_area: float | None = None
    target: Literal["width", "length"] | None = None


_NAMED_VALUE = rf"(?:is|equals|=|of|:)?\s*({GEOMETRY_DECIMAL})"
_AREA_VALUE = re.compile(rf"\barea\s*{_NAMED_VALUE}", re.IGNORECASE)
_DIMENSION_VALUE = {
    name: re.compile(rf"\b{name}\s*{_NAMED_VALUE}", re.IGNORECASE)
    for name in ("width", "length", "height")
}
_ADJECTIVE_DIMENSION = re.compile(
    rf"\b({GEOMETRY_DECIMAL})\s*(?:[a-z]+\s+)?(wide|long|high)\b", re.IGNORECASE
)


def _one_named_value(text: str, name: str) -> float | None:
    matches = _DIMENSION_VALUE[name].findall(text)
    if len(matches) != 1:
        return None
    return float(matches[0])


def parse_named_rectangle_request(text: str) -> NamedRectangleRequest | None:
    """Parse a whole natural rectangle request, including one inverse area case.

    Supported examples include ``length is 4, width is 3; find area`` and
    ``area is 12, width is 3; find length``. The parser deliberately declines
    mixed shapes, extra numbers, transformed requests, and explanation asks.
    """
    if len(text) > 1000:
        return None
    lower = " ".join(text.lower().split()).strip().rstrip(".?")
    if (
        "rectangle" not in lower
        or re.search(r"\bsquare\b(?!\s+units?\b)", lower)
        or any(
            shape in lower
            for shape in (
                "circle",
                "triangle",
                "trapezoid",
                "trapezium",
                "parallelogram",
                "prism",
                "cube",
                "sphere",
                "cylinder",
                "cone",
                "pyramid",
            )
        )
    ):
        return None
    if any(token in lower for token in (" explain", " why", " proof", " hint", " step")):
        return None
    if any(char in lower for char in "+*^!;") or re.search(r"(?<!\w)-\d", lower):
        return None

    width = _one_named_value(lower, "width")
    length = _one_named_value(lower, "length")
    height = _one_named_value(lower, "height")
    for raw, adjective in _ADJECTIVE_DIMENSION.findall(lower):
        value = float(raw)
        if adjective == "wide":
            if width is not None:
                return None
            width = value
        else:
            if length is not None or height is not None:
                return None
            length = value
    if height is not None:
        if length is not None:
            return None
        length = height

    area_matches = _AREA_VALUE.findall(lower)
    area = float(area_matches[0]) if len(area_matches) == 1 else None
    if len(area_matches) > 1:
        return None

    requested = [
        quantity
        for quantity, patterns in {
            "area": (
                r"\b(?:find|calculate|compute|determine)\s+(?:its\s+|the\s+)?area\b",
                r"\bwhat\s+is\s+the\s+area\b",
                r"\barea$",
            ),
            "perimeter": (
                r"\b(?:find|calculate|compute|determine)\s+(?:its\s+|the\s+)?perimeter\b",
                r"\bwhat\s+is\s+the\s+perimeter\b",
                r"\bperimeter$",
            ),
            "diagonal": (
                r"\b(?:find|calculate|compute|determine)\s+(?:its\s+|the\s+)?diagonal\b",
                r"\bwhat\s+is\s+the\s+diagonal\b",
                r"\bdiagonal$",
            ),
            "width": (
                r"\b(?:find|calculate|compute|determine)\s+"
                r"(?:its\s+|the\s+|the\s+missing\s+)?width\b",
                r"\bwhat\s+is\s+the\s+width\b",
                r"\bwidth$",
            ),
            "length": (
                r"\b(?:find|calculate|compute|determine)\s+"
                r"(?:its\s+|the\s+|the\s+missing\s+)?(?:length|height)\b",
                r"\bwhat\s+is\s+the\s+(?:length|height)\b",
                r"\b(?:length|height)$",
            ),
        }.items()
        if any(re.search(pattern, lower) for pattern in patterns)
    ]
    if re.search(
        r"\b(?:area\b[^.?!]{0,30}\band\b[^.?!]{0,20}\bperimeter|"
        r"perimeter\b[^.?!]{0,30}\band\b[^.?!]{0,20}\barea)\b",
        lower,
    ):
        requested.extend(("area", "perimeter"))
    # Also accept the common leading form: "area of a rectangle with ...".
    for quantity in ("area", "perimeter", "diagonal", "width", "length"):
        if re.search(rf"\b{quantity}\s+of\s+(?:a\s+|the\s+)?rectangle\b", lower):
            requested.append(quantity)
    requested = list(dict.fromkeys(requested))
    if set(requested) == {"area", "perimeter"}:
        quantity = "area_and_perimeter"
    elif len(requested) == 1:
        quantity = requested[0]
    else:
        return None

    numeric_count = len(re.findall(GEOMETRY_DECIMAL, lower))
    unit_source = _AREA_VALUE.sub(" ", lower)
    unit = solid_length_unit(unit_source)
    if unit is None:
        return None

    if quantity in {"area", "perimeter", "diagonal", "area_and_perimeter"}:
        if width is None or length is None or area is not None or numeric_count != 2:
            return None
        if not (0 < width <= 1_000_000 and 0 < length <= 1_000_000):
            return None
        return NamedRectangleRequest(width, length, unit, quantity)

    if area is None or numeric_count != 2 or not 0 < area <= 1_000_000_000_000:
        return None
    if quantity == "length" and width is not None and length is None:
        length = area / width
        target: Literal["width", "length"] = "length"
    elif quantity == "width" and length is not None and width is None:
        width = area / length
        target = "width"
    else:
        return None
    if not (0 < width <= 1_000_000 and 0 < length <= 1_000_000):
        return None
    return NamedRectangleRequest(width, length, unit, quantity, area, target)


def literal_triangle_angles_draw(text: str) -> tuple[float, float, float] | None:
    """One complete, valid angle triple requested only as a drawing."""
    if len(text) > 1000:
        return None
    request = " ".join(text.lower().split()).rstrip(".?")
    match = _ANGLE_DRAW.fullmatch(request)
    if match is None:
        return None
    a, b, c = (float(value) for value in match.groups())
    if any(not 0 < angle < 180 for angle in (a, b, c)) or not math.isclose(a + b + c, 180):
        return None
    return a, b, c


# "a right triangle has legs 3 and 4, find the hypotenuse": the legs come first.
_LEGS_THEN_HYPOTENUSE = re.compile(
    r"(?:a |the )?right triangle (?:has|with) (legs .+?)[,.;]? "
    r"(?:find|what is|what's|calculate|compute|determine) (?:the |its )?"
    r"(?:length of the )?hypotenuse"
)


_SHAPES = (
    "rectangular prism",
    "right triangle",
    "square pyramid",
    "circle sector",
    "parallelogram",
    "trapezoid",
    "trapezium",
    "rectangle",
    "triangle",
    "cylinder",
    "sphere",
    "sector",
    "square",
    "circle",
    "cuboid",
    "cube",
    "cone",
)
_QUANTITIES = (
    "total surface area",
    "surface area",
    "circumference",
    "arc length",
    "hypotenuse",
    "perimeter",
    "diagonal",
    "diameter",
    "volume",
    "area",
)


# "A triangle has sides 3, 4 and 5. What is its area?": the shape, then the question.
_STATED_THEN_ASKED = re.compile(
    r"(?:a|the) (?P<shape>[a-z ]+?) (?:has|with) (?P<dims>[^.?]+?)[.,]? "
    r"(?:what is|what's|find|calculate|compute) (?:its|the) (?P<quantity>[a-z ]+)"
)


def measurement_request(user_text: str) -> tuple[str, str] | None:
    """Keep all text after a short measurement lead-in for the shape matcher."""
    if len(user_text) > 1000:
        return None
    request = " ".join(user_text.lower().split()).rstrip(".?")
    if request.startswith("please "):
        request = request[7:]
    stated = _STATED_THEN_ASKED.fullmatch(request)
    if stated is not None and stated["shape"] in _SHAPES and stated["quantity"] in _QUANTITIES:
        return stated["quantity"], f"{stated['shape']} with {stated['dims'].strip()}"
    legs_first = _LEGS_THEN_HYPOTENUSE.fullmatch(request)
    if legs_first is not None:
        return "hypotenuse", f"right triangle with {legs_first.group(1)}"
    request = strip_command_lead(request)
    quantity, separator, body = request.partition(" of ")
    if separator:
        for article in ("a ", "the "):
            if body.startswith(article):
                body = body[len(article) :]
                break
        return quantity, body

    # Natural school prompts also put the shape first: “a rectangle area
    # with sides 4, 5”.  Normalize that into the same shape body used by the
    # strict direct guards.  Longer names/quantities run first so “surface
    # area” and “right triangle” are never truncated to a shorter phrase.
    for article in ("a ", "the "):
        if request.startswith(article):
            request = request[len(article) :]
            break
    for shape in _SHAPES:
        prefix = shape + " "
        if not request.startswith(prefix):
            continue
        remainder = request[len(prefix) :]
        for candidate in _QUANTITIES:
            quantity_prefix = candidate + " "
            if remainder.startswith(quantity_prefix):
                dimensions = remainder[len(quantity_prefix) :].lstrip()
                return candidate, f"{shape} {dimensions}"
    return None


def literal_hypotenuse_legs(text: str) -> tuple[float, float] | None:
    """A whole hypotenuse request, not a reference, multiple, or transformed value."""
    request = measurement_request(text)
    if request is None or request[0] != "hypotenuse":
        return None
    shape = "right triangle "
    if not request[1].startswith(shape):
        return None
    dimensions = request[1][len(shape) :]
    if dimensions.startswith("with "):
        dimensions = dimensions[5:]
    if solid_length_unit(dimensions) is None:
        return None
    match = RIGHT_TRIANGLE_LEGS.fullmatch(strip_geometry_length_units(dimensions).strip())
    if match is None:
        return None
    base, height = (float(value) for value in match.groups())
    if not (0 < base <= 1_000_000 and 0 < height <= 1_000_000):
        return None
    return base, height
