"""Vertical kinematics: a body dropped, thrown or falling under gravity."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.physics.ask import asked_phrases
from app.modules.physics.extractors.assignments import T_ASSIGN_RE, strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.kinematics_asks import (
    _ASKS_ACCELERATION_RE,
    _ASKS_TIME_RE,
    _H0_KEYWORDS,
    _IMPACT_RE,
    _UP_BEFORE_RE,
    HORIZONTAL_LAUNCH_RE,
    _asks_max_height,
    _asks_position,
    _asks_speed,
    _asks_time_to_peak,
    _asks_velocity,
    _states_a_non_gravity_acceleration,
    _velocity_is_downward,
)
from app.modules.physics.extractors.projectile import _PROJECTILE_CUE_RES
from app.modules.physics.extractors.stated_values import (
    find_value_after_keyword,
    find_value_with_specific_unit,
)
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, VELOCITY_UNIT_PATTERN
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_GRAVITY_MOTION_CUES = (
    "dropped",
    "free fall",
    "freefall",
    "falls from",
    "fall from",
    "falls off",
    "thrown upward",
    "thrown up",
    "thrown down",
    "thrown downward",
    "launched upward",
    "launched downward",
)

_KINEMATICS_CUES = (
    *_GRAVITY_MOTION_CUES,
    "how long until",
    "how long to hit",
    "how long to reach",
    "how long to fall",
    "time to hit",
    "time to reach",
    # Spoken forms of the same question. Naming the ground is unambiguous;
    # "how long ... to fall" needs the regex below, so a share price about to
    # fall 20% is not read as free fall.
    "to hit the ground",
    "to reach the ground",
    "velocity after",
    "speed after",
    "speed when",
    "impact speed",
    "speed at impact",
    "height after",
    "position after",
    "acceleration of",
)

_KINEMATICS_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bhow long\b.{0,60}?\bto fall\b"),
    # "thrown straight up", "thrown vertically upward": the plain cues only
    # had "thrown up", and the question went to math unanswered.
    re.compile(
        r"\b(?:thrown|tossed|launched|projected|fired|kicked|shot)\s+"
        r"(?:straight|vertically|directly)\s+(?:up|down)(?:wards?)?\b"
    ),
    # "how long till it hits the water", "how long before it lands".
    re.compile(
        r"\bhow long (?:till|before)\b.{0,40}?\b(?:hits?|lands?|strikes?)\s+"
        r"(?:the\s+)?(?:ground|floor|water|bottom|surface|sea)\b"
    ),
)


_UPWARD_WORDS_RE = re.compile(
    r"\b(?:rising|ascending|climbing|going\s+up|moving\s+up|vertically)\b", re.IGNORECASE
)


def _states_upward(text: str) -> bool:
    """The text says the launch goes up: "thrown straight up", "rising at 5 m/s"."""
    return _UP_BEFORE_RE.search(text) is not None or _UPWARD_WORDS_RE.search(text) is not None


# The place it was thrown from, not the ground below it.
_ABOVE_LAUNCH = re.compile(
    r"\babove\s+(?:the\s+|its\s+|his\s+|her\s+|their\s+)?(?:balcony|cliff|roof|building|"
    r"tower|bridge|window|hand|launch(?:\s+point)?|release\s+point|point\s+of\s+release|"
    r"(?:starting|throwing)\s+point|platform|table|ledge|edge|thrower)\b",
    re.IGNORECASE,
)


def _height_measured_from(op: str, h0: float | None, lower: str) -> float | None:
    """The launch height the asked height counts from: "How high above the balcony does
    it go?" asks the rise from where it was thrown; with the balcony's 10 m added it was
    answered as the height above the ground."""
    if op == "vertical_max_height" and _ABOVE_LAUNCH.search(lower) is not None:
        return None
    return h0


def _answerable_without_height(op: str, v0: float, time_value: float | None) -> bool:
    """Whether this ask has one answer when no starting height was stated.

    A throw straight up comes back to the hand: its flight, top and height above
    the hand need no height. A speed at a stated time needs none either. A landing
    anywhere else does: its time, its speed, and a fall downward all turn on a
    height nobody gave.
    """
    if op in ("time_to_ground", "time_to_peak", "vertical_max_height"):
        return v0 > 0
    if op == "position":
        return v0 > 0 and time_value is not None
    if op in ("speed", "velocity"):
        return time_value is not None
    return op == "acceleration"


def _extract_kinematics_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    # Must have a kinematics cue AND at least one number.
    if not has_cue(lower, _KINEMATICS_CUES, _KINEMATICS_CUE_RES):
        return None
    # A drop with F = -kv is not v = gt. The drag extractor owns that law.
    from app.modules.physics.extractors.drag import states_velocity_drag

    if states_velocity_drag(cleaned):
        return None
    # rad/s is not a linear speed. "Find the angular velocity" shares the
    # word velocity with free fall, and answering it as v = v0 + gt is wrong.
    if re.search(r"\bangular\b|\brad(?:ians?)?\s*/\s*s", cleaned, re.IGNORECASE):
        return None
    # Constant acceleration that is not gravity belongs to SUVAT, which runs
    # next. Claiming it here does not merely answer a different question — it
    # answers with the wrong acceleration.
    if _states_a_non_gravity_acceleration(cleaned):
        return None
    # A launch angle means the speed given is not the vertical speed, and this
    # extractor has no angle: it would use the whole 20 m/s as the vertical
    # component and answer 4.08 s where the projectile's answer is 2.04 s.
    # Same defect as the non-gravity acceleration above — a different question
    # answered with the wrong number, not merely a different question.
    # (``_PROJECTILE_CUE_RES`` is defined further down; module globals resolve
    # at call time.)
    if any(rx.search(lower) for rx in _PROJECTILE_CUE_RES):
        return None
    # A sideways launch leaves with no vertical speed. A stated speed is the
    # horizontal one: the projectile catalog's level launch reads it, and with no
    # height there is no fall to time ("thrown horizontally at 15 m/s, how long
    # until it hits the ground" was a throw upward, 3.06 s).
    sideways = HORIZONTAL_LAUNCH_RE.search(cleaned) is not None
    asked = asked_phrases(cleaned)
    if asked in {("acceleration",), ("deceleration",)} and not any(
        cue in lower for cue in _GRAVITY_MOTION_CUES
    ):
        # A given velocity cannot turn a request for an unknown acceleration
        # into a free-fall velocity calculation. SUVAT owns that request.
        return None
    asks_speed = _asks_speed(lower, asked)
    asks_velocity = _asks_velocity(lower, asked)
    asks_position = _asks_position(lower)
    asks_max_height = _asks_max_height(lower)
    asks_time_to_peak = _asks_time_to_peak(lower)
    # Defer to the equation extractor if there's an explicit "=" equation —
    # but strip "g = 1.6" parameter specs first (those are knowns, not algebra).
    # When they asked for v/speed/position at a time, ``t = 1`` is a given,
    # not the problem to solve.
    stripped = strip_param_assignments(cleaned)
    if asks_speed or asks_velocity or asks_position:
        stripped = T_ASSIGN_RE.sub("", stripped)
    if has_equation(stripped):
        return None

    # Initial height (h0): length units only so "5 kg" is not a drop height.
    # Unlabeled ``free fall 20 m`` still binds; projectile keeps require_keyword
    # so a wall ``15 m away`` is not a launch height.
    h0: float | None = None
    h0_unit = "m"
    hu = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        _H0_KEYWORDS,
        require_keyword=False,
    )
    if hu is not None:
        h0, h0_unit = hu

    # Initial velocity (v0): velocity words or a velocity unit — never the
    # substring "at" inside "What" / "with".
    v0: float = 0.0
    v0_unit = "m/s"
    vu = find_value_with_specific_unit(
        cleaned,
        VELOCITY_UNIT_PATTERN,
        ("velocity of", "speed of", "velocity", "speed", "initial velocity"),
    )
    if vu is None:
        vu = find_value_after_keyword(
            cleaned,
            ("velocity of", "speed of", "initial velocity", "velocity", "speed"),
        )
    if sideways and vu is not None:
        return None
    if vu is not None:
        v0, v0_unit = vu
    if vu is not None and _velocity_is_downward(cleaned, v0, v0_unit):
        v0 = -v0
    elif v0 != 0.0 and not _states_upward(cleaned):
        # "A ball is thrown at 25 m/s": up, down or sideways is not said, and
        # each gives a different flight.
        return None

    # If we found no height and no nonzero velocity, this isn't a solvable
    # kinematics problem — let the next extractor try. Speed and velocity at a
    # known time are the exception: v = v0 - g*t needs no height, so
    # "how fast is a dropped ball going after 1 s" is answerable. They are let
    # through here and gated below instead, where a missing time returns None.
    if h0 is None and v0 == 0.0 and not (asks_speed or asks_velocity):
        return None

    # Decide what the user is asking for.
    op: Literal[
        "position",
        "velocity",
        "speed",
        "acceleration",
        "time_to_ground",
        "time_to_peak",
        "vertical_max_height",
    ] = "time_to_ground"
    if asks_time_to_peak and not (asks_speed or asks_velocity or asks_position):
        # Only an upward throw has a top to reach after release.
        if v0 <= 0:
            return None
        op = "time_to_peak"
    elif asks_speed:
        op = "speed"
    elif asks_velocity:
        op = "velocity"
    elif asks_position:
        op = "position"
    elif asks_max_height:
        # A downward launch has its maximum at the starting instant and needs
        # different wording/working.  Refuse verification instead of showing
        # the upward-launch formula for a negative initial velocity.
        if v0 <= 0:
            return None
        op = "vertical_max_height"
    elif _ASKS_ACCELERATION_RE.search(lower) is not None and _ASKS_TIME_RE.search(lower) is None:
        if not any(cue in lower for cue in _GRAVITY_MOTION_CUES):
            return None
        op = "acceleration"

    time_value: float | None = None
    time_unit = "s"
    if op in ("position", "velocity", "speed"):
        time_match = find_value_with_specific_unit(
            cleaned,
            r"milliseconds?|ms|seconds?|secs?|sec|s|minutes?|mins?|min|hours?|hrs?|hr|h",
        )
        at_impact = op in ("speed", "velocity") and _IMPACT_RE.search(cleaned) is not None
        if time_match is None and not at_impact:
            # "velocity after" / "height after" without a duration is
            # ambiguous; do not silently answer with impact time.
            return None
        if time_match is not None:
            time_value, time_unit = time_match

    if h0 is None and not _answerable_without_height(op, v0, time_value):
        # No height was stated, and h₀ = 0 is not one: a throw down a well or
        # a speed at an unstated ground has no landing to solve for.
        return None

    g = detect_gravity(cleaned)
    params: dict[str, float] = {"g": g}
    units: dict[str, str] = {"g": "m/s^2"}
    if (h0 := _height_measured_from(op, h0, lower)) is not None:
        params["h0"] = h0
        units["h0"] = h0_unit or "m"
    params["v0"] = v0
    units["v0"] = v0_unit or "m/s"
    if time_value is not None:
        params["t"] = time_value
        units["t"] = time_unit or "s"

    return PhysicsIntent(
        kind="kinematics",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
