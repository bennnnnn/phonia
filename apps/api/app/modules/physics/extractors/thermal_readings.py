"""Temperatures, heat capacities and labelled energies, as thermal questions state them."""

from __future__ import annotations

import re

from app.modules.physics.bodies import WATER_SPECIFIC_HEAT
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    positioned_values,
)
from app.modules.physics.extractors.unit_patterns import DECIMAL, NUMBER
from app.modules.physics.schemas import PhysicsIntent
from app.services.units import CELSIUS_OFFSET_K

_KELVIN_PATTERN = r"K|kelvins?"

_CELSIUS_PATTERN = r"°C|degrees?\s+c(?:elsius)?|celsius|C(?![A-Za-z])"

_WATER_SPECIFIC_HEAT = WATER_SPECIFIC_HEAT

# Every way a specific heat capacity is written: J/kg/K, J/(kg·K), J/kg°C,
# J kg^-1 K^-1, and the same in kJ.
# Per kilogram or per gram: "4.18 J/g°C" is 4180 J/(kg·K), never water's default.
# "J/kg C" drops the degree sign; unread, water's 4186 replaced a stated 4200.
_SPECIFIC_HEAT_UNIT = (
    r"k?J\s*/\s*k?g\s*/\s*(?:K|°?\s*C)|k?J\s*/\s*\(\s*k?g\s*[·*]?\s*(?:K|°?\s*C)\s*\)"
    r"|k?J\s*/\s*k?g\s*[·*]?\s*(?:K|°?\s*C)(?![A-Za-z])|k?J\s*k?g\^?-1\s*(?:K|°?\s*C)\^?-1"
)

# "from 20 °C to 80 °C": two readings, scale written on both or on the second.
_TEMPERATURE_SPAN = re.compile(
    rf"\bfrom\s+({NUMBER})\s*(°\s*C|K)?\s*(?:up\s+|down\s+)?(?:to|until)\s+"
    rf"({NUMBER})\s*(°\s*C|K)(?![A-Za-z])",
)


# A change of temperature reads the same in K and °C; it is named as a change.
_TEMPERATURE_READING = re.compile(
    rf"({DECIMAL})\s*(?:{_KELVIN_PATTERN}|{_CELSIUS_PATTERN})(?![A-Za-z])",
    re.IGNORECASE,
)
_CHANGE_REACH = 30


def _temperature_change(cleaned: str, keywords: tuple[str, ...]) -> tuple[float, str] | None:
    """A temperature change the words name ("heated by 10 °C"), in kelvin.

    A lone "at 20 °C" is a temperature, not a change: reading it as one
    verified "heat 2 kg of water at 20 °C" as 167 kJ.
    """
    lower = cleaned.lower()
    for match in _TEMPERATURE_READING.finditer(cleaned):
        before = lower[max(0, match.start() - _CHANGE_REACH) : match.start()]
        if any(keyword in before for keyword in keywords):
            return float(match.group(1)), "K"
    return None


def _temperature_value(cleaned: str, keywords: tuple[str, ...]) -> tuple[float, str] | None:
    """A temperature with an explicit scale, or nothing.

    27 C and 27 K differ by a factor of eleven, so a bare number is refused
    rather than assumed - and "degrees" alone cannot help, because it means an
    *angle* everywhere else in this file.
    """
    kelvin = find_value_with_specific_unit(cleaned, _KELVIN_PATTERN, keywords)
    if kelvin is not None:
        return kelvin[0], "K"
    match = re.search(
        rf"({DECIMAL})\s*(?:{_CELSIUS_PATTERN})",
        cleaned,
        re.IGNORECASE,
    )
    if match is not None:
        return float(match.group(1)), "degC"
    return None


def _reservoir_temperatures(
    cleaned: str,
) -> tuple[tuple[float, str], tuple[float, str]] | None:
    """(hot, cold) reservoir readings, each with its scale.

    Labels decide when they are written. "Between 500 K and 300 K" names no
    reservoir, and the hot one is the hotter: reading each label's nearest
    value there gave 500 K twice.
    """
    readings = sorted(
        [(start, value, "K") for start, value, _ in positioned_values(cleaned, _KELVIN_PATTERN)]
        + [
            (start, value, "degC")
            for start, value, _ in positioned_values(cleaned, r"°\s*C|degrees?\s+celsius")
        ]
    )
    lower = cleaned.lower()
    if any(word in lower for word in ("hot", "cold", "source", "sink")):
        hot = _temperature_value(cleaned, ("hot reservoir", "hot", "source"))
        cold = _temperature_value(cleaned, ("cold reservoir", "cold", "sink"))
        if hot is None or cold is None or hot == cold or len(readings) != 2:
            return None
        return hot, cold
    if len(readings) != 2:
        return None
    first, second = ((value, unit) for _, value, unit in readings)
    in_kelvin = [
        value + (CELSIUS_OFFSET_K if unit == "degC" else 0.0) for value, unit in (first, second)
    ]
    return (first, second) if in_kelvin[0] > in_kelvin[1] else (second, first)


_ENERGY_UNIT = r"kilojoules?|joules?|kJ|J"
_WORK_WORDS = ("work",)
_SUPPLIED_WORDS = ("supplied", "absorbed", "absorbs", "absorb", "input", "from")
_REJECTED_WORDS = ("rejected", "rejects", "reject", "exhaust", "waste", "expelled")


def _energy_joules(value: float, unit: str) -> float:
    if unit.lower().startswith("k"):
        return value * 1000.0
    return value


def _nearest_labeled_energy(
    text: str, keywords: tuple[str, ...]
) -> tuple[int, int, float, str] | None:
    """The energy literal closest to one of ``keywords``, with its span."""
    energies = list(
        re.finditer(
            rf"({NUMBER})\s*({_ENERGY_UNIT})(?![A-Za-z0-9/^])",
            text,
            re.IGNORECASE,
        )
    )
    if not energies:
        return None
    spans = [
        (found.start(), found.end())
        for keyword in keywords
        for found in re.finditer(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE)
    ]
    if not spans:
        return None

    def distance(candidate: re.Match[str]) -> int:
        best = 10**9
        for start, end in spans:
            if candidate.end() <= start:
                best = min(best, start - candidate.end())
            elif end <= candidate.start():
                best = min(best, candidate.start() - end)
            else:
                return 0
        return best

    chosen = min(energies, key=distance)
    return chosen.start(), chosen.end(), float(chosen.group(1)), chosen.group(2)


def _efficiency_intent(
    work: tuple[int, int, float, str] | None,
    supplied: tuple[int, int, float, str] | None,
    rejected: tuple[int, int, float, str] | None,
) -> PhysicsIntent | None:
    """Work over heat in, or heat in minus heat out. Unlabeled pairs are refused."""
    same_span = (
        work is not None
        and supplied is not None
        and (work[0], work[1]) == (supplied[0], supplied[1])
    )
    if work is not None and supplied is not None and not same_span:
        work_j = _energy_joules(work[2], work[3])
        heat_j = _energy_joules(supplied[2], supplied[3])
        if work_j <= 0 or heat_j <= 0:
            return None
        params = {"W_out": work_j, "Q_in": heat_j}
    elif (
        work is None
        and supplied is not None
        and rejected is not None
        and (supplied[0], supplied[1]) != (rejected[0], rejected[1])
    ):
        heat_j = _energy_joules(supplied[2], supplied[3])
        rejected_j = _energy_joules(rejected[2], rejected[3])
        work_j = heat_j - rejected_j
        if heat_j <= 0 or work_j <= 0:
            return None
        params = {"W_out": work_j, "Q_in": heat_j}
    else:
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="thermal_efficiency",
        physics_params=params,
        physics_units={"W_out": "J", "Q_in": "J"},
        operation="solve",
    )
