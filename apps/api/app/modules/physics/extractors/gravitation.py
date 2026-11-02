"""Gravitation: Newton's law between two bodies, surface gravity, orbits and escape speed."""

from __future__ import annotations

import re

from app.modules.physics.bodies import named_body
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, NUMBER
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_GRAVITATION_CUES = (
    "gravitational force",
    "gravitational attraction",
    "gravitational constant",
    "gravitational field",
    "orbital velocity",
    "orbital speed",
    "escape velocity",
    "escape speed",
    "surface gravity",
    "gravitational potential",
    "newton's law of gravitation",
    "law of universal gravitation",
)

_GRAVITATION_CUE_RES: tuple[re.Pattern[str], ...] = (
    # "the force between two 1000 kg masses 10 m apart" names no topic word.
    re.compile(r"\bforce\s+between\b.{0,80}?\d\s*(?:kg|tonnes?|tons?)\b", re.IGNORECASE),
    re.compile(r"\bg\s+on\s+a\s+planet\b", re.IGNORECASE),
)

_IDENTICAL_PAIR_RE = re.compile(
    r"\b(?:two|a\s+pair\s+of|both)\b[^.?!]{0,40}?"
    r"\b(?:masses|spheres|balls|objects|bodies|blocks|stars|planets|satellites)\b",
    re.IGNORECASE,
)


def _extract_gravitation_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _GRAVITATION_CUES, _GRAVITATION_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    body = named_body(lower)
    masses = ordered_values(cleaned, r"kg|tonnes?|tons?")
    radius = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("radius", "radii"), require_keyword=True
    )
    if radius is None:
        radius_assignment = re.search(
            rf"\bR\s*=\s*({NUMBER})\s*({LENGTH_UNIT_PATTERN})(?![A-Za-z0-9/^])",
            cleaned,
        )
        if radius_assignment is not None:
            radius = (float(radius_assignment.group(1)), radius_assignment.group(2))
    altitude = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("above", "altitude", "height"), require_keyword=True
    )
    separation = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("apart", "separation", "between", "distance")
    )

    if "escape" in lower:
        planet_mass, planet_radius = _resolve_body(body, masses, radius)
        if planet_mass is None or planet_radius is None:
            return None
        return PhysicsIntent(
            kind="gravitation",
            physics_op="escape_velocity",
            physics_params={"M": planet_mass, "radius_body": planet_radius},
            physics_units={"M": "kg", "radius_body": "m"},
            operation="solve",
        )

    if "orbital" in lower:
        # Vis-viva needs the semi-major axis. Circular orbital speed would drop it.
        if re.search(r"semi-?major|vis-?viva", lower):
            return None
        planet_mass, planet_radius = _resolve_body(body, masses, radius)
        if planet_mass is None or planet_radius is None:
            return None
        # An orbit is measured from the centre, so an altitude adds to the
        # radius - but the two are rarely in the same unit ("400 km above the
        # earth"), so they are passed separately and added after `to_si`
        # rather than summed here in whatever units they arrived in.
        params: dict[str, float] = {"M": planet_mass, "radius_body": planet_radius}
        units: dict[str, str] = {"M": "kg", "radius_body": "m"}
        if altitude is not None:
            params["altitude"] = altitude[0]
            units["altitude"] = altitude[1] or "m"
        return PhysicsIntent(
            kind="gravitation",
            physics_op="orbital_velocity",
            physics_params=params,
            physics_units=units,
            operation="solve",
        )

    if "gravitational potential" in lower and "energy" not in lower and "surface" in lower:
        planet_mass, planet_radius = _resolve_body(body, masses, radius)
        if planet_mass is None or planet_radius is None:
            return None
        return PhysicsIntent(
            kind="gravitation",
            physics_op="gravitational_potential",
            physics_params={"M": planet_mass, "r": planet_radius},
            physics_units={"M": "kg", "r": "m"},
            operation="solve",
        )

    if "surface gravity" in lower or "gravitational field" in lower or "g on a planet" in lower:
        planet_mass, planet_radius = _resolve_body(body, masses, radius)
        if planet_mass is None or planet_radius is None:
            return None
        return PhysicsIntent(
            kind="gravitation",
            physics_op="surface_gravity",
            physics_params={"M": planet_mass, "radius_body": planet_radius},
            physics_units={"M": "kg", "radius_body": "m"},
            operation="solve",
        )

    # F = G M m / r^2 between two stated masses. "two 1000 kg masses" gives one
    # number for both bodies, which is the commonest wording of this question.
    if len(masses) == 1 and separation is not None and _IDENTICAL_PAIR_RE.search(cleaned):
        masses = [masses[0], masses[0]]
    if len(masses) >= 2 and separation is not None:
        return PhysicsIntent(
            kind="gravitation",
            physics_op="gravitational_force",
            physics_params={"m1": masses[0][0], "m2": masses[1][0], "r": separation[0]},
            physics_units={
                "m1": masses[0][1] or "kg",
                "m2": masses[1][1] or "kg",
                "r": separation[1] or "m",
            },
            operation="solve",
        )
    return None


def _resolve_body(
    body: tuple[float, float] | None,
    masses: list[tuple[float, str]],
    radius: tuple[float, str] | None,
) -> tuple[float | None, float | None]:
    """A named body, or a stated mass and radius - never a mix of guesses.

    A question that *describes* a planet without naming it and supplies only
    one of the two is refused: silently finishing it with Earth's other number
    is the same defect as the projectile default, one layer up.
    """
    if body is not None:
        return body
    if masses and radius is not None:
        return masses[0][0], radius[0]
    return None, None
