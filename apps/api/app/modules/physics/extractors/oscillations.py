"""Oscillations: Hooke's law, springs, pendulums and simple harmonic motion."""

from __future__ import annotations

import re
from typing import Literal

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.surface_gravity import EARTH_G, detect_gravity
from app.modules.physics.extractors.unit_patterns import DECIMAL, LENGTH_UNIT_PATTERN
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_SPRING_CUES = (
    "hooke",
    "spring constant",
    "simple harmonic",
    "oscillation",
    "oscillating",
    "oscillates",
)

_SPRING_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bspring\b.{0,80}?(?:(?<!\d)\d+\s*N/m|\bk\s*=)", re.IGNORECASE),
    re.compile(r"(?:(?<!\d)\d+\s*N/m|\bk\s*=).{0,80}?\bspring\b", re.IGNORECASE),
)

_SPRING_K_RE = re.compile(r"\bk\s*=\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)

_DISPLACEMENT_KEYWORDS = (
    "stretched",
    "compressed",
    "extended",
    "displacement",
    "amplitude",
    "extension",
    "by",
)

_PENDULUM_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpendulum\b.{0,80}?\d\s*(?:centimet(?:er|re)s?|met(?:er|re)s?|cm|m)\b", re.I),
    re.compile(r"\d\s*(?:centimet(?:er|re)s?|met(?:er|re)s?|cm|m)\b.{0,80}?\bpendulum\b", re.I),
)

_PENDULUM_PERIOD_RE = re.compile(
    r"\bperiod\b|\bhow long\b|\bswing\w*\b|\boscillat\w*\b|\btime\s+for\s+(?:one|a)\b",
    re.IGNORECASE,
)


def _extract_pendulum_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    # A physical or conical pendulum is a different formula. Leaving it here
    # would answer with the simple-pendulum length.
    if "physical pendulum" in lower or "conical pendulum" in lower or "compound pendulum" in lower:
        return None
    if not has_cue(lower, (), _PENDULUM_CUE_RES):
        return None
    if not _PENDULUM_PERIOD_RE.search(cleaned):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    length = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("pendulum", "length", "long", "string", "cord")
    )
    if length is None:
        return None

    params: dict[str, float] = {"L": length[0]}
    units: dict[str, str] = {"L": length[1] or "m"}
    gravity = detect_gravity(cleaned)
    if gravity != EARTH_G:
        params["g"], units["g"] = gravity, "m/s^2"
    return PhysicsIntent(
        kind="spring",
        physics_op="pendulum_period",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


_SHM_FREQUENCY_RE = re.compile(
    r"\bfrequency\b.{0,80}?\bperiod\b|\bperiod\b.{0,80}?\bfrequency\b",
    re.IGNORECASE,
)

_SHM_MAX_SPEED_RE = re.compile(
    r"\b(?:max(?:imum)?|peak)\s+(?:speed|velocity)\b.{0,80}?\bamplitude\b"
    r"|\bamplitude\b.{0,80}?\b(?:max(?:imum)?|peak)\s+(?:speed|velocity)\b",
    re.IGNORECASE,
)

_SHM_CUE_RES: tuple[re.Pattern[str], ...] = (_SHM_FREQUENCY_RE, _SHM_MAX_SPEED_RE)

_MOTION_ASK_RE = re.compile(
    r"\b(?:max(?:imum)?|peak|greatest|top|highest)\s+(?:speed|velocity|acceleration)\b"
    r"|\bhow\s+fast\b",
    re.IGNORECASE,
)

_SHM_TIME_UNITS = r"seconds?|secs?|sec|s|milliseconds?|ms|minutes?|mins?|min"

_ANGULAR_FREQ_RE = re.compile(
    rf"({DECIMAL})\s*(?:rad(?:ians?)?\s*(?:/|per)\s*s(?:ec(?:ond)?s?)?)",
    re.IGNORECASE,
)


def _extract_shm_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, (), _SHM_CUE_RES):
        return None
    # f = 1/T is the same arithmetic for an oscillator and a wave, but the kind
    # should say which was asked about. Waves runs later, so defer explicitly.
    if "wave" in lower:
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    if _SHM_MAX_SPEED_RE.search(cleaned):
        amplitude = find_value_with_specific_unit(
            cleaned, LENGTH_UNIT_PATTERN, ("amplitude",), require_keyword=True
        )
        omega = _ANGULAR_FREQ_RE.search(cleaned)
        if amplitude is None or omega is None:
            return None
        return PhysicsIntent(
            kind="spring",
            physics_op="shm_max_speed",
            physics_params={"x": amplitude[0], "omega": float(omega.group(1))},
            physics_units={"x": amplitude[1] or "m", "omega": "rad/s"},
            operation="solve",
        )

    period = find_value_with_specific_unit(
        cleaned, _SHM_TIME_UNITS, ("period",), require_keyword=True
    )
    if period is None:
        return None
    return PhysicsIntent(
        kind="spring",
        physics_op="shm_frequency",
        physics_params={"period": period[0]},
        physics_units={"period": period[1] or "s"},
        operation="solve",
    )


def _extract_spring_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _SPRING_CUES, _SPRING_CUE_RES):
        return None
    # Conservation and the work-energy theorem name a speed, not ½kx².
    # The energy extractor owns those sentences.
    if re.search(
        r"\b(?:conservation of energy|mechanical energy|energy is conserved"
        r"|work-energy|work energy theorem|net work)\b",
        lower,
    ):
        return None
    # Strip "k = 200" before the algebra check: it is a known, not an equation
    # to solve. Without this the whole question is read as algebra — which is
    # what happened before this extractor existed.
    if has_equation(strip_param_assignments(_SPRING_K_RE.sub("", cleaned))):
        return None
    # A speed or an acceleration is asked, which none of the laws below give:
    # "oscillates with amplitude 5 cm. max speed?" was answered with the period.
    if _MOTION_ASK_RE.search(cleaned):
        return None

    k_match = find_value_with_specific_unit(cleaned, r"N/m")
    if k_match is not None:
        k: float | None = k_match[0]
    else:
        k_assign = _SPRING_K_RE.search(cleaned)
        k = float(k_assign.group(1)) if k_assign else None
    if k is None:
        return None

    displacement = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, _DISPLACEMENT_KEYWORDS
    )
    # "A 250 g mass hangs on a spring" is a mass in grams.
    mass = find_value_with_specific_unit(
        cleaned, r"kg|mg|g|grams?|lb|lbs|oz", ("mass", "object", "body", "block")
    )

    # f = (1/2π)√(k/m) is the period law asked for the frequency. Returning
    # the period makes the ask guard drop the question.
    asks_frequency = "frequency" in lower and "period" not in lower and "angular" not in lower
    op: Literal["spring_force", "spring_energy", "shm_period", "shm_frequency"]
    if asks_frequency:
        op = "shm_frequency"
        if mass is None:
            return None
    elif "period" in lower or "oscillat" in lower or "simple harmonic" in lower:
        op = "shm_period"
        if mass is None:
            return None
    elif "energy" in lower:
        op = "spring_energy"
        if displacement is None:
            return None
    elif "force" in lower:
        op = "spring_force"
        if displacement is None:
            return None
    else:
        return None

    params: dict[str, float] = {"k": k}
    units: dict[str, str] = {"k": "N/m"}
    if displacement is not None and op != "shm_frequency":
        params["x"] = displacement[0]
        units["x"] = displacement[1] or "m"
    if mass is not None:
        params["m"] = mass[0]
        units["m"] = mass[1] or "kg"
    return PhysicsIntent(
        kind="spring",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
