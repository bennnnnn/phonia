"""Tension and vector extractors: Atwood, a vertical rope, resultants and components."""

from __future__ import annotations

import re

from app.modules.physics.extractors.angles import INCLINE_ANGLE_RE
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import DECIMAL, DEGREE_WORD
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.si import to_si
from app.services.text_match import has_equation

_TENSION_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\A(?=.*\btension\b)(?=.*\d\s*(?:kg|lbs?|oz)\b)"
        r"(?=.*(?:lift|rais|hoist|hang|suspend|hold|support|lower|descend|elevator))",
        re.IGNORECASE | re.DOTALL,
    ),
    # An Atwood pair often never says "tension" at all.
    re.compile(r"\batwood\b", re.IGNORECASE),
    re.compile(r"\bpulley\b.{0,80}?\d\s*(?:kg|lbs?|oz)\b", re.IGNORECASE),
    re.compile(r"\d\s*(?:kg|lbs?|oz)\b.{0,80}?\bpulley\b", re.IGNORECASE),
)

_TENSION_UP_RE = re.compile(
    r"\blift(?:s|ing|ed)?\b|\brais(?:e|es|ing|ed)\b|\bhoist\w*\b|\bpull(?:s|ed|ing)?\s+up\b"
    r"|\bupwards?\b|\bris(?:e|es|ing)\b|\bascend\w*\b|\baccelerat\w*\s+up\w*\b",
    re.IGNORECASE,
)

_TENSION_DOWN_RE = re.compile(
    r"\blower(?:s|ing|ed)?\b|\bdescend\w*\b|\bdownwards?\b|\bfall(?:s|ing)\b|\bdropp?(?:s|ing|ed)\b",
    re.IGNORECASE,
)

_TENSION_STATIC_RE = re.compile(
    r"\bhang(?:s|ing)?\b|\bsuspend\w*\b|\bhold(?:s|ing)?\b|\bsupport(?:s|ing)?\b"
    r"|\bstationary\b|\bat rest\b|\bequilibrium\b",
    re.IGNORECASE,
)

_UNSUPPORTED_TENSION_CONTEXT = (
    "incline",
    "ramp",
    "slope",
    "angle",
    "degree",
    "°",
    "friction",
    "coefficient",
    "horizontal",
    "floor",
    "table",
    "across",
    "two ropes",
    "both ropes",
    "each rope",
    "two cables",
    "both cables",
    "each cable",
    "two strings",
    "each string",
)


def _extract_tension_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, (), _TENSION_CUE_RES):
        return None
    if any(word in lower for word in _UNSUPPORTED_TENSION_CONTEXT):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    masses = ordered_values(cleaned, r"kg|lbs?|oz")
    if not masses:
        return None

    # --- Atwood: two masses sharing one pulley --------------------------------
    is_pair = "atwood" in lower or "pulley" in lower
    if is_pair and len(masses) >= 2:
        # The heavier mass descends, so ordering them here makes the sign of
        # the acceleration a property of the physics rather than of the
        # sentence. Its magnitude is what the question asks for either way.
        heavy, light = sorted(
            (masses[0], masses[1]),
            key=lambda pair: to_si(pair[0], pair[1] or "kg"),
            reverse=True,
        )
        return PhysicsIntent(
            kind="force",
            physics_op="atwood",
            physics_params={"m1": heavy[0], "m2": light[0]},
            physics_units={"m1": heavy[1] or "kg", "m2": light[1] or "kg"},
            operation="solve",
        )
    if is_pair:
        # A pulley with one mass named is an incomplete Atwood, not a hanging
        # mass: the rope runs over the pulley to something we were not told
        # about. Refusing beats assuming the other side is fixed.
        return None

    # --- a single rope, which must be vertical -------------------------------
    goes_up = _TENSION_UP_RE.search(cleaned) is not None
    goes_down = _TENSION_DOWN_RE.search(cleaned) is not None
    is_static = _TENSION_STATIC_RE.search(cleaned) is not None
    if not (goes_up or goes_down or is_static):
        return None

    params: dict[str, float] = {"m": masses[0][0]}
    units: dict[str, str] = {"m": masses[0][1] or "kg"}
    accel = find_value_with_specific_unit(
        cleaned,
        r"m/s\^?2|m/s2",
        ("acceleration", "accelerates", "accelerating", "accelerated"),
    )
    if accel is not None:
        value, unit = accel
        # Down is the only direction that has to be stated; "supporting a mass
        # accelerating at 2 m/s^2" reads as upward, which is what P2's example
        # meant by 59.05 N.
        params["a"] = -value if goes_down else value
        units["a"] = unit or "m/s^2"

    return PhysicsIntent(
        kind="force",
        physics_op="tension",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


_VECTOR_FORCE_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bresultant\b.{0,80}?\d\s*N\b", re.IGNORECASE),
    re.compile(r"\d\s*N\b.{0,80}?\bresultant\b", re.IGNORECASE),
    re.compile(
        rf"\A(?=.*\b(?:resolv\w*|components?)\b)(?=.*\d\s*N\b)(?=.*\d\s*{DEGREE_WORD})",
        re.IGNORECASE | re.DOTALL,
    ),
)

_PERPENDICULAR_RE = re.compile(
    rf"\bperpendicular\b|\bright angles?\b|\bat 90\s*{DEGREE_WORD}"
    r"|\b(?:north|south)\b.{0,60}?\b(?:east|west)\b|\b(?:east|west)\b.{0,60}?\b(?:north|south)\b"
    r"|\bhorizontal\b.{0,60}?\bvertical\b|\bvertical\b.{0,60}?\bhorizontal\b",
    re.IGNORECASE,
)

_ANGLE_BETWEEN_RE = re.compile(
    rf"({DECIMAL})\s*{DEGREE_WORD}(?:[^.]{{0,40}}?"
    r"(?:to each other|between them|apart|to one another))",
    re.IGNORECASE,
)

_RESOLVE_RE = re.compile(r"\bresolv\w*\b|\bcomponents?\b", re.IGNORECASE)


def _extract_vector_force_intent(cleaned: str) -> PhysicsIntent | None:
    if not has_cue(cleaned.lower(), (), _VECTOR_FORCE_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    forces = ordered_values(cleaned, r"N")

    # --- resultant of two forces -------------------------------------------
    if "resultant" in cleaned.lower() and len(forces) >= 2:
        between = _ANGLE_BETWEEN_RE.search(cleaned)
        if between is not None:
            phi = float(between.group(1))
        elif _PERPENDICULAR_RE.search(cleaned):
            phi = 90.0
        else:
            # Two forces and no stated geometry is not a resultant question
            # anyone can answer — the angle between them is the whole problem.
            return None
        return PhysicsIntent(
            kind="force",
            physics_op="resultant_force",
            physics_params={"F1": forces[0][0], "F2": forces[1][0], "angle": phi},
            physics_units={"F1": "N", "F2": "N", "angle": "deg"},
            operation="solve",
        )

    # --- one force split into components ------------------------------------
    if _RESOLVE_RE.search(cleaned) and forces:
        angle = INCLINE_ANGLE_RE.search(cleaned)
        if angle is None:
            return None
        return PhysicsIntent(
            kind="force",
            physics_op="resolve_force",
            physics_params={"F": forces[0][0], "angle": float(angle.group(1))},
            physics_units={"F": forces[0][1] or "N", "angle": "deg"},
            operation="solve",
        )

    return None
