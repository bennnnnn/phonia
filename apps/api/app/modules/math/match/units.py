"""Small unit vocabulary for text extraction; solvers retain dimensional checks."""

from __future__ import annotations

import re

from app.services.number_text import DECIMAL_LITERAL
from app.services.unit_text import LENGTH_UNITS, unit_after_quantity


def normalize_leading_decimals(cleaned: str) -> str:
    """Make .5 and -.5 explicit before existing dimension-number scanners."""
    return re.sub(r"(?<![\w.])([+-]?)\.(?=\d)", r"\g<1>0.", cleaned)


_DIMENSION_GLUE = {
    "by",
    "x",
    "and",
    "with",
    "height",
    "width",
    "length",
    "depth",
    "side",
    "edge",
    "radius",
    "diameter",
    "base",
    "top",
    "bottom",
    "angle",
    "degree",
    "degrees",
    "diagonal",
    "area",
    "perimeter",
    "circumference",
    "please",
    "units",
    "unit",
}


# "in m3": an answer asked in another unit needs a conversion this reader does not make.
_ASKED_IN_UNIT = re.compile(r"\bin\s+([a-z]+)(?:\^?[23])?[\s?.!]*$")


def solid_length_unit(cleaned: str) -> str | None:
    """One consistent printed length unit, or generic units when none is given.

    Mixed units need per-dimension conversion; do not relabel those raw numbers
    as if they used the same scale.
    """
    found: set[str] = set()
    for number in DECIMAL_LITERAL.finditer(cleaned):
        after = cleaned[number.end() :].lstrip()
        word = re.match(r"[A-Za-z]+", after)
        if word is None:
            continue
        name = word.group(0).lower()
        if name in _DIMENSION_GLUE:
            continue
        suffix = after[word.end() :]
        if (
            name not in LENGTH_UNITS
            or suffix.lstrip().startswith(("/", "^", "²", "³"))
            or (suffix and suffix[0].isdigit())
        ):
            return None
        if name == "in":
            # "in the plane" / "in meters" is prose, not an inch measure.
            # Terminal "4 in" and repeated "3 in by 4 in" stay supported.
            following = re.match(r"[A-Za-z]+", suffix.lstrip())
            if following is not None and following.group(0).lower() not in (
                _DIMENSION_GLUE - {"unit", "units"}
            ):
                return None
        found.add(LENGTH_UNITS[name])
    unit = next(iter(found), "units")
    asked = _ASKED_IN_UNIT.search(cleaned.lower())
    if len(found) > 1 or (asked and LENGTH_UNITS.get(asked.group(1), unit) != unit):
        return None
    return unit


def strip_geometry_length_units(cleaned: str) -> str:
    """Let existing dimension scanners read both ``3 by 4 cm`` and ``3 cm by 4 cm``.

    The caller separately validates the single common unit. Strip only recognized
    scalar length tokens, never arbitrary words or compound units.
    """
    chunks: list[str] = []
    start = 0
    for number in DECIMAL_LITERAL.finditer(cleaned):
        unit = unit_after_quantity(cleaned, number.end())
        if unit is None or unit[0].lower() not in {*LENGTH_UNITS, "unit", "units"}:
            continue
        chunks.append(cleaned[start : number.end()])
        start = unit[1]
    chunks.append(cleaned[start:])
    return "".join(chunks)


# "72 fahrenheit in celsius", "what is 72°F in °C", "how much is 5 km in miles": the
# whole message is one quantity and the unit to show it in. Only "convert … to" was
# read, and "whats 72 fahrenheit in celsius" went to the model unchecked.
_UNIT_WORD = r"[A-Za-zµμ°][A-Za-z0-9µμ°*/^._-]{0,63}"
_ASKED_CONVERSION = re.compile(
    r"(?:(?:what(?:'s|s|\s+is)|how\s+much\s+is|convert|change)\s+)?"
    rf"(?P<n>-?{DECIMAL_LITERAL.pattern})\s*(?P<src>{_UNIT_WORD})\s+(?:to|in|into|as)\s+"
    rf"(?P<dest>{_UNIT_WORD})\s*[?.!]*",
    re.IGNORECASE,
)
_DEGREE_MARK = re.compile(r"\^\{?\\circ\}?")


def asked_conversion(cleaned: str) -> tuple[float, str, str] | None:
    """(quantity, unit, unit to show it in) when that is the whole message and the
    converter knows both units: "72 degrees in here" and "3 apples in boxes" are not."""
    from app.modules.math.solve import SolveServiceError
    from app.modules.math.unit_conversion import convert_unit

    match = _ASKED_CONVERSION.fullmatch(" ".join(cleaned.split()))
    if match is None:
        return None
    src = _DEGREE_MARK.sub("°", match.group("src"))
    # A unit never ends in the sentence's full stop: "to minutes." is "minutes".
    dest = match.group("dest").rstrip(".")
    try:
        convert_unit(1.0, src, dest)
    except SolveServiceError:
        return None
    return float(match.group("n")), src, dest
