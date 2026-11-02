"""Circular motion: centripetal force and acceleration, period and angular speed."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.physics.extractors.angles import _stated_angle
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.friction import _MU_RE
from app.modules.physics.extractors.oscillations import _ANGULAR_FREQ_RE
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_CIRCULAR_CUES = (
    "centripetal",
    "circular motion",
    "orbital",
    "banked",
    "vertical circle",
    "loop-the-loop",
    "loop the loop",
)

_ANGULAR_ASK_RE = re.compile(r"\bangular\s+(?:velocity|speed|frequency)\b", re.IGNORECASE)
# The last ask verb. A given named "angular speed" is not the question when
# the verb asks for the centripetal acceleration.
_ASK_VERB_RE = re.compile(
    r"\b(?:find|what|calculate|determine|compute)\b",
    re.IGNORECASE,
)
_CircularOp = Literal[
    "centripetal_force",
    "centripetal_acceleration",
    "orbital_period",
    "angular_velocity",
]
_CIRCULAR_ASKS: tuple[tuple[str, _CircularOp], ...] = (
    ("centripetal acceleration", "centripetal_acceleration"),
    ("centripetal force", "centripetal_force"),
    ("angular velocity", "angular_velocity"),
    ("angular speed", "angular_velocity"),
    ("angular frequency", "angular_velocity"),
    ("orbital period", "orbital_period"),
    ("period", "orbital_period"),
    ("revolution", "orbital_period"),
    ("acceleration", "centripetal_acceleration"),
    ("force", "centripetal_force"),
)

_RPM_RE = re.compile(rf"({NUMBER})\s*(?:rpm|revolutions?\s+per\s+minute)\b", re.IGNORECASE)

_CIRCULAR_CUE_RES: tuple[re.Pattern[str], ...] = (
    # Revolutions of a body: counted ("3 revolutions", "one revolution") or a rate
    # ("revolutions per second"). Not "the French revolution" or a calculus
    # "volume (solid, surface) of revolution".
    # Lookbehinds keep it linear: a leading digit run would retry from every digit.
    re.compile(
        r"(?:(?<=\d)|(?<=\d )|(?<=\bone )|(?<=\ba )|(?<=\beach )|(?<=\bevery )|(?<=\bper )"
        r"|(?<=\bfull )|(?<=\bcomplete )|(?<=\bmany ))revolutions?\b"
        r"|\brevolutions?\s+(?:per|around|about|each|every)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bperiod\b.{0,80}?\bradius\b", re.IGNORECASE),
    re.compile(r"\bradius\b.{0,80}?\bperiod\b", re.IGNORECASE),
    re.compile(
        r"\bangular\s+(?:velocity|speed)\b.{0,80}?\b(?:radius|circular|circle|track|orbit)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:radius|circular|circle|track|orbit)\b.{0,80}?\bangular\s+(?:velocity|speed)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:rotates?|spins?|turns?)\b.{0,80}?\d\s*(?:rpm|revolutions?\s+per\s+minute)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bomega\s*=?.{0,30}?\brad(?:ians?)?/s\b.{0,80}?\bradius\b", re.IGNORECASE),
    re.compile(
        r"\bangular\s+(?:velocity|speed|frequency)\b.{0,80}?\bperiod\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bperiod\b.{0,80}?\bangular\s+(?:velocity|speed|frequency)\b",
        re.IGNORECASE,
    ),
)


_FRICTIONLESS = re.compile(
    r"\b(?:frictionless|no friction|without friction|neglect(?:ing)? friction)\b",
    re.IGNORECASE,
)
_LEVEL_CURVE = re.compile(
    r"\b(?:unbanked|level curve|flat curve|horizontal curve|level road)\b",
    re.IGNORECASE,
)
_BANKED = re.compile(r"\bbanked\b", re.IGNORECASE)
_CONTACT_SCENE = re.compile(
    r"\b(?:vertical circle|loop-the-loop|loop the loop|bucket of water|crest|hill)\b",
    re.IGNORECASE,
)
_CONTACT_ASK = re.compile(
    r"\bat the top\b|\bloses? contact\b|\bleaves? the (?:road|surface|track)\b"
    r"|\bstays? on the (?:road|surface|track)\b",
    re.IGNORECASE,
)
_JUST_COMPLETES = re.compile(r"\bjust completes?\b", re.IGNORECASE)
_ASKS_ANGLE = re.compile(
    r"\b(?:find|what|calculate|determine|compute)\b.{0,48}?\b(?:angle|bank angle)\b",
    re.IGNORECASE,
)
_ASKS_SPEED = re.compile(
    r"\b(?:find|what|calculate|determine|compute)\b.{0,48}?\b(?:speed|velocity)\b"
    r"|\b(?:maximum|max|fastest)\s+speed\b|\bwithout skidding\b",
    re.IGNORECASE,
)


def _asked_circular_op(text: str) -> _CircularOp | None:
    """The circular quantity the question asks for, not a given that shares its name."""
    verbs = list(_ASK_VERB_RE.finditer(text))
    tail = text[verbs[-1].end() :] if verbs else text
    found = [
        (index, operation)
        for phrase, operation in _CIRCULAR_ASKS
        if (index := tail.find(phrase)) >= 0
    ]
    if not found:
        return None
    return min(found)[1]


def _radius(text: str) -> tuple[float, str] | None:
    found = find_value_with_specific_unit(
        text, LENGTH_UNIT_PATTERN, ("radius", "radii"), require_keyword=True
    )
    if found is not None:
        return found
    labeled = re.search(
        rf"\br\s*=\s*({NUMBER})\s*({LENGTH_UNIT_PATTERN})(?![A-Za-z0-9/^])",
        text,
        re.IGNORECASE,
    )
    if labeled is None:
        return None
    return float(labeled.group(1)), labeled.group(2)


def _road_intent(text: str) -> PhysicsIntent | None:
    """Frictionless bank, level curve, or the speed where contact force is zero."""
    radius = _radius(text)
    if radius is None:
        return None
    gravity = detect_gravity(text)
    params: dict[str, float] = {"r": radius[0], "g": gravity}
    units: dict[str, str] = {"r": radius[1] or "m", "g": "m/s^2"}
    if _LEVEL_CURVE.search(text) and not _BANKED.search(text):
        mu = _MU_RE.search(text)
        if mu is None or not _ASKS_SPEED.search(text):
            return None
        params["mu"] = float(mu.group(1))
        units["mu"] = ""
        return PhysicsIntent(
            kind="circular",
            physics_op="level_curve_speed",
            physics_params=params,
            physics_units=units,
            operation="solve",
        )
    if _CONTACT_SCENE.search(text) and _CONTACT_ASK.search(text):
        if _JUST_COMPLETES.search(text) and not re.search(r"\bat the top\b", text, re.IGNORECASE):
            return None
        return PhysicsIntent(
            kind="circular",
            physics_op="contact_speed",
            physics_params=params,
            physics_units=units,
            operation="solve",
        )
    if not _BANKED.search(text):
        return None
    if re.search(r"\bfriction", text, re.IGNORECASE) and not _FRICTIONLESS.search(text):
        return None
    angle = _stated_angle(text)
    speed = find_value_with_specific_unit(text, VELOCITY_UNIT_PATTERN)
    asks_angle = _ASKS_ANGLE.search(text) is not None
    asks_speed = _ASKS_SPEED.search(text) is not None
    if asks_angle and asks_speed:
        return None
    if asks_angle and speed is not None:
        params["v"] = speed[0]
        units["v"] = speed[1] or "m/s"
        return PhysicsIntent(
            kind="circular",
            physics_op="banked_angle",
            physics_params=params,
            physics_units=units,
            operation="solve",
        )
    if asks_speed and angle is not None:
        params["angle"] = angle[0]
        units["angle"] = angle[1]
        return PhysicsIntent(
            kind="circular",
            physics_op="banked_speed",
            physics_params=params,
            physics_units=units,
            operation="solve",
        )
    return None


def _extract_circular_intent(cleaned: str) -> PhysicsIntent | None:
    road = _road_intent(cleaned)
    if road is not None:
        return road
    lower = cleaned.lower()
    if not has_cue(lower, _CIRCULAR_CUES, _CIRCULAR_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    rpm_match = _RPM_RE.search(cleaned)
    if rpm_match is not None and _ANGULAR_ASK_RE.search(cleaned):
        return PhysicsIntent(
            kind="circular",
            physics_op="angular_velocity",
            physics_params={"rpm": float(rpm_match.group(1))},
            physics_units={"rpm": "rpm"},
            operation="solve",
        )

    radius = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("radius", "radii"), require_keyword=True
    )
    speed = find_value_with_specific_unit(cleaned, VELOCITY_UNIT_PATTERN)
    omega = _ANGULAR_FREQ_RE.search(cleaned)
    if radius is None or (speed is None and omega is None):
        # ω = 2π/T needs a period and no tangential speed. Radius is not an input.
        if (
            _ANGULAR_ASK_RE.search(cleaned)
            and speed is None
            and omega is None
            and "period" in lower
        ):
            period = find_value_with_specific_unit(
                cleaned,
                r"seconds?|secs?|sec|s|minutes?|mins?|min",
                ("period",),
                require_keyword=True,
            )
            if period is not None:
                return PhysicsIntent(
                    kind="circular",
                    physics_op="angular_velocity",
                    physics_params={"period": period[0]},
                    physics_units={"period": period[1] or "s"},
                    operation="solve",
                )
        return None

    mass = find_value_with_specific_unit(
        cleaned, r"kg|g|mg|lb|lbs|oz", ("mass", "object", "body", "ball", "car")
    )

    op: _CircularOp
    asked = _asked_circular_op(lower)
    if asked is None:
        return None
    op = asked
    # F = m v^2 / r is the only one of the three that needs a mass; the
    # other two are mass-independent, same as the incline result in P5.
    if op == "centripetal_force" and mass is None:
        return None

    params: dict[str, float] = {"r": radius[0]}
    units: dict[str, str] = {"r": radius[1] or "m"}
    if speed is not None:
        params["v"] = speed[0]
        units["v"] = speed[1] or "m/s"
    elif op == "angular_velocity":
        # ω = v/r and rpm are the families this operation solves. A supplied
        # angular speed is already the answer, so it is not an input.
        return None
    elif omega is not None:
        params["omega"] = float(omega.group(1))
        units["omega"] = "rad/s"
    # a = v^2/r and the period do not use mass. Sending it makes the catalog
    # reject the intent, so a stated mass crashes instead of being ignored.
    if mass is not None and op == "centripetal_force":
        params["m"] = mass[0]
        units["m"] = mass[1] or "kg"
    return PhysicsIntent(
        kind="circular",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
