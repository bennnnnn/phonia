"""Optics laws a question names: Malus, Brewster, the double and single slit, lens power,
the critical angle, Snell's refractive index and magnification; and the thin-lens image
distance, which `optics.py` reads when no law is named."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.physics.extractors.angles import INCLINE_ANGLE_RE
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.unit_patterns import (
    DECIMAL,
    DEGREE_WORD,
    LENGTH_UNIT_PATTERN,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.optic_elements import (
    converging_element,
    inverted_image,
    places_named,
    signed_distances,
    upright_image,
)
from app.modules.physics.schemas import PhysicsIntent

_HEIGHT_RE = re.compile(r"\b(?:tall|high|height)\b")


def _malus(cleaned: str) -> PhysicsIntent | None:
    """I = I₀ cos²θ through a polarizer."""
    intensity = find_value_with_specific_unit(
        cleaned, r"W/m\^?2|watts?\s+per\s+square\s+met(?:er|re)", ("intensity",)
    )
    angle_match = INCLINE_ANGLE_RE.search(cleaned)
    if intensity is None or angle_match is None:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op="malus_intensity",
        physics_params={"intensity0": intensity[0], "angle": float(angle_match.group(1))},
        physics_units={"intensity0": intensity[1] or "W/m^2", "angle": "deg"},
        operation="solve",
    )


def _brewster(cleaned: str) -> PhysicsIntent | None:
    """tan θ_B = n₂ / n₁, from the two indexes written as n1 and n2."""
    indexes = [
        float(value) for value in re.findall(rf"\bn[12]\s*(?:=|is)\s*({NUMBER})", cleaned, re.I)
    ]
    if len(indexes) != 2:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op="brewster_angle",
        physics_params={"n1": indexes[0], "n2": indexes[1]},
        physics_units={"n1": "", "n2": ""},
        operation="solve",
    )


def _slit(cleaned: str, op: str, slit_words: tuple[str, ...]) -> PhysicsIntent | None:
    """A slit pattern from its wavelength, screen distance and slit size (``d``)."""
    wavelength = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("wavelength",), require_keyword=True
    )
    screen = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        ("screen distance", "to the screen"),
        require_keyword=True,
    )
    slit = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, slit_words, require_keyword=True
    )
    if wavelength is None or screen is None or slit is None:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op=op,
        physics_params={"wavelength": wavelength[0], "L": screen[0], "d": slit[0]},
        physics_units={
            "wavelength": wavelength[1] or "m",
            "L": screen[1] or "m",
            "d": slit[1] or "m",
        },
        operation="solve",
    )


def _double_slit(cleaned: str) -> PhysicsIntent | None:
    """The fringe spacing λL/d."""
    return _slit(cleaned, "double_slit_fringe_spacing", ("slit separation", "slits"))


def _single_slit(cleaned: str) -> PhysicsIntent | None:
    """The width of the central maximum, 2λL/a."""
    return _slit(cleaned, "diffraction_central_width", ("slit width", "aperture"))


def _lens_power(cleaned: str) -> PhysicsIntent | None:
    """P = 1/f, in dioptres."""
    focal = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("focal length", "focal"), require_keyword=True
    )
    if focal is None:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op="lens_power",
        physics_params={"focal": focal[0]},
        physics_units={"focal": focal[1] or "m"},
        operation="solve",
    )


def _index_values(cleaned: str) -> list[float]:
    """Every refractive index the question writes."""
    return [
        float(m.group(1))
        for m in re.finditer(
            r"(?:refractive\s+index|index\s+of\s+refraction)\s*(?:of|is|=)?\s*"
            r"(-?\d+(?:\.\d+)?)",
            cleaned,
            re.IGNORECASE,
        )
    ]


def _critical_angle(cleaned: str) -> PhysicsIntent | None:
    """sin θ_c = 1/n, from one index above 1."""
    index_values = _index_values(cleaned)
    if len(index_values) != 1 or index_values[0] <= 1:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op="critical_angle",
        physics_params={"n1": index_values[0]},
        physics_units={"n1": ""},
        operation="solve",
    )


def _refraction_angles(cleaned: str) -> list[float]:
    angles = [float(m.group(1)) for m in INCLINE_ANGLE_RE.finditer(cleaned)]
    if len(angles) < 2:
        # "bends from 30 to 20 degrees" puts the unit on the second angle only,
        # so the scan above sees one number where the question gave two.
        pair = re.search(
            rf"from\s+(-?\d+(?:\.\d+)?)\s*{DEGREE_WORD}?\s*to\s+"
            rf"({DECIMAL})\s*{DEGREE_WORD}",
            cleaned,
            re.IGNORECASE,
        )
        if pair is not None:
            angles = [float(pair.group(1)), float(pair.group(2))]
    return angles


def _refractive_index(cleaned: str) -> PhysicsIntent | None:
    """The index from Snell's two angles, or from the speed of light in the medium."""
    index_values = _index_values(cleaned)
    angles = _refraction_angles(cleaned)
    # n = sin(t1) / sin(t2) when both angles are given and the index is not.
    if len(angles) == 2 and not index_values:
        return PhysicsIntent(
            kind="optics",
            physics_op="refractive_index",
            physics_params={"angle": angles[0], "angle2": angles[1]},
            physics_units={"angle": "deg", "angle2": "deg"},
            operation="solve",
        )
    medium_speed = find_value_with_specific_unit(
        cleaned,
        VELOCITY_UNIT_PATTERN,
        ("travels", "speed", "in glass", "in water", "in the medium"),
    )
    if medium_speed is not None and not index_values:
        return PhysicsIntent(
            kind="optics",
            physics_op="refractive_index",
            physics_params={"v_wave": medium_speed[0]},
            physics_units={"v_wave": medium_speed[1] or "m/s"},
            operation="solve",
        )
    return None


def _focal_length(cleaned: str) -> tuple[float, str] | None:
    focal_match = re.search(
        rf"\bfocal(?:\s+length)?\b\s*(?:of|is|=|:)?\s*({NUMBER})\s*"
        rf"({LENGTH_UNIT_PATTERN})(?![A-Za-z0-9/^])",
        cleaned,
        re.IGNORECASE,
    )
    return (
        (float(focal_match.group(1)), focal_match.group(2))
        if focal_match is not None
        else find_value_with_specific_unit(
            cleaned, LENGTH_UNIT_PATTERN, ("focal length", "focal"), require_keyword=True
        )
    )


def _object_length(cleaned: str) -> tuple[float, str] | None:
    """The object's distance, or its height when the question gives one."""
    obj_match = re.search(
        rf"\bobject(?:\s+distance)?\b\s*(?:of|is|=|:)?\s*({NUMBER})\s*"
        rf"({LENGTH_UNIT_PATTERN})(?![A-Za-z0-9/^])",
        cleaned,
        re.IGNORECASE,
    ) or re.search(
        # "An object is placed 15 cm from the mirror": the object's own
        # sentence. The nearest number was the focal length just before it.
        rf"\bobject\b[^.?!]{{0,30}}?\b(?:placed|located|positioned|sits|is)\s+(?:at\s+)?"
        rf"({NUMBER})\s*({LENGTH_UNIT_PATTERN})(?![A-Za-z0-9/^])",
        cleaned,
        re.IGNORECASE,
    )
    return (
        (float(obj_match.group(1)), obj_match.group(2))
        if obj_match is not None
        else find_value_with_specific_unit(
            cleaned, LENGTH_UNIT_PATTERN, ("object",), require_keyword=True
        )
    )


def _magnification(cleaned: str) -> PhysicsIntent | None:
    """m = h_image / h_object, of an image not called real or inverted, not placed (a real
    image's place is its inverting side) and with no height signed: unsigned heights
    certified +3 for "a real, inverted image 6 cm tall" of a 2 cm object (it is -3)."""
    if inverted_image(cleaned) or places_named(cleaned) or signed_distances(cleaned):
        return None
    obj = _object_length(cleaned)
    # Heights only: "the image forms 60 cm from the lens" is a distance,
    # and m = -v/u (the catalog binder) answers that one.
    img = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("image",), require_keyword=True
    )
    if img is None or obj is None or _HEIGHT_RE.search(cleaned.lower()) is None:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op="magnification",
        physics_params={"h_img": img[0], "h_obj": obj[0]},
        physics_units={"h_img": img[1] or "m", "h_obj": obj[1] or "m"},
        operation="solve",
    )


def image_distance(cleaned: str) -> PhysicsIntent | None:
    """1/f = 1/u + 1/v, from a focal length and an object distance, all real-is-positive: a
    distance given its sign is another convention, and an upright image from an element
    not named converging may be a convex mirror's ("A mirror forms an erect image")."""
    if signed_distances(cleaned) or (upright_image(cleaned) and not converging_element(cleaned)):
        return None
    focal = _focal_length(cleaned)
    obj = _object_length(cleaned)
    if focal is None or obj is None:
        return None
    # Only the ray diagram reads it: a concave mirror reflects, a lens transmits.
    mirror = {"mirror": 1.0} if "mirror" in cleaned.lower() else {}
    return PhysicsIntent(
        kind="optics",
        physics_op="image_distance",
        physics_params={"focal": focal[0], "d_obj": obj[0], **mirror},
        physics_units={
            "focal": focal[1] or "m",
            "d_obj": obj[1] or "m",
            **dict.fromkeys(mirror, ""),
        },
        operation="solve",
    )


# Each named law and the phrases that name it, tried in this order. A question
# that names one is answered or declined by that law alone.
NAMED_OPTICS_LAWS: tuple[tuple[tuple[str, ...], Callable[[str], PhysicsIntent | None]], ...] = (
    (("malus",), _malus),
    (("brewster",), _brewster),
    (("double slit", "double-slit", "fringe spacing"), _double_slit),
    (("single slit", "single-slit"), _single_slit),
    (("lens power",), _lens_power),
    (("critical angle",), _critical_angle),
    (("refractive index", "index of refraction", "snell"), _refractive_index),
    (("magnification",), _magnification),
)
