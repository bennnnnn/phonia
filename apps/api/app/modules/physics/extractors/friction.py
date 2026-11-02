"""Friction extractors: f = muN, inclines, the slipping angle, minimum force."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.physics.extractors.angles import INCLINE_ANGLE_RE
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import DEGREE_WORD
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_FRICTION_CUES = (
    "normal force",
    "frictionless",
)

_FRICTION_SUBJECT = r"friction|frictional|incline|inclined|ramp"

_FRICTION_GIVEN = (
    r"coefficient|(?:\\?(?:\bmu|\u03bc)\s*_?\s*[sk]?\s*(?:=|is))|"
    rf"(?<!\d)\d+\s*{DEGREE_WORD}"
)

_FRICTION_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"(?:{_FRICTION_SUBJECT}).{{0,80}}?(?:{_FRICTION_GIVEN})", re.IGNORECASE),
    re.compile(rf"(?:{_FRICTION_GIVEN}).{{0,80}}?(?:{_FRICTION_SUBJECT})", re.IGNORECASE),
    re.compile(
        r"\b(?:minimum|least|smallest)\s+(?:horizontal\s+)?force\b.{0,100}?"
        r"\b(?:mu|μ)\s*(?:=|is)\s*\d",
        re.IGNORECASE,
    ),
)

_FRICTION_FORCE_ASK_RE = re.compile(
    r"friction(?:al)?\s+force|force\s+of\s+friction"
    r"|(?:find|calculate|determine|compute|what\s+is)\s+the\s+friction\b",
    re.IGNORECASE,
)

_MU_RE = re.compile(
    r"(?:coefficient\s+of\s+(?:kinetic\s+|static\s+)?friction\s*(?:of|=|is)?\s*"
    r"|coefficient\s*(?:of|=|is)?\s*"
    r"|\bmu(?:_?[ks])?\s+is\s+|\bmu(?:_?[ks])?\s*=\s*"
    r"|\u03bc(?:_?[ks])?\s+is\s+|\u03bc(?:_?[ks])?\s*=\s*)"
    r"(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_MU_STATIC_RE = re.compile(
    r"(?:\\?(?:\bmu|\u03bc)\s*_?\s*(?:s|\u209b)|"
    r"coefficient\s+of\s+static\s+friction|static\s+(?:coefficient\s+of\s+)?friction|"
    r"static\s+friction\s+coefficient)"
    r"\s*(?:=|is|of)?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_MU_KINETIC_RE = re.compile(
    r"(?:\\?(?:\bmu|\u03bc)\s*_?\s*(?:k|\u2096)|"
    r"coefficient\s+of\s+kinetic\s+friction|kinetic\s+(?:coefficient\s+of\s+)?friction)"
    r"\s*(?:=|is|of)?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_MU_ASK_RE = re.compile(
    r"(?:what|find|calculate|determine|compute)\b[^.?!]{0,40}?"
    r"\bcoefficient\s+of\s+(?:kinetic\s+|static\s+)?friction\b"
    r"|\bcoefficient\s+of\s+(?:kinetic\s+|static\s+)?friction\s*\?",
    re.IGNORECASE,
)

_SLIPPING_RE = re.compile(
    r"\bstarts?\s+to\s+(?:slide|slip|move)\b|\bbegins?\s+to\s+(?:slide|slip|move)\b"
    r"|\bslipping\s+begins?\b|\bjust\s+(?:slides?|slips?|begins)\b"
    r"|\bslides?\s+(?:at|when|down\s+a)\b|\bon\s+the\s+point\s+of\b"
    r"|\bjust\s+prevents?\s+(?:it\s+from\s+)?slid(?:e|ing)\b",
    re.IGNORECASE,
)

_SLIDING_ASK_RE = re.compile(
    r"\b(?:does|did|will|would|can|could|whether)\b[^.?!]{0,80}?"
    r"\b(?:slide|slid(?:e|es|ing)?|slip(?:s|ped|ping)?|mov(?:e|es|ing))\b"
    r"|\b(?:start|starts|started|begin|begins|began)\s+(?:to\s+)?"
    r"(?:slide|slid(?:e|es|ing)?|slip(?:s|ped|ping)?|mov(?:e|es|ing))\b",
    re.IGNORECASE,
)

_MIN_FORCE_ASK_RE = re.compile(
    r"\bminimum\s+force\b|\bleast\s+force\b|\bsmallest\s+force\b"
    r"|\bforce\s+(?:is\s+)?(?:needed|required)\s+to\s+(?:start|move|push|pull|budge)\b"
    r"|\bforce\s+to\s+(?:start|move|push|pull|budge)\b",
    re.IGNORECASE,
)

_REST = re.compile(r"\b(?:rests|resting|stationary|at rest|equilibrium)\b", re.IGNORECASE)
_INITIAL_REST = re.compile(
    r"\b(?:initially\s+(?:at\s+rest|stationary)|released\s+from\s+rest|starts?\s+from\s+rest)\b",
    re.IGNORECASE,
)
_UPHILL = re.compile(r"\b(?:moves?|moving|slides?|sliding|travell?ing)\s+up\b", re.IGNORECASE)
_MOVING = re.compile(r"\b(?:moves?|moving|slides?|sliding|travell?ing)\b", re.IGNORECASE)


def _extract_friction_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _FRICTION_CUES, _FRICTION_CUE_RES):
        return None
    if "net force" in lower:
        # A different quantity. The force extractor refuses it via
        # _UNSUPPORTED_FORCE_CONTEXT rather than guessing, which is right.
        return None
    without_coefficients = _MU_RE.sub("", _MU_STATIC_RE.sub("", _MU_KINETIC_RE.sub("", cleaned)))
    if has_equation(strip_param_assignments(without_coefficients)):
        return None

    mass = find_value_with_specific_unit(
        cleaned, r"kg|g|mg|lb|lbs|oz", ("mass", "block", "box", "crate", "object", "body")
    )

    frictionless = "frictionless" in lower
    mu_match = _MU_RE.search(cleaned)
    mu = 0.0 if frictionless else (float(mu_match.group(1)) if mu_match else None)
    static_mu_match = _MU_STATIC_RE.search(cleaned)

    angle_match = INCLINE_ANGLE_RE.search(cleaned)
    angle = float(angle_match.group(1)) if angle_match else 0.0

    wants_normal = "normal force" in lower
    wants_acceleration = "acceleration" in lower or "accelerate" in lower
    wants_friction = _FRICTION_FORCE_ASK_RE.search(cleaned) is not None and not frictionless
    wants_coefficient = _MU_ASK_RE.search(cleaned) is not None
    wants_min_force = _MIN_FORCE_ASK_RE.search(cleaned) is not None
    wants_sliding = _SLIDING_ASK_RE.search(cleaned) is not None

    op: Literal[
        "friction_force",
        "normal_force",
        "incline_acceleration",
        "friction_coefficient",
        "minimum_force",
        "incline_sliding",
    ]
    if wants_coefficient:
        # mu = tan(theta) holds only at the angle where it *starts* to slide.
        # On any other incline the angle says nothing about mu, so the slipping
        # wording is required rather than assumed.
        op = "friction_coefficient"
        if angle == 0.0 or mu is not None or not _SLIPPING_RE.search(cleaned):
            return None
    elif wants_min_force:
        op = "minimum_force"
        if mass is None or mu is None:
            return None
        if angle != 0.0:
            # On a slope the minimum force is mu*m*g*cos(t) + m*g*sin(t), a
            # different formula. Not solved here, so not guessed at either.
            return None
    elif wants_acceleration:
        op = "incline_acceleration"
        # No mass requirement here, and that is the point: a = g(sin t - mu cos t)
        # is mass-independent, which is the whole reason the incline result is
        # worth teaching. Demanding a mass would reject the textbook phrasing
        # ("a block on a frictionless 30 degree incline") that omits it.
        if mu is None:
            # Without a coefficient this is only solvable if it is stated to be
            # frictionless — otherwise the answer needs a number nobody gave.
            return None
        if angle == 0.0:
            # "acceleration" with no incline angle is an F = ma question, not
            # this one. Leave it for the force extractor.
            return None
    elif wants_sliding:
        op = "incline_sliding"
        if angle == 0.0:
            return None
        if static_mu_match is None:
            # Neither a kinetic nor an unqualified coefficient establishes
            # the maximum static friction available before motion starts.
            return None
        mu = float(static_mu_match.group(1))
    elif wants_normal:
        op = "normal_force"
        if mass is None:
            return None
        # N = mg cos(theta) needs no coefficient. One that was never stated
        # must not show as a given: "rests on a 30° incline" is not "μ = 0".
    elif wants_friction:
        op = "friction_force"
        # A block at rest on a slope is held by mg sin(theta) of static
        # friction, whatever the coefficient. Only a sliding block needs one.
        held = (
            mu is None
            and angle != 0.0
            and _REST.search(cleaned) is not None
            and _INITIAL_REST.search(cleaned) is None
            and _MOVING.search(cleaned) is None
        )
        if mass is None or (mu is None and not held):
            return None
    else:
        return None

    params: dict[str, float] = {"angle": angle, "g": detect_gravity(cleaned)}
    units: dict[str, str] = {
        "angle": "rad" if re.search(r"\b(?:rad|radians)\b", lower) else "deg",
        "g": "m/s^2",
    }
    # For `friction_coefficient` mu is the answer, not a given, so there is
    # none to pass. Every other op has already refused a missing one above.
    if op == "incline_sliding":
        params["mu_s"] = mu if mu is not None else 0.0
        units["mu_s"] = ""
    elif mu is not None:
        params["mu"] = mu
        units["mu"] = ""
    if mass is not None:
        params["m"] = mass[0]
        units["m"] = mass[1] or "kg"
    if op == "normal_force" and angle != 0.0 and not frictionless:
        # The diagram of a block resting on a slope shows what holds it there.
        if _REST.search(cleaned) is not None and _MOVING.search(cleaned) is None:
            params["static_equilibrium"] = 1.0
            units["static_equilibrium"] = ""
    if op in {"friction_force", "incline_acceleration"}:
        initially_at_rest = _INITIAL_REST.search(cleaned) is not None
        at_rest = _REST.search(cleaned) is not None and not initially_at_rest
        moving = _MOVING.search(cleaned) is not None
        kinetic = "kinetic" in lower
        static = "static" in lower
        limiting = any(
            word in lower for word in ("maximum", "limiting", "starts to", "just slides")
        )
        if (at_rest and (moving or kinetic)) or (static and moving):
            return None
        if (at_rest or static) and not limiting and not frictionless:
            # A second horizontal/applied force needs another force balance.
            if re.search(r"\b(?:push|pull|applied|external)\w*\b", cleaned, re.IGNORECASE):
                return None
            params["static_equilibrium"] = 1.0
            units["static_equilibrium"] = ""
        if moving or kinetic:
            params["motion_sign"] = -1.0 if _UPHILL.search(cleaned) else 1.0
            units["motion_sign"] = ""
        if initially_at_rest:
            params["released_from_rest"] = 1.0
            units["released_from_rest"] = ""
    return PhysicsIntent(
        kind="friction",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
