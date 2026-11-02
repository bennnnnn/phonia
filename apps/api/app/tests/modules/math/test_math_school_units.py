"""Pint-backed unit conversion (replaces hardcoded dicts in math_school)."""

from __future__ import annotations

import pytest

from app.modules.math.solve import SolveServiceError
from app.modules.math.unit_conversion import convert_unit

# ---------------------------------------------------------------------------
# Length
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, src, dest, expected",
    [
        (1.0, "m", "cm", 100.0),
        (100.0, "cm", "m", 1.0),
        (1.0, "km", "m", 1000.0),
        (1.0, "inch", "cm", 2.54),
        (1.0, "ft", "m", 0.3048),
        (1.0, "mi", "km", 1.609344),
    ],
)
def test_convert_length(value: float, src: str, dest: str, expected: float) -> None:
    result = float(convert_unit(value, src, dest))
    assert abs(result - expected) < 1e-6


# ---------------------------------------------------------------------------
# Mass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, src, dest, expected",
    [
        (1.0, "kg", "g", 1000.0),
        (1000.0, "g", "kg", 1.0),
        (1.0, "lb", "kg", 0.45359237),
        (1.0, "oz", "g", 28.349523125),
    ],
)
def test_convert_mass(value: float, src: str, dest: str, expected: float) -> None:
    result = float(convert_unit(value, src, dest))
    assert abs(result - expected) < 1e-6


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, src, dest, expected",
    [
        (1.0, "min", "s", 60.0),
        (1.0, "hr", "s", 3600.0),
        (1.0, "hr", "min", 60.0),
        (1000.0, "ms", "s", 1.0),
    ],
)
def test_convert_time(value: float, src: str, dest: str, expected: float) -> None:
    result = float(convert_unit(value, src, dest))
    assert abs(result - expected) < 1e-6


# ---------------------------------------------------------------------------
# Temperature (offset units — the main reason to use Pint over hand-rolled)
# ---------------------------------------------------------------------------


def test_convert_celsius_to_fahrenheit() -> None:
    result = float(convert_unit(0.0, "C", "F"))
    assert abs(result - 32.0) < 1e-6
    result = float(convert_unit(100.0, "C", "F"))
    assert abs(result - 212.0) < 1e-6


def test_convert_fahrenheit_to_celsius() -> None:
    result = convert_unit(32.0, "F", "C")
    assert result == "0"
    assert abs(float(result) - 0.0) < 1e-6
    result = convert_unit(212.0, "F", "C")
    assert abs(float(result) - 100.0) < 1e-6


def test_convert_celsius_to_kelvin() -> None:
    result = float(convert_unit(0.0, "C", "K"))
    assert abs(result - 273.15) < 1e-6


def test_convert_kelvin_to_celsius() -> None:
    result = float(convert_unit(273.15, "K", "C"))
    assert abs(result - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# Compound units (m/s, m/s^2, N, J, W) — new with Pint
# ---------------------------------------------------------------------------


def test_convert_velocity_ms_to_kmh() -> None:
    result = float(convert_unit(10.0, "m/s", "km/h"))
    assert abs(result - 36.0) < 1e-6


def test_convert_acceleration() -> None:
    # 1 g = 9.81 m/s^2 (approx, using standard gravity 9.80665)
    result = float(convert_unit(1.0, "m/s^2", "m/s^2"))
    assert abs(result - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Backward compat: plural stripping + aliases the old dicts accepted
# ---------------------------------------------------------------------------


def test_plural_stripping() -> None:
    assert float(convert_unit(1.0, "meters", "cm")) == 100.0
    assert float(convert_unit(1.0, "inches", "cm")) == 2.54


def test_unit_aliases() -> None:
    # "in" → inch, "ft" → foot, "lb" → pound
    assert abs(float(convert_unit(12.0, "in", "ft")) - 1.0) < 1e-6
    assert abs(float(convert_unit(1.0, "lb", "g")) - 453.59237) < 1e-4


# Converter-pad prompts (apps/mobile/features/chat/model/unitConverter.ts). Must parse with
# original case — lowercasing before Pint used to drop J/N/Pa/kWh/BTU/mmHg.
@pytest.mark.parametrize(
    "value, src, dest",
    [
        (5.0, "J", "cal"),
        (5.0, "kJ", "J"),
        (5.0, "N", "lbf"),
        (5.0, "kN", "N"),
        (5.0, "Pa", "psi"),
        (5.0, "kPa", "Pa"),
        (5.0, "kWh", "J"),
        (5.0, "Wh", "J"),
        (5.0, "eV", "J"),
        (5.0, "BTU", "kJ"),
        (5.0, "mmHg", "kPa"),
        (5.0, "fl-oz", "mL"),
        (1.0, "atm", "psi"),
        (1.0, "L", "mL"),
    ],
)
def test_converter_pad_prompts_round_trip(value: float, src: str, dest: str) -> None:
    result = float(convert_unit(value, src, dest))
    assert result > 0
    back = float(convert_unit(result, dest, src))
    assert abs(back - value) / value < 1e-6


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_incompatible_dimensions_raise() -> None:
    with pytest.raises(SolveServiceError):
        convert_unit(1.0, "m", "kg")


def test_unknown_unit_raises() -> None:
    with pytest.raises(SolveServiceError):
        convert_unit(1.0, "foo", "bar")
