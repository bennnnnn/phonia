"""What a fluid question states, read once for every fluid law."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.physics.bodies import WATER_DENSITY
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    MASS_UNITS,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)

AREA_PATTERN = r"m\^?2|cm\^?2|mm\^?2|square\s+met(?:er|re)s?"

_VOLUME_PATTERN = r"m\^?3|cm\^?3|litres?|liters?|ml"

_DENSITY_PATTERN = r"kg/m\^?3|g/cm\^?3|kg\s+per\s+cubic\s+met(?:er|re)"

_PRESSURE_PATTERN = r"Pa|pascals?|kPa|kilopascals?|MPa|megapascals?"


_WATER_DENSITY = WATER_DENSITY


Reading = tuple[float, str] | None


@dataclass(frozen=True, slots=True)
class FluidReading:
    """Every value a fluid law may use, found once in the question."""

    cleaned: str
    lower: str
    area: Reading
    volume: Reading
    mass: Reading
    force: Reading
    depth: Reading
    density: Reading
    viscosity: Reading
    surface_tension: Reading
    radius: Reading
    characteristic_length: Reading
    speed: list[tuple[float, str]]
    areas: list[tuple[float, str]]

    def fluid_density(self) -> float | None:
        """The stated density, or water's when the question names water."""
        if self.density is not None:
            return self.density[0]
        if "water" in self.lower:
            return _WATER_DENSITY
        return None


def read_fluid(cleaned: str) -> FluidReading:
    lower = cleaned.lower()
    area = find_value_with_specific_unit(cleaned, AREA_PATTERN)
    volume = find_value_with_specific_unit(cleaned, _VOLUME_PATTERN)
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass", "of"))
    force = find_value_with_specific_unit(cleaned, r"N|newtons?", ("force", "weight"))
    depth = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("depth", "deep", "below", "down"), require_keyword=True
    )
    density = find_value_with_specific_unit(cleaned, _DENSITY_PATTERN)
    speed = ordered_values(cleaned, VELOCITY_UNIT_PATTERN)
    areas = ordered_values(cleaned, AREA_PATTERN)
    viscosity = find_value_with_specific_unit(
        cleaned, r"Pa\s*[·*]\s*s|Pa\s*s|pascal\s*seconds?", ("viscosity",)
    )
    surface_tension = find_value_with_specific_unit(
        cleaned, r"N/m|newtons?\s+per\s+met(?:er|re)", ("surface tension",)
    )
    radius = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("radius",), require_keyword=True
    )
    characteristic_length = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        ("characteristic length", "diameter", "length scale"),
        require_keyword=True,
    )
    if len(areas) < 2:
        # "narrowing from 0.04 to 0.01 m^2" carries the unit once, on the
        # second value - the same shape the resistor networks had.
        pair = re.search(
            rf"from\s+({NUMBER})\s*(?:{AREA_PATTERN})?\s*to\s+({NUMBER})\s*"
            rf"({AREA_PATTERN})",
            cleaned,
            re.IGNORECASE,
        )
        if pair is not None:
            unit = pair.group(3)
            areas = [(float(pair.group(1)), unit), (float(pair.group(2)), unit)]
    return FluidReading(
        cleaned=cleaned,
        lower=lower,
        area=area,
        volume=volume,
        mass=mass,
        force=force,
        depth=depth,
        density=density,
        viscosity=viscosity,
        surface_tension=surface_tension,
        radius=radius,
        characteristic_length=characteristic_length,
        speed=speed,
        areas=areas,
    )
