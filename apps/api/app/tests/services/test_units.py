"""The shared unit registry: the Celsius offset is where Pint puts 0 °C."""

from __future__ import annotations

from app.services.units import CELSIUS_OFFSET_K, get_unit_registry


def test_the_celsius_offset_is_the_kelvin_reading_of_zero_celsius() -> None:
    zero = get_unit_registry().Quantity(0.0, "degC").to("kelvin").magnitude
    assert CELSIUS_OFFSET_K == float(zero) == 273.15
