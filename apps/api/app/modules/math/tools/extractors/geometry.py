"""Geometry intent extractors: plane shapes, triangles and solids."""

from __future__ import annotations

import re

from app.modules.math.schemas import MathIntent
from app.services.number_text import DECIMAL_LITERAL
from app.services.text_match import word_index


def _requests_geometry_measurement(lower: str) -> bool:
    """Illustration defaults cannot answer a request for a measured quantity."""
    return any(
        word in lower
        for word in (
            "area",
            "perimeter",
            "circumference",
            "diagonal",
            "hypotenuse",
            "arc length",
        )
    )


def _wants_geometry_angles(lower: str) -> bool:
    # "triangle" and "rectangle" contain "angle" but are not angle requests.
    return any(word_index(lower, w) != -1 for w in ("angle", "angles", "degree", "degrees"))


def _geometry_request_mode(lower: str, has_requested_quantity: bool) -> str | None:
    if has_requested_quantity:
        return None
    if any(verb in lower for verb in ("draw ", "show ", "sketch ", "visualize ", "visualise ")):
        return "geometry_draw"
    return "geometry_clarify"


def _extract_solid_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    # Explicit convert … to … is a unit ask. SOLID runs first in the registry
    # and used to steal ``convert 1 atmosphere to psi`` as a sphere.
    if "convert" in lower and " to " in lower:
        return None
    parsed = mtm.parse_solid(cleaned)
    if parsed is None:
        return None
    asks_measure = parsed.wants_volume or parsed.wants_surface_area
    if not asks_measure and word_index(lower, "diagonal") != -1:
        # The solid solver has volume and surface area only; a diagonal is
        # the geometry measures' (s√3 for a cube), not a request to clarify.
        return None
    return MathIntent(
        kind="solid",
        solid_shape=parsed.shape,
        width=parsed.width,
        height=parsed.height,
        depth=parsed.depth,
        side=parsed.side,
        radius=parsed.radius,
        unit=parsed.unit,
        operation="solve",
        wants_volume=parsed.wants_volume,
        wants_surface_area=parsed.wants_surface_area,
        school_op=_geometry_request_mode(lower, parsed.wants_volume or parsed.wants_surface_area),
    )


def _extract_rectangle_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm
    from app.modules.math.match.literal_geometry import parse_named_rectangle_request

    lower = cleaned.lower()
    if mtm.classify_solid_shape(lower) is not None:
        return None
    named = parse_named_rectangle_request(cleaned)
    if named is not None:
        return MathIntent(
            kind="rectangle",
            width=named.width,
            height=named.length,
            unit=named.unit,
            operation="solve",
            wants_diagonal=named.quantity == "diagonal",
            wants_area=named.quantity in {"area", "area_and_perimeter"},
            wants_perimeter=named.quantity in {"perimeter", "area_and_perimeter"},
            given_area=named.given_area,
            geometry_target=named.target,
        )
    from app.modules.math.match.units import strip_geometry_length_units

    dimensions = strip_geometry_length_units(cleaned)
    dims = mtm.first_dim_pair(dimensions)
    if dims is None and "rectangle" in lower:
        sides = mtm.two_numbers_after(dimensions, "sides")
        if sides is None:
            sides = mtm.two_numbers_after(dimensions, "side lengths")
        if sides is not None:
            dims = (sides[0], sides[1], "cm")
    padded = f" {lower} "
    if dims is not None and ("rectangle" in lower or " rect " in padded or "diagonal" in lower):
        width, height, unit = dims
        return MathIntent(
            kind="rectangle",
            width=width,
            height=height,
            unit=unit,
            operation="solve",
            wants_diagonal=" diagonal" in padded or padded.startswith("diagonal "),
            wants_angle=" angle" in padded or "angles" in lower,
            wants_area=" area" in padded or padded.startswith("area "),
            wants_perimeter=" perimeter" in padded or padded.startswith("perimeter "),
            school_op=_geometry_request_mode(
                lower,
                any(
                    (
                        " diagonal" in padded or padded.startswith("diagonal "),
                        " angle" in padded or "angles" in lower,
                        " area" in padded or padded.startswith("area "),
                        " perimeter" in padded or padded.startswith("perimeter "),
                    )
                ),
            ),
        )

    if mtm.has_draw_shape(cleaned, "rectangle") and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="rectangle",
            width=6,
            height=4,
            unit="cm",
            operation="solve",
            school_op="geometry_draw",
        )
    return None


def _extract_square_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    if mtm.classify_solid_shape(lower) is not None:
        return None
    if "square" not in lower:
        return None
    # Algebraic uses of the word "square" must not become a geometry diagram:
    # "solve square root of x = 4" or "graph the square root" is no 5 cm square.
    if any(
        phrase in lower
        for phrase in (
            "square root",
            "perfect square",
            "squared",
            "squares to",
            "square of",
        )
    ):
        return None
    dims = mtm.first_dim_pair(cleaned)
    side = mtm.measure_after(cleaned, "side") or mtm.measure_after(cleaned, "edge")
    if side is None and dims is not None and dims[0] == dims[1]:
        side = dims[0]
    if side is not None:
        return MathIntent(
            kind="square",
            side=side,
            width=side,
            height=side,
            unit="cm",
            operation="solve",
            wants_perimeter="perimeter" in lower,
            wants_diagonal="diagonal" in lower,
            wants_area="area" in lower,
            school_op=_geometry_request_mode(
                lower,
                any(word in lower for word in ("area", "perimeter", "diagonal")),
            ),
        )
    # Default dimensions only when the user asked to draw/show the shape —
    # never invent a square for bare prose that merely contains "square".
    if mtm.has_draw_shape(cleaned, "square") and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="square",
            side=5,
            width=5,
            height=5,
            unit="cm",
            operation="solve",
            wants_perimeter="perimeter" in lower,
            wants_diagonal="diagonal" in lower,
            wants_area="area" in lower,
            school_op="geometry_draw",
        )
    return None


def _given_number(cleaned: str, label: str) -> float | None:
    """The number given for ``label``: "radius 4", "radius of 4 cm", "radius = 4".

    Not the next number anywhere after the word: in "the radius of a circle
    with circumference 31.4" the 31.4 is the circumference, and reading it
    as the radius answered a different circle.
    """
    from app.modules.math import match as mtm

    return mtm.measure_after(cleaned, label)


def _extract_circle_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    if mtm.classify_solid_shape(lower) is not None:
        return None
    if "circle" not in lower:
        return None
    # Sector mentions almost always include "circle" + "radius" — leave those
    # to `_extract_sector_intent` (which runs first). Without this guard a
    # partial sector cue ("sector … radius 5") becomes a plain circle fence.
    if "sector" in lower or "pie slice" in lower:
        return None
    # Algebra / unit-circle asks still contain "circle" (and often "radius") —
    # do not steal them from equation/graph extractors that run later.
    if mtm.geometry_deferred_for_algebra(lower):
        return None
    if re.search(r"\bsemi-?circle|\bhalf\s+(?:a\s+)?circle", lower):
        # A semicircle is half of this circle's area, not all of it.
        return None
    if mtm.pi_form_or_value_set(cleaned):
        return None  # "in terms of π", "use π = 22/7": not what a card to two places shows
    wants_area = "area" in lower
    wants_circumference = "circumference" in lower
    radius = _given_number(cleaned, "radius")
    if radius is not None:
        chord = mtm.measure_after(cleaned, "chord")
        return MathIntent(
            kind="circle",
            radius=radius,
            unit="cm",
            operation="solve",
            wants_area=wants_area,
            wants_circumference=wants_circumference,
            wants_diameter="diameter" in lower,
            chord_length=chord,
            wants_center_distance=chord is not None and "distance" in lower and "center" in lower,
            school_op=_geometry_request_mode(
                lower,
                wants_area
                or wants_circumference
                or "diameter" in lower
                or (chord is not None and "distance" in lower),
            ),
        )
    diameter = _given_number(cleaned, "diameter")
    if diameter is not None:
        return MathIntent(
            kind="circle",
            radius=diameter / 2,
            unit="cm",
            operation="solve",
            wants_diameter=False,
            given_diameter=True,
            wants_area=wants_area,
            wants_circumference=wants_circumference,
            school_op=_geometry_request_mode(lower, wants_area or wants_circumference),
        )
    # Default radius only on an explicit draw/show/sketch — never invent a
    # 5 cm circle for "what is a circle?" / "unit circle" / algebra that
    # merely mentions the word (those used to ship as SymPy-verified).
    if mtm.has_draw_shape(cleaned, "circle") and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="circle",
            radius=5,
            unit="cm",
            operation="solve",
            wants_area=wants_area,
            wants_circumference=wants_circumference,
            school_op="geometry_draw",
        )
    return None


def _right_triangle_named_legs(cleaned: str) -> tuple[float, float, str] | None:
    """``legs 3 and 4`` is not an ``8 x 5`` dim pair — parse it before defaulting."""
    from app.modules.math import match as mtm

    for label in ("leg lengths", "legs", "leg"):
        pair = mtm.two_numbers_after(cleaned, label)
        if pair is not None:
            return pair[0], pair[1], "cm"
    return None


def _extract_right_triangle_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm
    from app.modules.math.match.literal_geometry import (
        literal_hypotenuse_legs,
        measurement_request,
    )

    lower = cleaned.lower()
    if "right triangle" not in lower:
        return None
    if mtm.geometry_deferred_for_algebra(lower):
        return None
    padded = f" {lower} "
    wants_area = " area" in padded or padded.startswith("area ")
    dims = mtm.first_dim_pair(cleaned) or _right_triangle_named_legs(cleaned)
    if dims is not None:
        base, height, unit = dims
        return MathIntent(
            kind="right_triangle",
            base=base,
            height=height,
            unit=unit,
            operation="solve",
            wants_hypotenuse=literal_hypotenuse_legs(cleaned) == (base, height),
            wants_perimeter="perimeter" in cleaned.lower(),
            wants_area=wants_area,
            wants_angle=_wants_geometry_angles(lower),
            school_op=_geometry_request_mode(
                lower,
                any(
                    (
                        literal_hypotenuse_legs(cleaned) == (base, height),
                        "perimeter" in lower,
                        wants_area,
                        _wants_geometry_angles(lower),
                        measurement_request(cleaned) is not None,
                    )
                ),
            ),
        )
    if mtm.has_draw_shape(cleaned, "right triangle") and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="right_triangle",
            base=6,
            height=4,
            unit="cm",
            operation="solve",
            wants_perimeter="perimeter" in cleaned.lower(),
            wants_area=wants_area,
            wants_angle=_wants_geometry_angles(lower),
            school_op="geometry_draw",
        )
    return None


def _extract_triangle_sides_intent(cleaned: str) -> MathIntent | None:
    """Checked BEFORE the generic base+height triangle extractor below — a
    "triangle with sides 3, 4, 5" mention must not fall into that extractor's
    broad "triangle" + "area"/"draw"/... fallback and get the wrong (default
    base=8, height=5) shape instead of the SSS one actually named."""
    from app.modules.math import match as mtm

    if mtm.geometry_deferred_for_algebra(cleaned.lower()):
        return None
    sides = mtm.triangle_sides_signal(cleaned)
    if sides is None:
        return None
    a, b, c = sides
    return MathIntent(
        kind="triangle_sides",
        tri_a=a,
        tri_b=b,
        tri_c=c,
        unit="cm",
        operation="solve",
        wants_perimeter="perimeter" in cleaned.lower(),
        wants_angle=_wants_geometry_angles(cleaned.lower()),
        wants_area="area" in cleaned.lower(),
        school_op=_geometry_request_mode(
            cleaned.lower(),
            any(
                (
                    "perimeter" in cleaned.lower(),
                    _wants_geometry_angles(cleaned.lower()),
                    "area" in cleaned.lower(),
                )
            ),
        ),
    )


def _extract_trapezoid_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    if "perimeter" in lower:
        return None
    if "trapezoid" not in lower and "trapezium" not in lower:
        return None
    if mtm.geometry_deferred_for_algebra(lower):
        return None
    dimensions = mtm.trapezoid_dimensions(cleaned)
    if dimensions is not None:
        top, bottom, height = dimensions
        return MathIntent(
            kind="trapezoid",
            trapezoid_top=top,
            trapezoid_bottom=bottom,
            height=height,
            unit="cm",
            operation="solve",
            wants_area="area" in lower,
            wants_angle=_wants_geometry_angles(lower),
            school_op=_geometry_request_mode(
                lower, "area" in lower or _wants_geometry_angles(lower)
            ),
        )
    shape = "trapezoid" if "trapezoid" in lower else "trapezium"
    if mtm.has_draw_shape(cleaned, shape) and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="trapezoid",
            trapezoid_top=4,
            trapezoid_bottom=8,
            height=5,
            unit="cm",
            operation="solve",
            wants_angle=_wants_geometry_angles(lower),
            school_op="geometry_draw",
        )
    return None


def _extract_parallelogram_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    if "parallelogram" not in lower:
        return None
    if mtm.geometry_deferred_for_algebra(lower):
        return None
    base = mtm.measure_after(cleaned, "base")
    height = mtm.measure_after(cleaned, "height")
    side = mtm.measure_after(cleaned, "side")
    if "perimeter" in lower and side is None:
        return None
    if base is not None and height is not None:
        # Side is only needed for the slanted diagram. When the user gave
        # base+height (enough for area) but no side, use a right parallelogram
        # (side=height → zero shear) rather than inventing a fake slant length.
        return MathIntent(
            kind="parallelogram",
            base=base,
            height=height,
            side=side if side is not None else height,
            unit="cm",
            operation="solve",
            wants_area="area" in lower,
            wants_perimeter="perimeter" in cleaned.lower(),
            wants_angle=_wants_geometry_angles(lower),
            school_op=_geometry_request_mode(
                lower,
                "area" in lower or "perimeter" in lower or _wants_geometry_angles(lower),
            ),
        )
    if mtm.has_draw_shape(cleaned, "parallelogram") and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="parallelogram",
            base=8,
            height=4,
            side=5,
            unit="cm",
            operation="solve",
            wants_perimeter="perimeter" in cleaned.lower(),
            wants_angle=_wants_geometry_angles(lower),
            school_op="geometry_draw",
        )
    return None


def _extract_sector_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    if "sector" not in lower and "pie slice" not in lower:
        return None
    if "sector" in lower and not any(k in lower for k in ("circle", "radius", "pie", "arc")):
        return None
    if mtm.geometry_deferred_for_algebra(lower) or mtm.pi_form_or_value_set(cleaned):
        return None
    radius = mtm.measure_after(cleaned, "radius")
    if radius is None:
        radius = mtm.measure_after(cleaned, "r=")
    angle = mtm.measure_after(cleaned, "angle")
    if angle is None:
        deg_at = cleaned.find("°")
        if deg_at == -1:
            deg_at = lower.find(" degrees")
        if deg_at != -1:
            found = list(DECIMAL_LITERAL.finditer(cleaned[:deg_at]))
            if found:
                angle = float(found[-1].group(0))
    if radius is not None and angle is not None:
        return MathIntent(
            kind="sector",
            radius=radius,
            sector_angle_deg=angle,
            unit="cm",
            operation="solve",
            wants_area="area" in lower,
            wants_arc_length="arc" in lower,
            school_op=_geometry_request_mode(lower, "area" in lower or "arc" in lower),
        )
    # Defaults only when the user asked to draw the shape — never invent a
    # 90° / 5 cm sector for "sector of a circle with radius 5" alone.
    if (
        mtm.has_draw_shape(cleaned, "sector") or mtm.has_draw_shape(cleaned, "pie slice")
    ) and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="sector",
            radius=radius if radius is not None else 5,
            sector_angle_deg=angle if angle is not None else 90,
            unit="cm",
            operation="solve",
            school_op="geometry_draw",
        )
    return None


def _extract_triangle_angles_intent(cleaned: str) -> MathIntent | None:
    """AAA (and angle-sum) triangles — law of sines with relative side units.

    Must run before the generic draw-a-triangle default (base=8, height=5)
    so "triangle with angles 120, 40, 20" is not an invented isosceles.
    """
    from app.modules.math import match as mtm
    from app.modules.math import solve as math_solve
    from app.modules.math.match.literal_geometry import literal_triangle_angles_draw

    if mtm.geometry_deferred_for_algebra(cleaned.lower()):
        return None
    angles = mtm.triangle_angles_signal(cleaned)
    if angles is None:
        return None
    try:
        side_a, side_b, side_c = math_solve.sides_from_interior_angles(*angles)
    except math_solve.SolveServiceError:
        return None
    return MathIntent(
        kind="triangle_sides",
        tri_a=side_a,
        tri_b=side_b,
        tri_c=side_c,
        triangle_relative_lengths=True,
        unit="units",
        operation="solve",
        wants_angle=literal_triangle_angles_draw(cleaned) is None,
        wants_area=word_index(cleaned.lower(), "area") != -1,
        wants_perimeter=word_index(cleaned.lower(), "perimeter") != -1,
    )


def _extract_triangle_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    lower = cleaned.lower()
    if "perimeter" in lower:
        return None
    if mtm.geometry_deferred_for_algebra(lower):
        return None
    base_n = mtm.measure_after(cleaned, "base")
    height_n = mtm.measure_after(cleaned, "height")
    if base_n is not None and height_n is not None and "triangle" in lower:
        return MathIntent(
            kind="triangle",
            base=base_n,
            height=height_n,
            unit="cm",
            operation="solve",
            wants_area="area" in lower,
            wants_angle=_wants_geometry_angles(lower),
            school_op=_geometry_request_mode(
                lower, "area" in lower or _wants_geometry_angles(lower)
            ),
        )

    # "area of a triangle" is a definition question — do not invent base/height.
    # Defaults only for an explicit draw/show/sketch/visualize request.
    # A supplied angle list that failed AAA parsing/validation cannot turn
    # into an unrelated default triangle and its invented area.
    if (_wants_geometry_angles(lower) or "°" in cleaned) and any(
        char.isdigit() for char in cleaned
    ):
        return None
    if mtm.has_draw_shape(cleaned, "triangle") and not _requests_geometry_measurement(lower):
        return MathIntent(
            kind="triangle",
            base=8,
            height=5,
            unit="cm",
            operation="solve",
            wants_angle=_wants_geometry_angles(lower),
            school_op="geometry_draw",
        )
    return None
