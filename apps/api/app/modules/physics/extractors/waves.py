"""Waves: the wave equation, string speed, pipe and string harmonics, and the Doppler effect."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.doppler import SOUND_SOURCE, doppler_intent
from app.modules.physics.extractors.oscillations import _SHM_TIME_UNITS
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_WAVE_CUES = (
    "wavelength",
    "doppler",
    "sound wave",
    "light wave",
    "water wave",
    "wave on a string",
    "string tension",
    "linear density",
    "standing wave",
    "open pipe",
    "closed pipe",
    "sound intensity",
    "beat frequency",
)

_HERTZ_PATTERN = r"Hz|hertz|kHz|kilohertz|MHz|megahertz"

_WAVE_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\bwaves?\b.{{0,80}}?\d\s*(?:{_HERTZ_PATTERN})\b", re.IGNORECASE),
    re.compile(rf"\d\s*(?:{_HERTZ_PATTERN})\b.{{0,80}}?\bwaves?\b", re.IGNORECASE),
    re.compile(rf"\b(?:{SOUND_SOURCE})\b.{{0,80}}?\d\s*(?:{_HERTZ_PATTERN})\b", re.IGNORECASE),
    re.compile(rf"\d\s*(?:{_HERTZ_PATTERN})\b.{{0,80}}?\b(?:{SOUND_SOURCE})\b", re.IGNORECASE),
    re.compile(rf"\bbeats?\b.{{0,80}}?\d\s*(?:{_HERTZ_PATTERN})\b", re.IGNORECASE),
    re.compile(rf"\d\s*(?:{_HERTZ_PATTERN})\b.{{0,80}}?\bbeats?\b", re.IGNORECASE),
    # A wave stated by its period carries no Hz at all. The time unit has to
    # follow "period", so "a wave of layoffs over a 3 week period" cannot match
    # - it puts its number before the word, and weeks are not in the pattern.
    re.compile(
        r"\bwaves?\b.{0,80}?\bperiod\b\s*(?:of\s*)?\d+(?:\.\d+)?\s*"
        r"(?:seconds?|secs?|milliseconds?|ms|s)\b",
        re.IGNORECASE,
    ),
)


def _extract_waves_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _WAVE_CUES, _WAVE_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    frequencies = ordered_values(cleaned, _HERTZ_PATTERN)

    # --- Waves on strings: v = sqrt(T / mu) ----------------------------
    if "string" in lower and ("tension" in lower or "linear density" in lower):
        tension = find_value_with_specific_unit(cleaned, r"N|newtons?", ("tension",))
        linear_density = find_value_with_specific_unit(
            cleaned,
            r"kg/m|g/m|kilograms?\s+per\s+met(?:er|re)|grams?\s+per\s+met(?:er|re)",
            ("linear density", "mass per unit length"),
        )
        if tension is None or linear_density is None:
            return None
        return PhysicsIntent(
            kind="waves",
            physics_op="string_wave_speed",
            physics_params={"tension": tension[0], "linear_density": linear_density[0]},
            physics_units={
                "tension": tension[1] or "N",
                "linear_density": linear_density[1] or "kg/m",
            },
            operation="solve",
        )

    # --- Open/closed pipes and strings: f_n = n v / (k L) --------------
    if any(cue in lower for cue in ("standing wave", "open pipe", "closed pipe")):
        length = find_value_with_specific_unit(
            cleaned, LENGTH_UNIT_PATTERN, ("length", "long", "pipe", "string")
        )
        speed = find_value_with_specific_unit(cleaned, VELOCITY_UNIT_PATTERN)
        if length is None or speed is None:
            return None
        harmonic_match = re.search(
            rf"\b({NUMBER})(?:st|nd|rd|th)?\s+(?:harmonic|mode)\b", cleaned, re.IGNORECASE
        )
        named_harmonic = re.search(
            r"\b(first|second|third|fourth|fifth|sixth)\s+(?:harmonic|mode)\b",
            cleaned,
            re.IGNORECASE,
        )
        harmonic_names = {
            "first": 1.0,
            "second": 2.0,
            "third": 3.0,
            "fourth": 4.0,
            "fifth": 5.0,
            "sixth": 6.0,
        }
        if harmonic_match is not None:
            harmonic = float(harmonic_match.group(1))
        elif named_harmonic is not None:
            harmonic = harmonic_names[named_harmonic.group(1).lower()]
        elif "fundamental" in lower:
            harmonic = 1.0
        else:
            # An unnamed harmonic is not automatically the fundamental.
            return None
        mode_factor = 4.0 if "closed pipe" in lower else 2.0
        # Only the scene reads it: a pipe draws as a tube, a string with clamped ends.
        pipe = {"pipe": 1.0} if "pipe" in lower else {}
        return PhysicsIntent(
            kind="waves",
            physics_op="resonance_frequency",
            physics_params={
                "v_wave": speed[0],
                "L": length[0],
                "harmonic": harmonic,
                "mode_factor": mode_factor,
                **pipe,
            },
            physics_units={
                "v_wave": speed[1] or "m/s",
                "L": length[1] or "m",
                "harmonic": "",
                "mode_factor": "",
                **dict.fromkeys(pipe, ""),
            },
            operation="solve",
        )

    # --- Sound spreading from a point source: I = P / (4 pi r^2) -------
    if "sound intensity" in lower:
        power = find_value_with_specific_unit(
            cleaned, r"W|watts?|kW|kilowatts?", ("power", "source", "emits")
        )
        radius = find_value_with_specific_unit(
            cleaned, LENGTH_UNIT_PATTERN, ("distance", "radius", "away", "at")
        )
        if power is None or radius is None:
            return None
        return PhysicsIntent(
            kind="waves",
            physics_op="sound_intensity",
            physics_params={"sound_power": power[0], "r": radius[0]},
            physics_units={"sound_power": power[1] or "W", "r": radius[1] or "m"},
            operation="solve",
        )

    # --- Beats: f_b = |f_1 - f_2| --------------------------------------
    if "beat" in lower:
        if len(frequencies) != 2:
            return None
        return PhysicsIntent(
            kind="waves",
            physics_op="beat_frequency",
            physics_params={"freq": frequencies[0][0], "freq2": frequencies[1][0]},
            physics_units={
                "freq": frequencies[0][1] or "Hz",
                "freq2": frequencies[1][1] or "Hz",
            },
            operation="solve",
        )

    freq = find_value_with_specific_unit(cleaned, _HERTZ_PATTERN)
    wavelength = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("wavelength",), require_keyword=True
    )
    speed = find_value_with_specific_unit(cleaned, VELOCITY_UNIT_PATTERN)
    period = find_value_with_specific_unit(
        cleaned, _SHM_TIME_UNITS, ("period",), require_keyword=True
    )

    moving_source = re.search(rf"\b(?:{SOUND_SOURCE})\b", lower) is not None
    if "doppler" in lower or (freq is not None and speed is not None and moving_source):
        return doppler_intent(cleaned, freq)

    # f = 1/T and T = 1/f, whichever of the pair is missing.
    if period is not None and freq is None:
        return PhysicsIntent(
            kind="waves",
            physics_op="wave_frequency_from_period",
            physics_params={"period": period[0]},
            physics_units={"period": period[1] or "s"},
            operation="solve",
        )
    if freq is not None and wavelength is None and speed is None and "period" in lower:
        return PhysicsIntent(
            kind="waves",
            physics_op="wave_period",
            physics_params={"freq": freq[0]},
            physics_units={"freq": freq[1] or "Hz"},
            operation="solve",
        )

    # v = f lambda, solved for whichever of the three is absent.
    given = {
        "freq": freq,
        "wavelength": wavelength,
        "v_wave": speed,
    }
    present = {key: value for key, value in given.items() if value is not None}
    if len(present) != 2:
        return None
    missing = ({"freq", "wavelength", "v_wave"} - set(present)).pop()
    op = {
        "freq": "wave_frequency",
        "wavelength": "wavelength",
        "v_wave": "wave_speed",
    }[missing]
    defaults = {"freq": "Hz", "wavelength": "m", "v_wave": "m/s"}
    return PhysicsIntent(
        kind="waves",
        physics_op=op,
        physics_params={key: value[0] for key, value in present.items()},
        physics_units={key: (value[1] or defaults[key]) for key, value in present.items()},
        operation="solve",
    )
