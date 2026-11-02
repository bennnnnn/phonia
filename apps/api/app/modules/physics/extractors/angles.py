"""Angles a question states, in degrees or radians."""

from __future__ import annotations

import re

from app.modules.physics.extractors.unit_patterns import DECIMAL, DEGREE_WORD

INCLINE_ANGLE_RE = re.compile(rf"({DECIMAL})\s*{DEGREE_WORD}(?![A-Za-z0-9])", re.IGNORECASE)

_RADIAN_ANGLE_RE = re.compile(
    r"(?:at|angle(?:\s+of)?)\s+(-?\d+(?:\.\d+)?)\s*(?:radians?|rad)\b",
    re.IGNORECASE,
)


def _stated_angle(text: str) -> tuple[float, str] | None:
    match = INCLINE_ANGLE_RE.search(text)
    if match is not None:
        return float(match.group(1)), "deg"
    rad = _RADIAN_ANGLE_RE.search(text)
    if rad is not None:
        return float(rad.group(1)), "rad"
    return None
