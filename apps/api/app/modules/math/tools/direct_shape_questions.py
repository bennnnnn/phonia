"""Shape descriptions that name dimensions but no measurement.

"A rectangle 3 by 4" gets a diagram and a question instead of an invented area;
"draw a rectangle 3 by 4" gets only the diagram. Angle-only triangles cannot be
measured at all, so the reply asks for one side.
"""

from __future__ import annotations

import json
import re

from app.modules.math.tools.direct_fences import solver_fences
from app.services.solving import VerifiedMathBlock

_GEOMETRY_DECLARATION_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "angle",
        "angles",
        "base",
        "bases",
        "bottom",
        "by",
        "circle",
        "cm",
        "cone",
        "cube",
        "cuboid",
        "cylinder",
        "degree",
        "degrees",
        "depth",
        "diameter",
        "draw",
        "edge",
        "edges",
        "feet",
        "foot",
        "ft",
        "height",
        "in",
        "inch",
        "inches",
        "km",
        "leg",
        "legs",
        "length",
        "lengths",
        "m",
        "meter",
        "meters",
        "metre",
        "metres",
        "mm",
        "of",
        "parallelogram",
        "pie",
        "please",
        "prism",
        "pyramid",
        "radius",
        "rect",
        "rectangle",
        "rectangular",
        "right",
        "sector",
        "show",
        "side",
        "sides",
        "sketch",
        "slice",
        "sphere",
        "square",
        "the",
        "top",
        "trapezium",
        "trapezoid",
        "triangle",
        "unit",
        "units",
        "visualise",
        "visualize",
        "width",
        "with",
        "x",
    }
)
_GEOMETRY_SHAPE_ALIASES: dict[str, tuple[str, ...]] = {
    "rectangle": ("rectangle", "rect"),
    "square": ("square",),
    "triangle": ("triangle",),
    "right_triangle": ("right triangle",),
    "triangle_sides": ("triangle",),
    "parallelogram": ("parallelogram",),
    "trapezoid": ("trapezoid", "trapezium"),
    "circle": ("circle",),
    "sector": ("circle sector", "sector", "pie slice"),
}
_GEOMETRY_QUESTIONS = {
    "rectangle": "Do you want the area, perimeter, or diagonal?",
    "square": "Do you want the area, perimeter, or diagonal?",
    "triangle": "Do you want the area, or only a labeled diagram?",
    "right_triangle": "Do you want the area, perimeter, hypotenuse, or angles?",
    "triangle_sides": "Do you want the area, perimeter, or angles?",
    "parallelogram": "Do you want the area or perimeter?",
    "trapezoid": "Do you want the area, or only a labeled diagram?",
    "circle": "Do you want the area, circumference, or diameter?",
    "sector": "Do you want the area or arc length?",
}
_DRAW_WORDS = frozenset({"draw", "show", "sketch", "visualize", "visualise"})
_GEOMETRY_NUMBER_COUNTS: dict[str, frozenset[int]] = {
    "rectangle": frozenset({2}),
    "square": frozenset({1}),
    "triangle": frozenset({2}),
    "right_triangle": frozenset({2}),
    "triangle_sides": frozenset({3}),
    "parallelogram": frozenset({2, 3}),
    "trapezoid": frozenset({3}),
    "circle": frozenset({1}),
    "sector": frozenset({2}),
    "cube": frozenset({1}),
    "rectangular_prism": frozenset({3}),
    "cylinder": frozenset({2}),
    "cone": frozenset({2}),
    "sphere": frozenset({1}),
    "pyramid": frozenset({2}),
}


def _geometry_shape_mentions(lower: str) -> list[str]:
    """Return semantic shape mentions, collapsing compound shape names."""
    normalized = lower
    compounds = (
        (r"\bsector\s+of\s+(?:a\s+)?circle\b", "sector"),
        (r"\bcircle\s+sector\b", "sector"),
        (r"\bpie\s+slice\b", "sector"),
        (r"\bright\s+triangle\b", "right_triangle"),
        (r"\brectangular\s+prism\b", "rectangular_prism"),
        (r"\bsquare\s+pyramid\b", "pyramid"),
    )
    mentions: list[str] = []
    for pattern, kind in compounds:
        matches = re.findall(pattern, normalized)
        mentions.extend(kind for _ in matches)
        normalized = re.sub(pattern, " ", normalized)
    aliases = {
        "rect": "rectangle",
        "trapezium": "trapezoid",
    }
    for shape in re.findall(
        r"\b(?:rectangle|rect|square|triangle|parallelogram|trapezoid|trapezium|"
        r"circle|sector|cube|cuboid|cylinder|cone|sphere|pyramid)\b",
        normalized,
    ):
        mentions.append(aliases.get(shape, shape))
    return mentions


def _plain_geometry_description(
    user_text: str, aliases: tuple[str, ...], kind: str
) -> tuple[bool, bool]:
    """Return (is plain shape description, explicitly asks for a drawing)."""
    if len(user_text) > 1000 or any(char in user_text for char in "+=^;!-"):
        return False, False
    lower = " ".join(user_text.lower().split()).strip().rstrip(".?")
    words = re.findall(r"[a-z]+", lower)
    if not words or any(word not in _GEOMETRY_DECLARATION_WORDS for word in words):
        return False, False
    draw = any(word in _DRAW_WORDS for word in words)
    if len(_geometry_shape_mentions(lower)) != 1:
        return False, False
    number_count = len(re.findall(r"(?:\d+(?:\.\d+)?|\.\d+)", lower))
    expected_counts = _GEOMETRY_NUMBER_COUNTS[kind]
    if number_count not in expected_counts and not (draw and number_count == 0):
        return False, False
    request = lower
    if request.startswith("please "):
        request = request[7:].lstrip()
    if draw:
        for verb in _DRAW_WORDS:
            if request.startswith(verb + " "):
                request = request[len(verb) + 1 :].lstrip()
                break
    for article in ("a ", "an ", "the "):
        if request.startswith(article):
            request = request[len(article) :].lstrip()
            break
    starts_with_shape = any(
        request == alias or request.startswith(alias + " ") for alias in aliases
    )
    return starts_with_shape and (any(char.isdigit() for char in lower) or draw), draw


def nonmeasurement_geometry_reply(verified: VerifiedMathBlock, user_text: str) -> str | None:
    """Clarify a dimension-only shape instead of inventing area/volume.

    Explicit draw/show requests are complete as written and return only their
    solver-owned diagram. The narrow vocabulary check keeps mixed requests on
    the normal language path.
    """
    from app.modules.math.match.literal_geometry import measurement_request

    # Never reinterpret an answering block as a draw/clarification request.
    # This also prevents a stale verified measurement from being hidden by a
    # later, less specific drawing phrase.
    if verified.canonical_answer is not None:
        return None

    requested_measurement = measurement_request(user_text)
    fences = solver_fences(verified)
    if len(fences) == 1:
        # Angle-only triangles already have a strict whole-request validator.
        # Let it reject added sides, shapes, calculations, or explanations.
        if fences[0].get("relative_lengths") is True:
            return None
        kind = fences[0].get("type")
        aliases = _GEOMETRY_SHAPE_ALIASES.get(str(kind))
        if aliases is not None:
            plain, draw = _plain_geometry_description(user_text, aliases, str(kind))
            if not plain:
                return None
            if draw:
                return f"```geometry\n{json.dumps(fences[0], separators=(',', ':'))}\n```\n"
            question = _GEOMETRY_QUESTIONS[str(kind)]
            diagram = json.dumps(fences[0], separators=(",", ":"))
            return (
                f"You gave the dimensions, but not what to calculate. {question}\n\n"
                f"```geometry\n{diagram}\n```\n"
            )
        if requested_measurement is not None:
            return None

    if verified.canonical_answer is None and not fences:
        for kind, aliases in _GEOMETRY_SHAPE_ALIASES.items():
            # Both SSS and base-height inputs say "triangle". Preserve the
            # more specific choices when the user supplied all three sides.
            if kind == "triangle" and re.search(r"\bsides?\b", user_text, re.IGNORECASE):
                continue
            if kind == "triangle_sides" and not re.search(r"\bsides?\b", user_text, re.IGNORECASE):
                continue
            plain, draw = _plain_geometry_description(user_text, aliases, kind)
            if plain and not draw:
                return (
                    "You gave the dimensions, but not what to calculate. "
                    f"{_GEOMETRY_QUESTIONS[kind]}"
                )

    if requested_measurement is not None:
        return None

    from app.modules.math.match.geometry import parse_solid

    solid = parse_solid(user_text)
    if solid is None or solid.wants_volume or solid.wants_surface_area:
        return None
    aliases = {
        "cube": ("cube",),
        "rectangular_prism": ("rectangular prism", "cuboid"),
        "cylinder": ("cylinder",),
        "cone": ("cone",),
        "sphere": ("sphere",),
        "pyramid": ("square pyramid", "pyramid"),
    }[solid.shape]
    plain, draw = _plain_geometry_description(user_text, aliases, solid.shape)
    if not plain or draw:
        return None
    return (
        "You gave the dimensions, but not what to calculate. "
        "Do you want the volume or surface area?"
    )


def underdetermined_triangle_measurement(verified: VerifiedMathBlock, user_text: str) -> str | None:
    """A complete AAA measurement has a known shape, but no physical scale."""
    from app.modules.math.match.literal_geometry import measurement_request
    from app.modules.math.tools.direct_geometry import can_direct_triangle_angles

    if verified.canonical_answer is not None:
        return None
    parsed = measurement_request(user_text)
    if parsed is None or parsed[0] not in {"area", "perimeter"}:
        return None
    quantity, triangle = parsed
    # The existing whole-draw grammar validates all three literal angles and
    # their agreement with the one relative diagram; extra clauses cannot pass.
    if not can_direct_triangle_angles(f"Draw a {triangle}", solver_fences(verified)):
        return None
    return quantity
