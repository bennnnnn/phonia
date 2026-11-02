"""Regex fragments for a number and its unit in a physics question."""

from __future__ import annotations

from app.services.number_text import TEXT_DECIMAL, TEXT_NUMBER

# The extractors' short names for the shared running-text number, and the same
# number without an exponent, as an angle or a reading is written.
NUMBER = TEXT_NUMBER


DECIMAL = TEXT_DECIMAL


# The unit after an angle in degrees.
DEGREE_WORD = r"(?:degrees?|deg|\u00b0)"


LENGTH_UNIT_PATTERN = (
    r"kilometers?|km|centimeters?|cm|millimeters?|mm|"
    r"nanometers?|nm|micrometers?|micrometres?|um|µm|"
    r"miles?|mi|meters?|metres?|m|feet|ft|yards?|yd|inches?|in"
)


VELOCITY_UNIT_PATTERN = r"m/s|km/h|mph|cm/s|mm/s|miles\s+per\s+hour"


AMP_PATTERN = r"A|amps?|amperes?"


OHM_PATTERN = r"ohms?|\u03a9"


TESLA_PATTERN = r"T|tesla|teslas|mT|millitesla"


MASS_UNITS = r"kg|mg|g|lb|lbs|oz"
