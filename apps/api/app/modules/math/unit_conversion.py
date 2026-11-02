"""Convert a value between two units with Pint, as the school unit questions ask."""

from __future__ import annotations

from typing import Any

from app.modules.math.solve import SolveServiceError
from app.services.units import get_unit_registry

# Aliases the old hardcoded tables accepted that Pint doesn't by default.
# Maps user-facing unit strings → Pint-compatible strings.
_UNIT_ALIASES = {
    "in": "inch",
    "inches": "inch",
    "ft": "foot",
    "feet": "foot",
    "foot": "foot",
    "yd": "yard",
    "mi": "mile",
    "miles": "mile",
    "mile": "mile",
    "lbs": "pound",
    "lb": "pound",
    "oz": "ounce",
    "sec": "second",
    "secs": "second",
    "s": "second",
    "mins": "minute",
    "min": "minute",
    "hr": "hour",
    "hrs": "hour",
    "h": "hour",
    "ms": "millisecond",
    "c": "degC",
    "celsius": "degC",
    "f": "degF",
    "fahrenheit": "degF",
    "k": "kelvin",
    "kelvin": "kelvin",
    "fl-oz": "fluid_ounce",
    "floz": "fluid_ounce",
    "fl oz": "fluid_ounce",
}


def unit_key(unit: str) -> str:
    """One name for the ways a unit is written: "miles", "mile" and "mi" are ``mile``,
    "ms" stays a millisecond, never a plural of "m", and "MB" is not "mb"."""
    key = unit.strip()
    lower = key.lower()
    if lower in _UNIT_ALIASES:
        return _UNIT_ALIASES[lower]
    singular = lower.removesuffix("s")
    if len(lower) > 2 and singular in _UNIT_ALIASES:
        return _UNIT_ALIASES[singular]
    if len(key) > 3 and key.islower():
        return key.removesuffix("es" if key.endswith("ches") else "s")
    return key


def convert_unit(value: float, src: str, dest: str) -> str:
    """Convert a value from one unit to another using Pint dimensional analysis.

    Handles length, mass, time, temperature (C/F/K), and compound units
    (m/s, m/s², N, J, Pa, W, Hz, etc.). Raises SolveServiceError on
    unsupported conversions or dimensionality mismatches.
    """
    ureg = get_unit_registry()

    def _candidates(unit: str) -> list[str]:
        raw = unit.strip()
        key = raw.lower()
        out: list[str] = []

        def add(item: str) -> None:
            if item and item not in out:
                out.append(item)

        if key in _UNIT_ALIASES:
            add(_UNIT_ALIASES[key])
            return out
        if "/" not in key and "^" not in key and len(key) > 1:
            stripped = key.rstrip("s")
            if stripped in _UNIT_ALIASES:
                add(_UNIT_ALIASES[stripped])
                return out
        # Pint is case-sensitive (J joule, N newton). Prefer the original
        # spelling, then lowercase, so the converter pad's ``J``/``N``/``Pa``
        # survive. Do not lowercase first.
        add(raw)
        add(key)
        return out

    def _quantity(value: float, unit: str) -> Any:
        last_exc: Exception | None = None
        for cand in _candidates(unit):
            try:
                return value * ureg(cand)
            except Exception as exc:
                last_exc = exc
                try:
                    return ureg.Quantity(value, cand)
                except Exception as inner:
                    last_exc = inner
                    continue
        raise SolveServiceError(f"unsupported conversion {src} to {dest}") from last_exc

    try:
        quantity = _quantity(value, src)
        last_exc: Exception | None = None
        for dest_cand in _candidates(dest):
            try:
                result = quantity.to(dest_cand)
                mag = float(result.magnitude)
                # Offset units (32 F → C) land at 0 ± 1e-14. Do not snap
                # microscopic energy conversions (eV → J) to zero.
                if abs(mag) < 1e-9 and quantity.check("[temperature]"):
                    mag = 0.0
                return f"{mag:.10g}"
            except Exception as exc:
                last_exc = exc
                continue
        raise SolveServiceError(f"unsupported conversion {src} to {dest}") from last_exc
    except SolveServiceError:
        raise
    except Exception as exc:
        raise SolveServiceError(f"unsupported conversion {src} to {dest}") from exc
