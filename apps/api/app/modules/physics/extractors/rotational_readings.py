"""The units and values a rotational-dynamics question states."""

from __future__ import annotations

import re

from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    labeled_value,
)
from app.modules.physics.extractors.unit_patterns import NUMBER
from app.modules.physics.schemas import PhysicsIntent

_INERTIA_PATTERN = r"kg\s*m\^?2|kg\s*\*\s*m\^?2|kilogram\s+met(?:er|re)\s+squared"
_OMEGA_UNIT = r"rad(?:ians?)?\s*/\s*s(?:ec(?:ond)?s?)?(?!\s*(?:\^?\s*2|squared))"
_ALPHA_UNIT = r"rad(?:ians?)?\s*/\s*s(?:ec(?:ond)?s?)?\s*(?:\^?\s*2|squared)"
_TIME_UNIT = r"seconds?|secs?|sec|s"
_TORQUE_UNIT = r"(?:N|newtons?)\s*(?:[·*]\s*)?(?:m|met(?:er|re)s?)"


def _intent(operation: str, params: dict[str, float], units: dict[str, str]) -> PhysicsIntent:
    return PhysicsIntent(
        kind="rotation",
        physics_op=operation,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _omega_pair(text: str) -> tuple[tuple[float, str], tuple[float, str]] | None:
    match = re.search(
        rf"\bfrom\s+({NUMBER})\s*({_OMEGA_UNIT})\s+to\s+({NUMBER})\s*({_OMEGA_UNIT})\b",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return (float(match.group(1)), match.group(2)), (float(match.group(3)), match.group(4))


def _time(text: str) -> tuple[float, str] | None:
    match = re.search(rf"\b(?:after|in)\s+({NUMBER})\s*({_TIME_UNIT})\b", text, re.IGNORECASE)
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def _alpha(text: str) -> tuple[float, str] | None:
    found = labeled_value(text, r"angular acceleration", _ALPHA_UNIT)
    if found is not None:
        return found
    match = re.search(rf"({NUMBER})\s*({_ALPHA_UNIT})\b", text, re.IGNORECASE)
    if match is None:
        return None
    return float(match.group(1)), "rad/s^2"


def _from_rest(text: str) -> bool:
    return (
        re.search(r"\b(?:from rest|starts at rest|starts from rest)\b", text, re.IGNORECASE)
        is not None
    )


def _torque_value(text: str) -> float | None:
    match = re.search(rf"({NUMBER})\s*{_TORQUE_UNIT}(?![A-Za-z0-9/^])", text, re.IGNORECASE)
    if match is None:
        return None
    return float(match.group(1))


def _inertia_value(text: str) -> float | None:
    found = find_value_with_specific_unit(text, _INERTIA_PATTERN)
    if found is None:
        return None
    return found[0]


_MASS_NOT_INERTIA_RE = re.compile(
    rf"({NUMBER})\s*(kg|g|mg)\b(?!\s*[*·]?\s*m(?:\s*\^?\s*2|\s+squared)\b)",
    re.IGNORECASE,
)


def _mass_not_inertia(text: str) -> tuple[float, str] | None:
    """A mass in kg, g, or mg that is not the number in front of kg·m².

    "center of mass" contains the word mass, and "2 kg m^2" is an inertia, so
    a keyword search for mass would bind the wrong quantity.
    """
    match = _MASS_NOT_INERTIA_RE.search(text)
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def _angular_values(text: str) -> list[float]:
    return [
        float(match.group(1))
        for match in re.finditer(
            rf"({NUMBER})\s*(?:kg\s*m\^?2\s*/\s*s|kg\*m\^?2/s)",
            text,
            re.IGNORECASE,
        )
    ]
