"""The g a question means: one it states, the body it names, or Earth's."""

from __future__ import annotations

import re

from app.modules.physics.bodies import SCHOOL_GRAVITY
from app.services.text_match import word_index

EARTH_G = SCHOOL_GRAVITY["earth"]


def stated_gravity(text: str) -> float | None:
    """A gravity value the user wrote: "g = 1.6", "gravity = 1.62", "g = 1.6 m/s^2"."""
    lower = text.lower()
    m = re.search(r"\bg\s*=\s*(-?\d+(?:\.\d+)?)", lower)
    if m:
        return float(m.group(1))
    m = re.search(r"\bgravity\s*(?:of|is|=)?\s*(-?\d+(?:\.\d+)?)", lower)
    if m:
        return float(m.group(1))
    return None


def detect_gravity(text: str) -> float:
    """If the user named a gravity value, use it; else the named body's, else 9.81 m/s^2."""
    stated = stated_gravity(text)
    if stated is not None:
        return stated
    lower = text.lower()
    for body in ("moon", "mars"):
        if word_index(lower, body) != -1:
            return SCHOOL_GRAVITY[body]
    return EARTH_G
