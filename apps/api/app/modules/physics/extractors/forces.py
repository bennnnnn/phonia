"""Force extractors: F = ma and the net force."""

from __future__ import annotations

import re

from app.modules.physics.ask import asked_dimensions
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.givens import unit_dimension
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_FORCE_CUES = (
    "net force",
    "newton's second law",
    "newtons second law",
    "force of",
    "force required",
    "what is the force",
    "what's the force",
    "find the force",
    "find the mass",
    "acceleration given",
    "given force",
    # Question-first and verb-first shapes ("what force accelerates 5 kg...",
    # "calculate the force on a 5 kg object"). solve_force still needs exactly
    # two of F, m, a with units, so a non-physics "force" sentence returns None.
    "what force",
    "how much force",
    "force needed",
    "force on",
    "force acts",
    "force applied",
    "accelerates at",
    "accelerating at",
    "accelerated at",
)

_UNSUPPORTED_FORCE_CONTEXT = (
    "tension",
    "friction",
    "coefficient",
    "incline",
    "ramp",
    "slope",
    "pulley",
    "normal force",
    "spring",
    "centripetal",
    "buoyan",
)

_FORCE_CUE_RES: tuple[re.Pattern[str], ...] = (
    # A bare physics force symbol is ``f``. Function notation and derivatives
    # (``f(x)``, ``f'(x)``) remain math even when introduced with "find".
    re.compile(r"\b(?:find|calculate|determine|compute)\s+f\b(?!\s*[('])"),
    # "How much external force is required to accelerate a 1500 kg car …" (a grade 7
    # physics book, 2026-10-30): a word before "force" broke "how much force".
    re.compile(
        r"\b(?:how\s+much|what|which|find\s+the|calculate\s+the|determine\s+the)\s+"
        r"(?:external|applied|resultant|unbalanced|total|average)\s+force\b"
    ),
    re.compile(r"\bforce\s+(?:is\s+|was\s+|would\s+be\s+)?(?:needed|required)\b"),
)


_F_MA_DIMENSIONS = frozenset(
    reading[0]
    for unit in ("newton", "kilogram", "meter / second ** 2")
    if (reading := unit_dimension(unit)) is not None
)


# Lifting, an elevator or a launch: the force up is m(g + a), not ma ("What applied force
# is needed to lift a 20 kg box upward at 2 m/s²?" was verified as 40 N; review,
# 2026-10-30). Only the net force asked for is ma there.
_AGAINST_GRAVITY = re.compile(
    r"\b(?:lift(?:s|ed|ing)?|raise[sd]?|raising|hoist\w*|upwards?|elevators?|"
    r"launch\w*|rockets?|vertical(?:ly)?)\b"
)
_NET_FORCE = re.compile(r"\b(?:net|resultant|unbalanced)\s+force\b")


def _extract_force_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _FORCE_CUES, _FORCE_CUE_RES):
        return None
    if any(word in lower for word in _UNSUPPORTED_FORCE_CONTEXT):
        return None
    if _AGAINST_GRAVITY.search(lower) and not _NET_FORCE.search(lower):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    # Mass (m): "mass of 5 kg", "5 kg mass", "5kg object" — use unit-specific
    # search so "20 N" (force) isn't picked up as the mass.
    mass: float | None = None
    mass_unit = "kg"
    mu = find_value_with_specific_unit(
        cleaned,
        r"kg|g|mg|lb|lbs|oz",
        ("mass", "object", "body"),
    )
    if mu is not None:
        mass, mass_unit = mu

    # Force (F): "force of 20 N", "20 N force" — use unit-specific search.
    force: float | None = None
    force_unit = "N"
    fu = find_value_with_specific_unit(cleaned, r"N", ("force",))
    if fu is not None:
        force, force_unit = fu

    # Acceleration (a): "acceleration of 2 m/s^2"
    accel: float | None = None
    accel_unit = "m/s^2"
    au = find_value_with_specific_unit(
        cleaned,
        r"m/s\^?2|m/s2",
        ("acceleration", "accelerates", "accelerated"),
    )
    if au is not None:
        accel, accel_unit = au

    # Need at least two of (mass, force, accel) to solve F = ma.
    known = [v for v in (mass, force, accel) if v is not None]
    if len(known) < 2:
        return None
    # F = ma answers a force, a mass or an acceleration. "How fast is it moving
    # after 5 s" asks for something else, which a catalog law may answer.
    asked = asked_dimensions(cleaned)
    if asked and not set(asked) <= _F_MA_DIMENSIONS:
        return None

    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if mass is not None:
        params["m"] = mass
        units["m"] = mass_unit or "kg"
    if force is not None:
        params["F"] = force
        units["F"] = force_unit or "N"
    if accel is not None:
        params["a"] = accel
        units["a"] = accel_unit or "m/s^2"

    return PhysicsIntent(
        kind="force",
        physics_op="net_force",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
