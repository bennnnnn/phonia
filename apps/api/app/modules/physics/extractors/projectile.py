"""Projectile motion: range, flight time, peak height and launch angle."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.momentum import _COLLISION_SUBJECT_RE
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    find_value_with_unit,
)
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import (
    DECIMAL,
    DEGREE_WORD,
    LENGTH_UNIT_PATTERN,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_PROJECTILE_CUES = (
    "projectile",
    "launched at angle",
    "launched at an angle",
    "fired at angle",
    "fired at an angle",
    "thrown at angle",
    "thrown at an angle",
    "maximum height",
    "max height",
    "trajectory",
)

_PROJECTILE_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\d\s*(?:m/s|km/h|mph)\b.{{0,80}}?\d\s*{DEGREE_WORD}"),
    re.compile(rf"\d\s*{DEGREE_WORD}.{{0,80}}?\d\s*(?:m/s|km/h|mph)\b"),
    # The launch-angle question has no angle to co-occur with — the angle is
    # what it is asking for — so the signature above cannot see it. A speed
    # beside an explicit ask for an angle is the signature instead.
    re.compile(
        r"\b(?:what|which)\s+(?:launch\s+)?angle\b.{0,80}?\d\s*(?:m/s|km/h|mph)\b"
        r"|\d\s*(?:m/s|km/h|mph)\b.{0,80}?\b(?:what|which)\s+(?:launch\s+)?angle\b",
        re.IGNORECASE,
    ),
)

_PROJECTILE_UNKNOWN_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "max_height",
        re.compile(
            r"\bmax(?:imum)?\s+height\b|\bhow high\b|\bhighest point\b|\bpeak height\b"
            r"|\bapex\b|\bheight (?:does|it) (?:reach|rise)",
            re.IGNORECASE,
        ),
    ),
    (
        # A speed word AND a landing word, in either order. Either alone is a
        # different question: the speed alone is the given it was thrown at,
        # and the landing alone is the time of flight below.
        "impact_speed",
        re.compile(
            r"(?:\bhow fast\b|\bspeed\b|\bvelocity\b).{0,60}?"
            r"(?:\bland\w*\b|\bimpact\b|\bhits?\b|\bstrikes?\b|\btouch(?:es)? down\b)"
            r"|(?:\bland\w*\b|\bimpact\b|\bhits?\b|\bstrikes?\b|\btouch(?:es)? down\b).{0,60}?"
            r"(?:\bhow fast\b|\bspeed\b|\bvelocity\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "time_of_flight",
        re.compile(
            r"\btime of flight\b|\bflight time\b|\bhow long\b|\bhow much time\b"
            r"|\btime (?:in|it spends in) the air\b|\btime (?:to|before) (?:it )?lands?\b",
            re.IGNORECASE,
        ),
    ),
    (
        # Before `range` — this phrasing says "range" itself ("what launch angle
        # gives a range of 35 m"), and there the range is the given.
        "launch_angle",
        re.compile(r"\b(?:what|which)\s+(?:launch\s+)?angle\b|\blaunch angle\b", re.IGNORECASE),
    ),
    (
        "range",
        re.compile(
            r"\brange\b|\bhow far\b|\bhorizontal distance\b|\btrajectory\b"
            r"|\bdistance (?:does|it)\b|\bhow much ground\b",
            re.IGNORECASE,
        ),
    ),
)

_RANGE_GIVEN_KEYWORDS = ("range", "travel", "reach", "cover", "land", "distance", "far")

# Read right after the angle: "30° below the horizontal", "at 20 degrees downward".
_BELOW_HORIZONTAL_RE = re.compile(
    r"\s*(?:degrees?|deg|°)?\s*(?:below|beneath|under)\s+(?:the\s+)?horizontal\b"
    r"|\s*(?:degrees?|deg|°)?\s*(?:down(?:wards?)?|downward)\b",
    re.IGNORECASE,
)


def _extract_projectile_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _PROJECTILE_CUES, _PROJECTILE_CUE_RES):
        return None
    from app.modules.physics.extractors.drag import states_velocity_drag

    if states_velocity_drag(cleaned):
        return None
    # A collision is not a projectile, whatever units it carries. The signature
    # cue above is "a speed and an angle in one clause" — which a 2D collision
    # also satisfies, and this extractor runs first. Without this guard,
    # "a 2 kg ball at 3 m/s hits a 1 kg ball at rest ... at 30 degrees" was
    # answered 0.79 m: the range of a ball lobbed at 3 m/s.
    if _COLLISION_SUBJECT_RE.search(cleaned):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    # Initial speed (v0): "at 15 m/s", "speed of 15 m/s", "velocity of 15 m/s"
    # Search for a number followed by a velocity unit (m/s, km/h) so "at 45 degrees"
    # isn't mistaken for the speed.
    v0: float | None = None
    v0_unit = "m/s"
    speed_m = re.search(
        rf"({DECIMAL})\s*({VELOCITY_UNIT_PATTERN})",
        cleaned,
        re.IGNORECASE,
    )
    if speed_m:
        v0 = float(speed_m.group(1))
        v0_unit = speed_m.group(2)
    else:
        vu = find_value_with_unit(cleaned, ("speed of", "velocity of", "speed", "velocity"))
        if vu is not None:
            v0, v0_unit = vu

    # Angle (theta): "angle of 45", "at an angle of 30", "at 45 degrees", "at 30°"
    angle: float | None = None
    # Prefer "angle of N" / "at an angle of N" — unambiguous.
    angle_m = re.search(
        r"(?:angle\s*(?:of|=)?\s*|at\s+an\s+angle\s*(?:of)?\s*)(-?\d+(?:\.\d+)?)\s*"
        r"(?:degrees?|°|deg|radians?|rad)?",
        lower,
    )
    if angle_m is None:
        # Fall back to "at N degrees/°/deg" — only when the unit word is
        # present so "at 15 m/s" (speed) isn't mistaken for an angle.
        # ``°`` is not a word char, so a trailing ``\b`` would miss ``30°?``.
        angle_m = re.search(
            rf"\bat\s+(-?\d+(?:\.\d+)?)\s*{DEGREE_WORD}(?![A-Za-z0-9])",
            lower,
        )
    if angle_m is None:
        # After stripping ``angle = 30``, only ``30 deg`` remains.
        angle_m = re.search(
            rf"({DECIMAL})\s*(?:degrees?|°|deg|radians?|rad)(?![A-Za-z0-9])",
            lower,
        )
    if angle_m:
        angle = float(angle_m.group(1))
        # "30° below the horizontal" is a launch downward: -30°. Read as 30°
        # above, the ball flew 22.4 m from a 20 m building instead of 13.6 m.
        if angle > 0 and _BELOW_HORIZONTAL_RE.match(lower, angle_m.end()):
            angle = -angle

    if v0 is None:
        return None

    # What is being asked decides which givens are required, so it is read
    # before the angle gate below: the launch-angle question has no angle in it
    # by definition.
    op = next((name for name, rx in _PROJECTILE_UNKNOWN_RES if rx.search(cleaned)), None)
    if op is None:
        return None

    g = detect_gravity(cleaned)
    angle_unit = "rad" if re.search(r"\b(?:rad|radians)\b", lower) else "deg"

    if op == "launch_angle":
        # The range is the given here and the angle is the answer, so an angle
        # in the text would make the question self-contradictory.
        if angle is not None:
            return None
        ru = find_value_with_specific_unit(
            cleaned, LENGTH_UNIT_PATTERN, _RANGE_GIVEN_KEYWORDS, require_keyword=True
        )
        if ru is None:
            return None
        return PhysicsIntent(
            kind="projectile",
            physics_op=op,
            physics_params={"v0": v0, "d": ru[0], "g": g},
            physics_units={"v0": v0_unit or "m/s", "d": ru[1] or "m", "g": "m/s^2"},
            operation="solve",
        )

    if angle is None:
        return None
    if angle < 0 and op == "max_height":
        # A downward launch is highest where it starts; the upward formula
        # would add a rise that never happens.
        return None

    h0: float | None = None
    h0_unit = "m"
    hu = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        ("from", "initial height", "height of", "high", "above", "cliff", "h0"),
        require_keyword=True,
    )
    if hu is not None:
        h0, h0_unit = hu

    params: dict[str, float] = {"v0": v0, "angle": angle, "g": g}
    units: dict[str, str] = {"v0": v0_unit or "m/s", "angle": angle_unit, "g": "m/s^2"}
    if h0 is not None:
        params["h0"] = h0
        units["h0"] = h0_unit or "m"
    return PhysicsIntent(
        kind="projectile",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
