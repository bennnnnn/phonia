"""Optics extractors: lenses, mirrors, refraction, magnification.

The law of reflection is tried first; then the first law a question names
(`optics_laws.NAMED_OPTICS_LAWS`) answers or declines it; else the thin-lens image
distance.
"""

from __future__ import annotations

import re

from app.modules.physics.extractors.angles import INCLINE_ANGLE_RE
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.optics_laws import NAMED_OPTICS_LAWS, image_distance
from app.modules.physics.extractors.unit_patterns import NUMBER
from app.modules.physics.optic_elements import diverging_element
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.ask import ASK_VERBS
from app.services.text_match import has_equation

_OPTICS_CUES = (
    "focal length",
    "refractive index",
    "critical angle",
    "index of refraction",
    "converging lens",
    "convex lens",
    "concave mirror",
    "converging mirror",
    "magnification",
    "snell",
    "lens power",
    "double slit",
    "double-slit",
    "fringe spacing",
    "single slit diffraction",
    "single-slit diffraction",
    "malus",
    "brewster",
    # Not a bare "mirror": "I bought a bathroom mirror for 30 dollars" is not optics.
    "plane mirror",
    "angle of reflection",
    "angle of incidence",
    "reflected ray",
)

# The law of reflection. One angle is given, against the normal or against the
# mirror's surface, and the asked angle is against one of them too.
_NOT_REFLECTION_RE = re.compile(
    r"refract|snell|critical angle|index of refraction|\blens|focal|concave|convex"
)
_NORMAL_REF_RE = re.compile(r"\bnormal\b|\bangle\s+of\s+incidence\b|\bincident\s+angle\b")
_SURFACE_REF_RE = re.compile(r"\b(?:surface|mirror|glancing|grazing)\b")
_SURFACE_ASK_RE = re.compile(
    r"\b(?:with|and|to|from|against|relative\s+to)\s+(?:the\s+)?(?:plane\s+)?"
    r"(?:mirror(?:'s)?(?:\s+surface)?|surface)\b"
)
_BETWEEN_RAYS_RE = re.compile(
    r"between\s+the\s+(?:incident|incoming)\s+(?:ray\s+)?and\s+(?:the\s+)?reflected"
    r"|between\s+the\s+reflected\s+(?:ray\s+)?and\s+(?:the\s+)?(?:incident|incoming)"
)
_CLAUSE_END_RE = re.compile(r"[.?!;](?:\s|$)")
# "If the angle of incidence is 42.5 degrees, what is ...": the comma ends the given.
_GIVEN_END_RE = re.compile(r"[.?!;,](?:\s|$)")
# "the angle between the incident ray and the mirror is 50 degrees"
_SURFACE_BEFORE_RE = re.compile(
    r"\b(?:between|with)\b[^.?!]{0,40}\b(?:mirror|surface)\s+(?:is|of|=|measures)\s*$"
)
_CLAUSE_LEAD_RE = re.compile(r"\b(?:when|if|where|as|after|while)\b")


def _reflection_intent(cleaned: str) -> PhysicsIntent | None:
    """35 degrees to a mirror's surface is 55 to the normal, and so is the reflection.

    Asked of the model, it answered 35. An angle given without saying which
    line it is measured from is left alone: guessing the line is the error.
    """
    lower = cleaned.lower()
    if "reflect" not in lower or _NOT_REFLECTION_RE.search(lower):
        return None
    angles = list(INCLINE_ANGLE_RE.finditer(cleaned))
    if len(angles) != 1:
        return None
    match = angles[0]
    value = float(match.group(1))
    if not 0 <= value <= 90:
        return None
    # The given angle's clause: from its sentence start, or from "when" in a
    # one-sentence question, to the end of its sentence.
    after = lower[match.end() :]
    end = _GIVEN_END_RE.search(after)
    clause_end = match.end() + (end.start() if end else len(after))
    clause_start = max(
        (found.end() for found in _CLAUSE_END_RE.finditer(lower, 0, match.start())), default=0
    )
    lead = list(_CLAUSE_LEAD_RE.finditer(lower, clause_start, match.start()))
    if lead:
        clause_start = lead[-1].start()
    given_clause = lower[clause_start:clause_end]
    if _NORMAL_REF_RE.search(given_clause):
        param = "angle"
    elif (
        _SURFACE_REF_RE.search(lower[match.end() : clause_end])
        or _SURFACE_BEFORE_RE.search(lower[clause_start : match.start()])
        or re.search(r"\b(?:glancing|grazing)\b", given_clause)
    ):
        param = "angle_surface"
    else:
        return None
    asked = lower[:clause_start] + " " + lower[clause_end:]
    if not ASK_VERBS.search(asked) and "?" not in asked:
        return None
    if _BETWEEN_RAYS_RE.search(asked):
        op = "reflection_ray_angle"
    elif _SURFACE_ASK_RE.search(asked) and "normal" not in asked:
        op = "reflection_surface_angle"
    elif "normal" in asked or "angle of reflection" in asked or "reflected" in asked:
        op = "reflection_angle"
    else:
        return None
    return PhysicsIntent(
        kind="optics",
        physics_op=op,
        physics_params={param: value},
        physics_units={param: "deg"},
        operation="solve",
    )


def _extract_optics_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _OPTICS_CUES):
        return None
    without_index_assignments = re.sub(r"\bn[12]\s*=\s*" + NUMBER, "", cleaned, flags=re.I)
    if has_equation(strip_param_assignments(without_index_assignments)):
        return None
    if diverging_element(cleaned):
        return None
    # The catalog owns a microscope and the lens-maker equation. This reader
    # would treat "objective" as an object distance.
    if "microscope" in lower or "lens maker" in lower or "lensmaker" in lower:
        return None

    reflection = _reflection_intent(cleaned)
    if reflection is not None:
        return reflection
    for names, law in NAMED_OPTICS_LAWS:
        if any(name in lower for name in names):
            return law(cleaned)
    return image_distance(cleaned)
