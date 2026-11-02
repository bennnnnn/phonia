"""Closed sinusoidal AC templates. Not a general network solver."""

from __future__ import annotations

import re

from app.modules.physics.extractors.school_common import (
    _FARAD,
    _HENRY,
    _HERTZ,
    NUMBER,
    _henry_unit,
    _intent,
    _one,
)
from app.modules.physics.extractors.unit_patterns import AMP_PATTERN, OHM_PATTERN
from app.modules.physics.schemas import PhysicsIntent

_PEAK_ASK_RE = re.compile(
    r"\b(?:find|what(?:'s| is)|calculate|compute|determine)\b"
    r"(?:(?!\brms\b).){0,48}\b(?:peak|amplitude|maximum)\b",
    re.IGNORECASE,
)
_GIVEN_PEAK_RE = re.compile(r"\b(?:peak|amplitude)\s+of\b", re.IGNORECASE)


def _rms_params(value: float, unit: str, text: str) -> tuple[dict[str, float], dict[str, str]]:
    """Divide by sqrt(2) for a stated peak. Multiply when the rms value is given."""
    params = {"V": value}
    units = {"V": unit}
    asks_peak = _PEAK_ASK_RE.search(text) is not None and _GIVEN_PEAK_RE.search(text) is None
    if asks_peak:
        params["to_peak"] = 1.0
        units["to_peak"] = ""
    return params, units


def extract_ac(text: str, lower: str) -> PhysicsIntent | None:
    if re.search(r"\brms\b", lower):
        # Average power with a stated phase is not an rms conversion.
        if "phase" in lower:
            return None
        if "voltage" in lower or re.search(r"\bvolts?\b", lower):
            given = _one(text, r"V|volts?")
            if given is None:
                return None
            params, units = _rms_params(given[0], given[1] or "V", text)
            return _intent("circuit", "rms_voltage", params, units)
        given = _one(text, AMP_PATTERN)
        if given is None:
            return None
        params = {"I": given[0]}
        units = {"I": given[1] or "A"}
        if _PEAK_ASK_RE.search(text) is not None and _GIVEN_PEAK_RE.search(text) is None:
            params["to_peak"] = 1.0
            units["to_peak"] = ""
        return _intent("circuit", "rms_current", params, units)
    frequency = _one(text, _HERTZ)
    inductance = _one(text, _HENRY)
    capacitance = _one(text, _FARAD)
    resistance = _one(text, OHM_PATTERN, ("resistance", "resistor"))
    if any(word in lower for word in ("resonant", "resonance")) and inductance and capacitance:
        if "string" in lower or "pipe" in lower:
            return None
        return _intent(
            "circuit",
            "lc_resonance",
            {"inductance": inductance[0], "capacitance": capacitance[0]},
            {
                "inductance": _henry_unit(inductance[1] or "H"),
                "capacitance": capacitance[1] or "F",
            },
        )
    inductive = re.search(
        rf"inductive reactance(?:\s+of)?\s+({NUMBER})\s*({OHM_PATTERN})",
        text,
        re.IGNORECASE,
    )
    capacitive = re.search(
        rf"capacitive reactance(?:\s+of)?\s+({NUMBER})\s*({OHM_PATTERN})",
        text,
        re.IGNORECASE,
    )
    if "impedance" in lower and resistance is not None:
        if inductive is not None and capacitive is not None:
            return _intent(
                "circuit",
                "series_impedance",
                {
                    "R": resistance[0],
                    "reactance_l": float(inductive.group(1)),
                    "reactance_c": float(capacitive.group(1)),
                },
                {"R": resistance[1] or "ohm", "reactance_l": "ohm", "reactance_c": "ohm"},
            )
        if inductance and capacitance and frequency:
            return _intent(
                "circuit",
                "series_impedance",
                {
                    "R": resistance[0],
                    "inductance": inductance[0],
                    "capacitance": capacitance[0],
                    "freq": frequency[0],
                },
                {
                    "R": resistance[1] or "ohm",
                    "inductance": _henry_unit(inductance[1] or "H"),
                    "capacitance": capacitance[1] or "F",
                    "freq": frequency[1] or "Hz",
                },
            )
    if "inductive reactance" in lower and inductance and frequency:
        return _intent(
            "circuit",
            "inductive_reactance",
            {"inductance": inductance[0], "freq": frequency[0]},
            {
                "inductance": _henry_unit(inductance[1] or "H"),
                "freq": frequency[1] or "Hz",
            },
        )
    if "capacitive reactance" in lower and capacitance and frequency:
        return _intent(
            "circuit",
            "capacitive_reactance",
            {"capacitance": capacitance[0], "freq": frequency[0]},
            {"capacitance": capacitance[1] or "F", "freq": frequency[1] or "Hz"},
        )
    if "average power" in lower and resistance is not None:
        current = _one(text, AMP_PATTERN)
        if current is None:
            return None
        return _intent(
            "circuit",
            "ac_average_power",
            {"I": current[0], "R": resistance[0]},
            {"I": current[1] or "A", "R": resistance[1] or "ohm"},
        )
    return None
