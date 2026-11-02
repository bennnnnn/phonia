"""Closed fluids, gravitation, and thermal templates."""

from __future__ import annotations

import re

from app.modules.physics.extractors.school_common import (
    _PRESSURE,
    _VOLUME,
    _intent,
    _kelvin,
    _one,
)
from app.modules.physics.extractors.stated_values import ordered_values
from app.modules.physics.extractors.thermal_readings import _reservoir_temperatures
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, NUMBER
from app.modules.physics.schemas import PhysicsIntent


def extract_poiseuille(text: str, lower: str) -> PhysicsIntent | None:
    if "poiseuille" not in lower:
        return None
    radius = _one(text, LENGTH_UNIT_PATTERN, ("radius",), require_keyword=True)
    length = _one(text, LENGTH_UNIT_PATTERN, ("length", "long"), require_keyword=True)
    pressure = _one(text, _PRESSURE)
    viscosity = _one(text, r"Pa·s|Pa\*s|Pa s")
    if radius is None or length is None or pressure is None or viscosity is None:
        return None
    return _intent(
        "fluids",
        "poiseuille_flow",
        {
            "r": radius[0],
            "L": length[0],
            "delta_pressure": pressure[0],
            "viscosity": viscosity[0],
        },
        {
            "r": radius[1] or "m",
            "L": length[1] or "m",
            "delta_pressure": pressure[1] or "Pa",
            "viscosity": "Pa*s",
        },
    )


def extract_gravitation(text: str, lower: str) -> PhysicsIntent | None:
    mass = ordered_values(text, r"kg|tonnes?|tons?")
    distance = _one(
        text,
        LENGTH_UNIT_PATTERN,
        ("radius", "distance", "separation", "apart", "from the center"),
    )
    if "gravitational potential energy" in lower:
        if len(mass) != 2 or distance is None:
            return None
        return _intent(
            "gravitation",
            "gravitational_potential_energy",
            {"M": mass[0][0], "m": mass[1][0], "r": distance[0]},
            {"M": "kg", "m": "kg", "r": distance[1] or "m"},
        )
    if "gravitational potential" in lower:
        if len(mass) != 1 or distance is None:
            return None
        return _intent(
            "gravitation",
            "gravitational_potential",
            {"M": mass[0][0], "r": distance[0]},
            {"M": "kg", "r": distance[1] or "m"},
        )
    if "orbital energy" in lower:
        if len(mass) != 2 or distance is None:
            return None
        return _intent(
            "gravitation",
            "orbital_energy",
            {"M": mass[0][0], "m": mass[1][0], "r": distance[0]},
            {"M": "kg", "m": "kg", "r": distance[1] or "m"},
        )
    if "kepler" not in lower:
        return None
    if len(mass) != 1 or distance is None:
        return None
    return _intent(
        "gravitation",
        "kepler_period",
        {"M": mass[0][0], "r": distance[0]},
        {"M": "kg", "r": distance[1] or "m"},
    )


def extract_thermal(text: str, lower: str) -> PhysicsIntent | None:
    if "monatomic" in lower and "internal energy" in lower:
        moles = _one(text, r"mol|moles?")
        temp = _kelvin(text, ("temperature", "at"))
        if moles is None or temp is None:
            return None
        return _intent(
            "thermal",
            "monatomic_energy",
            {"moles": moles[0], "temp": temp[0]},
            {"moles": "mol", "temp": "K"},
        )
    if "isobaric" in lower:
        pressure = _one(text, _PRESSURE)
        volumes = ordered_values(text, _VOLUME)
        if pressure is None or len(volumes) != 2:
            return None
        return _intent(
            "thermal",
            "isobaric_work",
            {"pres": pressure[0], "vol1": volumes[0][0], "vol2": volumes[1][0]},
            {
                "pres": pressure[1] or "Pa",
                "vol1": volumes[0][1] or "m^3",
                "vol2": volumes[1][1] or "m^3",
            },
        )
    if "adiabatic" in lower:
        return _adiabatic(text, lower)
    if "coefficient of performance" in lower or "heat pump" in lower or "refrigerator" in lower:
        return _cop(text, lower)
    if "ideal gas" not in lower:
        return None
    return _ideal_gas(text)


def _adiabatic(text: str, lower: str) -> PhysicsIntent | None:
    del lower
    gamma = re.search(rf"\bgamma(?:\s+is|\s+of|=)?\s*({NUMBER})", text, re.IGNORECASE)
    if gamma is None:
        return None
    # Boyle and Charles already read "2 atm" and "3 L". This law uses the same units.
    pressures = ordered_values(text, _PRESSURE + r"|atm|atmospheres?")
    volumes = ordered_values(text, _VOLUME + r"|mL|L")
    params: dict[str, float] = {"gamma_gas": float(gamma.group(1))}
    units = {"gamma_gas": ""}
    if len(pressures) == 1 and len(volumes) == 2:
        params.update({"pres1": pressures[0][0], "vol1": volumes[0][0], "vol2": volumes[1][0]})
        units.update(
            {
                "pres1": pressures[0][1] or "Pa",
                "vol1": volumes[0][1] or "m^3",
                "vol2": volumes[1][1] or "m^3",
            }
        )
        return _intent("thermal", "adiabatic_pressure", params, units)
    if len(pressures) == 2 and len(volumes) == 1:
        params.update({"pres1": pressures[0][0], "pres2": pressures[1][0], "vol1": volumes[0][0]})
        units.update(
            {
                "pres1": pressures[0][1] or "Pa",
                "pres2": pressures[1][1] or "Pa",
                "vol1": volumes[0][1] or "m^3",
            }
        )
        return _intent("thermal", "adiabatic_volume", params, units)
    return None


def _cop(text: str, lower: str) -> PhysicsIntent | None:
    # "Between 250 K and 300 K" names no reservoir. The colder one is Tc,
    # the same reading Carnot already uses.
    reservoirs = _reservoir_temperatures(text)
    if reservoirs is None:
        return None
    hot, cold = reservoirs
    if "heat pump" in lower:
        operation = "heat_pump_cop"
    elif "refrigerator" in lower:
        operation = "refrigerator_cop"
    else:
        return None
    return _intent(
        "thermal",
        operation,
        {"temp": hot[0], "temp_env": cold[0]},
        {"temp": hot[1], "temp_env": cold[1]},
    )


def _ideal_gas(text: str) -> PhysicsIntent | None:
    # PV = NkT counts molecules. PV = nRT must not claim that question.
    if re.search(r"\b(?:molecules?|particles)\b", text, re.IGNORECASE):
        return None
    # A second pressure, volume, or temperature is a change of state. Keeping
    # the first state would answer n = PV/RT and block the combined-gas law.
    if (
        len(ordered_values(text, _PRESSURE)) > 1
        or len(ordered_values(text, _VOLUME)) > 1
        or len(ordered_values(text, r"K|kelvins?")) > 1
    ):
        return None
    pressure = _one(text, _PRESSURE)
    volume = _one(text, _VOLUME)
    moles = _one(text, r"mol|moles?")
    temp = _kelvin(text, ("temperature", "at"))
    present = {
        key: value
        for key, value in {
            "pres": pressure,
            "volume": volume,
            "moles": moles,
            "temp": temp,
        }.items()
        if value is not None
    }
    # Pressure from n, V, and T stays with the existing ideal-gas extractor.
    if len(present) != 3 or "pres" not in present:
        return None
    missing = ({"volume", "moles", "temp"} - set(present)).pop() if "pres" in present else None
    operation = {
        "volume": "ideal_gas_volume",
        "moles": "ideal_gas_amount",
        "temp": "ideal_gas_temperature",
    }.get(missing or "")
    if operation is None:
        return None
    params = {key: value[0] for key, value in present.items()}
    units = {
        "pres": "Pa",
        "volume": (volume[1] if volume else None) or "m^3",
        "moles": "mol",
        "temp": "K",
    }
    return _intent("thermal", operation, params, {key: units[key] for key in params})
