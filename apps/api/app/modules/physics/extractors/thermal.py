"""Thermal extractors: heat, expansion, phase change, gas laws, efficiency."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.school_extensions import blocks_thermal
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.thermal_laws import NAMED_THERMAL_LAWS
from app.modules.physics.extractors.thermal_readings import (
    _CELSIUS_PATTERN,
    _KELVIN_PATTERN,
    _SPECIFIC_HEAT_UNIT,
    _TEMPERATURE_SPAN,
    _WATER_SPECIFIC_HEAT,
    _temperature_change,
    _temperature_value,
)
from app.modules.physics.extractors.unit_patterns import DEGREE_WORD, MASS_UNITS, NUMBER
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

# Warming through a change of state: boiling a liquid away, melting a solid,
# freezing or condensing. Heating "to boiling" only reaches the boiling point.
PHASE_CHANGE_RE = re.compile(
    r"\bboil(?:s|ed|ing)?\s+(?:it\s+|them\s+|the\s+\w+\s+)?(?:all\s+|completely\s+)?"
    r"(?:away|off|dry)\b"
    r"|\b(?:completely\s+)?(?:vapori[sz]\w*|evaporat\w*|melt\w*|freez\w*|solidif\w*|"
    r"condens\w*|thaw\w*)"
    r"|\b(?:in)?to\s+steam\b|\bturn\w*\s+(?:it\s+)?(?:in)?to\s+(?:water|steam|ice)\b"
    r"|\bice\b[^.?!]{0,80}?\b(?:in)?to\s+water\b",
    re.IGNORECASE,
)

_THERMAL_CUES = (
    "specific heat",
    "heat capacity",
    "ideal gas",
    "gas constant",
    "thermal expansion",
    "linear expansion",
    "coefficient of linear expansion",
    "latent heat",
    "first law of thermodynamics",
    "internal energy",
    "carnot",
    "entropy",
    "heat conduction",
    "thermal conductivity",
)

_THERMAL_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\b(?:heat|warm|cool)\w*\b.{{0,80}}?\d\s*(?:{_KELVIN_PATTERN}|{_CELSIUS_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\d\s*(?:{_KELVIN_PATTERN}|{_CELSIUS_PATTERN}).{{0,80}}?\b(?:heat|warm|cool)\w*\b",
        re.IGNORECASE,
    ),
    re.compile(r"\befficiency\b.{0,80}?\d\s*(?:J|joules?|kJ|kilojoules?)\b", re.IGNORECASE),
    re.compile(r"\d\s*(?:J|joules?|kJ|kilojoules?)\b.{0,80}?\befficiency\b", re.IGNORECASE),
    # "the pressure of 2 moles of gas at 300 K" names no thermal word at all -
    # a mole count beside a temperature is the signature itself.
    re.compile(
        rf"\d\s*mol(?:e|es)?\b.{{0,80}}?\d\s*(?:{_KELVIN_PATTERN}|{_CELSIUS_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\d\s*(?:{_KELVIN_PATTERN}|{_CELSIUS_PATTERN}).{{0,80}}?\d\s*mol(?:e|es)?\b",
        re.IGNORECASE,
    ),
)


def _extract_thermal_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _THERMAL_CUES, _THERMAL_CUE_RES):
        return None
    # Isothermal work is W = nRT ln(V2/V1). The same n, V and T would otherwise
    # be read as the pressure of an ideal gas.
    if re.search(r"\bisothermal", lower) and re.search(r"\bwork\b", lower):
        return None
    if blocks_thermal(cleaned):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    for names, law in NAMED_THERMAL_LAWS:
        if any(name in lower for name in names):
            return law(cleaned)

    # A stated amount of gas is PV = nRT; anything else left is Q = mc dT.
    moles = find_value_with_specific_unit(cleaned, r"mol|moles?")
    if moles is not None or "ideal gas" in lower:
        return _ideal_gas(cleaned, moles)
    return _heat_energy(cleaned)


def _ideal_gas(cleaned: str, moles: tuple[float, str] | None) -> PhysicsIntent | None:
    """PV = nRT for the pressure, from moles, a volume and an absolute temperature."""
    volume = find_value_with_specific_unit(cleaned, r"m\^?3|cm\^?3|litres?|liters?|l|ml")
    temp = _temperature_value(cleaned, ("temperature", "at"))
    if moles is None or volume is None or temp is None:
        return None
    if temp[1] != "K":
        # PV = nRT needs an absolute temperature. Celsius would be wrong by
        # 273 and look plausible.
        return None
    return PhysicsIntent(
        kind="thermal",
        physics_op="ideal_gas_pressure",
        physics_params={"moles": moles[0], "volume": volume[0], "temp": temp[0]},
        physics_units={
            "moles": "mol",
            "volume": volume[1] or "m^3",
            "temp": "K",
        },
        operation="solve",
    )


_STATED_CAPACITY = re.compile(
    rf"(?:specific\s+heat(?:\s+capacity)?|\bc)\s*(?:=|is|of)\s*{NUMBER}", re.IGNORECASE
)


def _heat_energy(cleaned: str) -> PhysicsIntent | None:
    """Q = mc dT, from a stated change or two readings, and a stated or water's c."""
    lower = cleaned.lower()
    if PHASE_CHANGE_RE.search(cleaned):
        # Boiling it away or melting it takes latent heat as well: mcΔT alone
        # answered 83.7 kJ for the 649 kJ that warming and boiling 250 g take.
        return None
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass", "of"))
    readings = _TEMPERATURE_SPAN.search(cleaned)
    rise = None if readings else _temperature_change(cleaned, ("by", "rise", "raise", "change"))
    if rise is None and readings is None:
        # A temperature *difference* is the same number in kelvin and celsius,
        # so a bare "by 10 degrees" is unambiguous here in a way an absolute
        # "at 300 degrees" is not. Only the interval may be loose.
        bare = re.search(
            rf"(?:by|rises?|raise[sd]?|warms?|cools?)\s+(?:by\s+)?({NUMBER})\s*"
            rf"{DEGREE_WORD}(?![A-Za-z0-9])",
            cleaned,
            re.IGNORECASE,
        )
        if bare is not None:
            rise = (float(bare.group(1)), "K")
    if mass is None or (rise is None and readings is None):
        return None
    capacity = find_value_with_specific_unit(
        cleaned, _SPECIFIC_HEAT_UNIT, ("specific heat", "capacity", "c =", "c is")
    )
    if capacity is not None:
        c_value = capacity[0]
        c_unit = _capacity_unit(capacity[1])
    elif _STATED_CAPACITY.search(cleaned):
        # A capacity is given but its unit was not read: water's 4186 would
        # silently replace the stated number.
        return None
    elif "water" in lower:
        c_value, c_unit = _WATER_SPECIFIC_HEAT, "J/kg/K"
    else:
        # No capacity and no named substance: the answer would be a guess.
        return None
    params = {"m": mass[0], "c_heat": c_value}
    units = {"m": mass[1] or "kg", "c_heat": c_unit}
    if readings is not None:
        scale = readings.group(4)
        first_scale = readings.group(2) or scale
        params.update(temp_initial=float(readings.group(1)), temp_final=float(readings.group(3)))
        units.update(
            temp_initial=_temperature_unit(first_scale), temp_final=_temperature_unit(scale)
        )
    elif rise is not None:
        # A temperature *difference* is the same number in kelvin and celsius,
        # so this one does not need the scale an absolute reading does.
        params["delta_temp"] = rise[0]
        units["delta_temp"] = "K"
    return PhysicsIntent(
        kind="thermal",
        physics_op="heat_energy",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _temperature_unit(scale: str) -> str:
    return "K" if scale.strip().upper() == "K" else "degC"


def _capacity_unit(spelled: str) -> str:
    """The specific heat's unit as written: per kilogram or per gram, in J or kJ."""
    compact = re.sub(r"[\s()·*°^]", "", spelled.lower())
    energy = "kJ" if compact.startswith("kj") else "J"
    per_gram = re.search(r"(?<!k)g", compact.removeprefix("kj").removeprefix("j")) is not None
    return f"{energy}/{'g' if per_gram else 'kg'}/K"
