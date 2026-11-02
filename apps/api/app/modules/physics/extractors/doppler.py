"""Doppler questions: who moves, toward whom, and how fast sound travels.

The formula needs each party's speed with a sign (toward the other is
positive), so the reading is by role. A party the question calls stationary
has speed 0 and the one stated speed belongs to the other. "Moves at 20 m/s"
with no direction, two speeds for one role, or a direction the words do not
settle all decline. A stated speed of sound replaces the 343 m/s default.
"""

from __future__ import annotations

import re

from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.unit_patterns import NUMBER, VELOCITY_UNIT_PATTERN
from app.modules.physics.schemas import PhysicsIntent

SOUND_SOURCE = r"siren|ambulance|police|horn|whistle|train|engine|speaker|source"

_SPEED_OF_SOUND = 343.0

_APPROACHING_RE = re.compile(
    r"\bapproach\w*\b|\btowards?\b|\bcoming\s+(?:at|toward)\b|\bnearing\b", re.IGNORECASE
)
_RECEDING_RE = re.compile(
    r"\breced\w*\b|\baway\s+from\b|\bmoving\s+away\b|\bdeparting\b", re.IGNORECASE
)
_OBSERVER_ROLE_RE = re.compile(r"\b(?:observer|listener)\b", re.IGNORECASE)
_ROLE_SPEED_RE = re.compile(
    rf"\b(source|observer|listener)\b.{{0,60}}?({NUMBER})\s*({VELOCITY_UNIT_PATTERN})\b",
    re.IGNORECASE,
)
# "The speed of sound is 340 m/s." The window stops at a sentence end or a digit.
_STATED_SOUND_RE = re.compile(
    r"\b(?:(?:speed|velocity)\s+of\s+sound|sound\s+(?:speed|travels\s+at))\b"
    rf"[^.\d]{{0,30}}?({NUMBER})\s*m/s\b",
    re.IGNORECASE,
)
_STILL = r"stationary|parked|standing\s+still|at\s+rest"
_STILL_OBSERVER_RE = re.compile(
    rf"\b(?:{_STILL})\s+(?:observer|listener|person)\b"
    rf"|\b(?:observer|listener)\s+(?:who\s+)?(?:is\s+)?(?:{_STILL})\b",
    re.IGNORECASE,
)
_STILL_SOURCE_RE = re.compile(
    rf"\b(?:{_STILL})\s+(?:{SOUND_SOURCE})\b|\b(?:{SOUND_SOURCE})\s+(?:is\s+)?(?:{_STILL})\b",
    re.IGNORECASE,
)

_Speed = tuple[float, str]


def doppler_intent(cleaned: str, freq: _Speed | None) -> PhysicsIntent | None:
    """The source and observer speeds this question states, signed, or None."""
    if freq is None:
        return None
    sound, rest = _without_stated_sound(cleaned)
    still_observer = _STILL_OBSERVER_RE.search(rest) is not None
    still_source = _STILL_SOURCE_RE.search(rest) is not None
    if still_observer and still_source:
        return None
    if _OBSERVER_ROLE_RE.search(rest) is not None and not (still_observer or still_source):
        roles = _signed_role_speeds(rest)
        if roles is None:
            return None
        return _intent(freq, sound, source=roles[0], observer=roles[1])
    speed = find_value_with_specific_unit(rest, VELOCITY_UNIT_PATTERN)
    signed = None if speed is None else _signed(speed, rest)
    if signed is None:
        return None
    # The one stated speed is the mover's: the observer's when the source is still.
    if still_source:
        return _intent(freq, sound, source=(0.0, "m/s"), observer=signed)
    return _intent(freq, sound, source=signed, observer=None)


def _without_stated_sound(cleaned: str) -> tuple[_Speed, str]:
    """The speed of sound, and the text with its statement blanked out."""
    match = _STATED_SOUND_RE.search(cleaned)
    if match is None:
        return (_SPEED_OF_SOUND, "m/s"), cleaned
    blank = " " * (match.end() - match.start())
    return (float(match.group(1)), "m/s"), cleaned[: match.start()] + blank + cleaned[match.end() :]


def _signed(speed: _Speed, window: str) -> _Speed | None:
    """Toward is positive and away negative; both or neither said declines."""
    approaching = _APPROACHING_RE.search(window) is not None
    receding = _RECEDING_RE.search(window) is not None
    if approaching == receding:
        return None
    value, unit = speed
    return (value if approaching else -value), unit or "m/s"


def _signed_role_speeds(cleaned: str) -> tuple[_Speed, _Speed] | None:
    """Source and observer speeds. Positive means that party moves toward the other."""
    found: dict[str, _Speed] = {}
    for match in _ROLE_SPEED_RE.finditer(cleaned):
        role = "source" if match.group(1).lower() == "source" else "observer"
        if role in found:
            return None
        window = cleaned[match.start() : match.end() + 32]
        signed = _signed((float(match.group(2)), match.group(3)), window)
        if signed is None:
            return None
        found[role] = signed
    if "source" not in found or "observer" not in found:
        return None
    return found["source"], found["observer"]


def _intent(
    freq: _Speed, sound: _Speed, *, source: _Speed, observer: _Speed | None
) -> PhysicsIntent:
    params = {"freq": freq[0], "v_src": source[0], "v_sound": sound[0]}
    units = {"freq": freq[1] or "Hz", "v_src": source[1], "v_sound": sound[1]}
    if observer is not None:
        params["v_obs"] = observer[0]
        units["v_obs"] = observer[1]
    return PhysicsIntent(
        kind="waves",
        physics_op="doppler_frequency",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
