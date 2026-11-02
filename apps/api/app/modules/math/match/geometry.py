"""Solid / triangle-side homework cues."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from app.modules.math.match.dimensions import (
    first_dim_pair,
    first_dim_triple,
    measure_after,
    two_numbers_after,
)
from app.modules.math.schemas.operations import SolidShape
from app.services.number_text import DECIMAL_LITERAL
from app.services.text_match import word_index

_SOLID_ALGEBRA_PHRASES = (
    "cube root",
    "cubic",
    "cubed",
    "cube of",
    "perfect cube",
)


def trapezoid_dimensions(text: str) -> tuple[float, float, float] | None:
    """Read either ``top/bottom/height`` or natural ``bases a and b`` dimensions."""
    top = measure_after(text, "top")
    bottom = measure_after(text, "bottom")
    height = measure_after(text, "height")
    if top is not None and bottom is not None and height is not None:
        return top, bottom, height
    if height is None:
        return None

    lower = text.lower()
    bases_at = word_index(lower, "bases")
    if bases_at == -1:
        return None
    height_at = word_index(lower, "height")
    end = height_at if height_at > bases_at else len(text)
    bases = two_numbers_after(text[bases_at:end], "bases")
    if bases is None:
        return None
    return bases[0], bases[1], height


def _solid_word_index(lower: str, stem: str) -> int:
    """``sphere`` / ``spheres``, not ``atmosphere`` / ``hemisphere``."""
    start = 0
    n = len(stem)
    while True:
        idx = lower.find(stem, start)
        if idx == -1:
            return -1
        before_ok = idx == 0 or not lower[idx - 1].isalpha()
        after = idx + n
        if after < len(lower) and lower[after] == "s":
            after += 1
        after_ok = after >= len(lower) or not lower[after].isalpha()
        if before_ok and after_ok:
            return idx
        start = idx + 1


# The question sets π's value ("use π = 22/7", "take π as 3.14") or asks for the answer
# in π ("in terms of π", "leave your answer in π", "the exact area"). A card worked with
# π itself to two places answers neither.
_PI = r"(?:\u03c0|\\pi\b|\bpi\b)"
_PI_VALUE = re.compile(
    rf"{_PI}\s*(?:=|\u2248|as\b|to\s+be\b)|\b(?:use|using|take|taking)\s+{_PI}", re.IGNORECASE
)
_PI_FORM = re.compile(
    rf"\bin\s+terms\s+of\s+{_PI}|\bleave\s+(?:your\s+|the\s+)?answers?\s+in\s+"
    rf"(?:terms\s+of\s+)?{_PI}|\bexact\s+(?:answer|value|form|area|volume|length)\b",
    re.IGNORECASE,
)


def pi_value_set(text: str) -> bool:
    return _PI_VALUE.search(text) is not None


def pi_form_or_value_set(text: str) -> bool:
    return _PI_VALUE.search(text) is not None or _PI_FORM.search(text) is not None


def classify_solid_shape(lower: str) -> SolidShape | None:
    """3D homework shapes. Algebraic 'cube' (cube root, cubic) is not a solid.

    Match on word boundaries so ``atmosphere`` is not a sphere and ``silicone``
    is not a cone. English plurals (``spheres``) still count.
    """
    if "rectangular prism" in lower or "rect prism" in lower or "cuboid" in lower:
        return "rectangular_prism"
    if _solid_word_index(lower, "cylinder") != -1:
        return "cylinder"
    if _solid_word_index(lower, "cone") != -1:
        return "cone"
    if _solid_word_index(lower, "sphere") != -1:
        return "sphere"
    if _solid_word_index(lower, "pyramid") != -1:
        return "pyramid"
    if _solid_word_index(lower, "cube") != -1 and not any(
        p in lower for p in _SOLID_ALGEBRA_PHRASES
    ):
        return "cube"
    return None


def solid_homework_cue(lower: str) -> bool:
    padded = f" {lower} "
    return (
        " volume" in padded
        or padded.startswith("volume ")
        or "surface area" in lower
        or "surface-area" in lower
        or "capacity" in lower
    )


@dataclass(frozen=True)
class SolidParse:
    shape: SolidShape
    width: float | None = None
    height: float | None = None
    depth: float | None = None
    side: float | None = None
    radius: float | None = None
    unit: str = "cm"
    wants_volume: bool = False
    wants_surface_area: bool = False


def _solid_complete(parsed: SolidParse) -> bool:
    if parsed.shape == "cube":
        return parsed.side is not None
    if parsed.shape == "rectangular_prism":
        return parsed.width is not None and parsed.height is not None and parsed.depth is not None
    if parsed.shape in {"cylinder", "cone"}:
        return parsed.radius is not None and parsed.height is not None
    if parsed.shape == "sphere":
        return parsed.radius is not None
    if parsed.shape == "pyramid":
        if parsed.height is None:
            return False
        if parsed.side is not None:
            return True
        return parsed.width is not None and parsed.depth is not None
    return False


def parse_solid(cleaned: str) -> SolidParse | None:
    """Volume/surface-area homework with printed measures — never invent dims."""
    from app.modules.math.match.units import normalize_leading_decimals, solid_length_unit

    cleaned = normalize_leading_decimals(cleaned)
    lower = cleaned.lower()
    shape = classify_solid_shape(lower)
    if shape is None:
        return None
    if pi_form_or_value_set(cleaned):
        return None
    if geometry_deferred_for_algebra(lower):
        return None
    padded = f" {lower} "
    wants_volume = solid_homework_cue(lower) and "surface" not in lower
    wants_sa = "surface area" in lower or "surface-area" in lower
    if wants_sa and "volume" in padded:
        wants_volume = True

    unit = solid_length_unit(cleaned)
    if unit is None:
        return None
    triple = first_dim_triple(cleaned)
    pair = first_dim_pair(cleaned)
    side = measure_after(cleaned, "side") or measure_after(cleaned, "edge")
    radius = measure_after(cleaned, "radius")
    diameter = measure_after(cleaned, "diameter")
    height = measure_after(cleaned, "height")
    length = measure_after(cleaned, "length")
    width = measure_after(cleaned, "width")
    depth = measure_after(cleaned, "depth")
    base = measure_after(cleaned, "base")
    if diameter is not None and radius is None:
        radius = diameter / 2.0
    width_v = width
    height_v = height
    depth_v = depth
    side_v = side if side is not None else base
    if shape == "cube":
        if side_v is None:
            side_v = _first_positive_number(cleaned)
    elif shape == "rectangular_prism":
        if triple is not None:
            width_v, depth_v, height_v = triple[0], triple[1], triple[2]
        else:
            labeled = [v for v in (length, width, depth, height) if v is not None]
            if len(labeled) >= 3:
                width_v, depth_v, height_v = labeled[0], labeled[1], labeled[2]
            else:
                width_v = width_v or length or (pair[0] if pair else None)
                depth_v = depth_v or (pair[1] if pair else None)
    elif shape in {"cylinder", "cone"}:
        if height_v is None and pair is not None:
            if radius is None:
                radius, height_v = pair[0], pair[1]
            else:
                height_v = pair[1] if pair[0] == radius else pair[0]
    elif shape == "sphere":
        if radius is None:
            radius = _first_positive_number(cleaned)
    elif shape == "pyramid":
        if height_v is None and triple is not None:
            width_v, depth_v, height_v = triple[0], triple[1], triple[2]
        elif side_v is None and pair is not None and height_v is not None:
            side_v = pair[0]
        elif side_v is None and width_v is None and triple is None:
            if pair is not None:
                width_v, depth_v = pair[0], pair[1]

    parsed = SolidParse(
        shape=shape,
        width=width_v,
        height=height_v,
        depth=depth_v,
        side=side_v,
        radius=radius,
        unit=unit,
        wants_volume=wants_volume,
        wants_surface_area=wants_sa,
    )
    if not _solid_complete(parsed):
        return None
    return parsed


def _first_positive_number(text: str) -> float | None:
    m = DECIMAL_LITERAL.search(text)
    if m is None:
        return None
    value = float(m.group(0))
    return value if value > 0 else None


def geometry_deferred_for_algebra(lower: str) -> bool:
    """Geometry extractors run *before* equation/graph extractors.

    A phrase like "solve x^2+y^2=25 for the circle of radius 5" used to match
    the circle extractor (radius present) and steal the algebra path. Defer
    geometry when the ask is clearly algebraic — unless the user also asked
    to draw/show/sketch the shape.
    """
    if any(v in lower for v in ("draw ", "show ", "sketch ", "visualize ", "visualise ")):
        return False
    padded = f" {lower} "
    return any(
        cue in padded
        for cue in (
            " equation ",
            " equations ",
            " solve ",
            " algebra ",
            " complete the square ",
            " unit circle ",
            " expand ",
            " factor ",
            " differentiate ",
            " derivative ",
            " integrate ",
            " integral ",
        )
    )


_TRIANGLE_SIDES_PREFIXES = ("sides ", "side lengths ", "sides of ", "side lengths of ")


def triangle_sides_signal(text: str) -> tuple[float, float, float] | None:
    """ "triangle with sides 3, 4, 5" -> (3, 4, 5). Requires the word
    "triangle" AND a "sides" cue immediately before 3 numbers, so a bare
    "triangle" (handled by the existing base+height extractor) never matches."""
    lower = text.lower()
    if "triangle" not in lower:
        return None
    for prefix in _TRIANGLE_SIDES_PREFIXES:
        idx = lower.find(prefix)
        if idx == -1:
            continue
        nums = [m.group(0) for m in DECIMAL_LITERAL.finditer(text, idx + len(prefix))]
        if len(nums) >= 3:
            try:
                return float(nums[0]), float(nums[1]), float(nums[2])
            except ValueError:
                return None
    return None


def triangle_angles_signal(text: str) -> tuple[float, float, float] | None:
    """AAA triangle — needs an angle cue, not just three numbers that sum to 180.

    ``"triangle with angles 120, 40, 20"`` / degrees / ``°``. ``"triangle"``
    contains the letters ``angle`` so the cue must be a whole word.
    """
    lower = text.lower()
    if "triangle" not in lower:
        return None
    if any(p in lower for p in ("sides ", "side lengths", "side lengths of")):
        return None
    if "base" in lower or "height" in lower:
        return None
    has_angle_cue = (
        "°" in text
        or word_index(lower, "degree") != -1
        or word_index(lower, "degrees") != -1
        or word_index(lower, "angle") != -1
        or word_index(lower, "angles") != -1
    )
    if not has_angle_cue:
        return None
    matches = list(DECIMAL_LITERAL.finditer(text))
    if len(matches) != 3:
        return None
    for left, right in pairwise(matches):
        gap = "".join(text[left.end() : right.start()].lower().split())
        for degree in ("degrees", "degree", "°"):
            if gap.startswith(degree):
                gap = gap[len(degree) :]
                break
        for label in ("anglea=", "angleb=", "anglec=", "a=", "b=", "c="):
            if gap.endswith(label):
                gap = gap[: -len(label)]
                break
        if gap not in {"", ",", ";", "and", ",and"}:
            return None
    angle_a, angle_b, angle_c = (float(match.group(0)) for match in matches)
    if any(not 0 < angle < 180 for angle in (angle_a, angle_b, angle_c)):
        return None
    if abs(angle_a + angle_b + angle_c - 180.0) > 0.6:
        return None
    return angle_a, angle_b, angle_c
