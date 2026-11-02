"""Normalize chemistry quantities with the shared Pint registry.

Bare ``pa`` is a petayear and bare ``c`` is the speed of light, so every
chemistry unit goes through this alias table before Pint sees it.
"""

from __future__ import annotations

from app.services.units import get_unit_registry

_ALIASES = {
    "atm": "atm",
    "pa": "pascal",
    "kpa": "kilopascal",
    "bar": "bar",
    "mmhg": "mmHg",
    "torr": "torr",
    "l": "liter",
    "ml": "milliliter",
    "liter": "liter",
    "liters": "liter",
    "litre": "liter",
    "litres": "liter",
    "k": "kelvin",
    "kelvin": "kelvin",
    "c": "degC",
    "°c": "degC",
    "degc": "degC",
    "celsius": "degC",
}


def _pint_unit(unit: str) -> str:
    key = unit.strip().replace(" ", "").lower()
    try:
        return _ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported chemistry unit: {unit}") from exc


def convert(value: float, unit: str, target: str) -> float:
    """Convert ``value`` from one chemistry alias (``mmHg``, ``mL``, ``°C``) to another."""
    registry = get_unit_registry()
    # Offset units such as degC cannot be multiplied; Quantity handles 25 °C → K.
    quantity = registry.Quantity(value, _pint_unit(unit))
    return float(quantity.to(_pint_unit(target)).magnitude)


def to_atm(value: float, unit: str) -> float:
    return convert(value, unit, "atm")


def to_liters(value: float, unit: str) -> float:
    return convert(value, unit, "liter")


def to_kelvin(value: float, unit: str) -> float:
    return convert(value, unit, "kelvin")
