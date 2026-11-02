"""Shared unit registry for conversions, dimensional checks and physical constants."""

from __future__ import annotations

from pint import UnitRegistry

# The kelvin reading of 0 °C: exact, by the definition of the Celsius scale.
CELSIUS_OFFSET_K = 273.15

_unit_registry: UnitRegistry | None = None


def get_unit_registry() -> UnitRegistry:
    global _unit_registry
    if _unit_registry is None:
        _unit_registry = UnitRegistry()
    return _unit_registry


def constant(name: str, unit: str | None = None) -> float:
    """One CODATA magnitude from the registry, in ``unit`` or else in SI base units."""
    quantity = get_unit_registry().Quantity(1, name)
    converted = quantity.to_base_units() if unit is None else quantity.to(unit)
    return float(converted.magnitude)
