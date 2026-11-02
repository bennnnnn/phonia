"""Subject-neutral text vocabulary for scalar length and time units."""

from __future__ import annotations

import re

from app.services.number_text import SIGNED_DECIMAL

LENGTH_UNITS = {
    alias: symbol
    for symbol, aliases in {
        "m": ("m", "meter", "meters", "metre", "metres"),
        "cm": ("cm", "centimeter", "centimeters", "centimetre", "centimetres"),
        "mm": ("mm", "millimeter", "millimeters", "millimetre", "millimetres"),
        "km": ("km", "kms", "kilometer", "kilometers", "kilometre", "kilometres"),
        "ft": ("ft", "foot", "feet"),
        "in": ("in", "inch", "inches"),
        "yd": ("yd", "yard", "yards"),
        "mi": ("mi", "mile", "miles"),
    }.items()
    for alias in aliases
}
TIME_UNITS = {
    alias: symbol
    for symbol, aliases in {
        "s": ("s", "sec", "secs", "second", "seconds"),
        "ms": ("ms", "millisecond", "milliseconds"),
        "min": ("min", "mins", "minute", "minutes"),
        "h": ("h", "hr", "hrs", "hour", "hours"),
        "day": ("day", "days"),
    }.items()
    for alias in aliases
}

QUANTITY_NUMBER = re.compile(SIGNED_DECIMAL)


def unit_after_quantity(text: str, number_end: int) -> tuple[str, int] | None:
    index = number_end
    while index < len(text) and text[index].isspace():
        index += 1
    start = index
    while index < len(text) and text[index].isascii() and text[index].isalpha():
        index += 1
    if index == start:
        return None
    if index < len(text) and (text[index] in "/^" or text[index].isdigit()):
        return None
    return text[start:index], index
