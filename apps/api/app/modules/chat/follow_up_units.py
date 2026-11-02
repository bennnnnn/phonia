"""Numbers and their units, read one way for the follow-up rules.

A reworded question writes the same quantity another way ("2 s" and "2 seconds", "45 m"
and "45 meters", "9.8 m/s²" and "9.8 m/s^2", "4 Ω" and "4 ohm", "$1,200" and "$1200"), and
a reply restates a problem's quantities in its own words. ``follow_up_repeats`` and
``follow_up_ground`` read each number here: its sign or root, the number (a fraction or a
ratio whole), and its unit or currency, each in one written form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Signs and powers as a phone or a model types them, in their plain form.
SYMBOLS = str.maketrans(
    {
        "\u00b2": "^2",  # squared
        "\u00b3": "^3",  # cubed
        "\u2212": "-",  # the minus sign
        "\u2013": "-",  # an en dash
        "\u00d7": "*",  # times
        "\u00b7": "*",  # a middle dot
        "\u00f7": "/",  # divided by
        "\u2009": " ",  # a thin space
        "\uff1f": "?",  # a full-width question mark
    }
)
# A number and what follows it: "$1,200", "-5 m/s", "\u221a2", "3/2", "3:2", "48 cm",
# "9.8 m/s^2", "300 \u00b0C", "5%", "2w". A fraction or a ratio is written without spaces:
# "153.9 / 100" divides two numbers.
QUANTITY = re.compile(
    r"(?<![\w.^])([$\u20ac\u00a3]?)([-\u221a]?)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:([/:])(\d+(?:\.\d+)?))?"
    r"(?:(\s*)(\u00b0\s?[CF]?|%|[a-zA-Z\u00b5\u03a9][a-zA-Z/^0-9\u00b0]*))?"
)
# Short words written after a number that are no unit: "$80 is $20", "48 and 60".
NOT_UNITS = frozenset(
    "a an and are as at be by for from if in is it of on or per so the to was".split()
)
# Each unit's written forms, under the one it is read as.
_UNIT_FORMS = {
    "s": "s sec secs second seconds",
    "min": "min mins minute minutes",
    "h": "h hr hrs hour hours",
    "day": "day days",
    "m": "m meter meters metre metres",
    "cm": "cm centimeter centimeters centimetre centimetres",
    "mm": "mm millimeter millimeters millimetre millimetres",
    "km": "km kilometer kilometers kilometre kilometres",
    "mi": "mi mile miles",
    "ft": "ft foot feet",
    "in": "inch inches",
    "kg": "kg kilo kilos kilogram kilograms",
    "g": "g gram grams",
    "lb": "lb lbs pound pounds",
    "L": "l L liter liters litre litres",
    "mL": "ml mL milliliter milliliters millilitre millilitres",
    "N": "N newton newtons",
    "J": "J joule joules",
    "kJ": "kJ kilojoule kilojoules",
    "W": "W watt watts",
    "V": "V volt volts",
    "A": "A amp amps ampere amperes",
    "\u03a9": "\u03a9 ohm ohms",
    "mol": "mol mole moles",
    "K": "K kelvin",
    # An angle or a temperature in degrees: "0 \u00b0C" and "0 degrees" ask the same.
    "\u00b0": "\u00b0 \u00b0C degree degrees celsius",
    "\u00b0F": "\u00b0F fahrenheit",
    "%": "% percent",
    "km/h": "kph",
    "mi/h": "mph",
}
_UNIT = {form: unit for unit, forms in _UNIT_FORMS.items() for form in forms.split()}
_UNIT_FOLDED = {form.casefold(): unit for form, unit in _UNIT.items() if len(form) > 2}
_LONGEST_UNKNOWN_UNIT = 3


@dataclass(frozen=True)
class Quantity:
    number: str  # "-5", "\u221a2", "1200", "19.8", "3/2", "3:2"
    unit: str | None  # "m/s^2", "\u00b0", "$"; None when nothing follows it
    small: bool  # a single digit: "2 eggs" is in any recipe

    def __str__(self) -> str:
        return f"{self.number} {self.unit}" if self.unit else self.number


def quantities(text: str) -> list[Quantity]:
    """The numbers in ``text`` in order, each with its unit read one way."""
    found = []
    for match in QUANTITY.finditer(text.translate(SYMBOLS)):
        currency, sign, whole, split, part, space, unit = match.groups()
        number = sign + _plain_number(whole)
        if split:
            number += split + _plain_number(part)
        small = not sign and not split and len(number) == 1
        found.append(
            Quantity(number, read_unit(space or "", unit or "") or currency or None, small)
        )
    return found


def read_unit(space: str, written: str) -> str | None:
    """The unit as one written form, or None: "2w" is a variable and "48 and" a word."""
    written = written.replace(" ", "")  # "300 \u00b0 C" is "300 \u00b0C"
    if (
        not written
        or written in NOT_UNITS
        or (len(written) > 1 and written.casefold() in NOT_UNITS)
    ):
        return None  # "a" is a word, "A" is amperes
    if not space and len(written) == 1 and written.isalpha():
        return None
    parts = [_one_unit(part) for part in written.split("/")]
    if all(part is not None for part in parts):
        return "/".join(part for part in parts if part)
    if space and written.isalpha() and len(written) > _LONGEST_UNKNOWN_UNIT:
        return None  # "4 people": a word, not a unit
    return written


def unit_kind(unit: str) -> str:
    """The unit's first part: "m/s^2" and "m/s" are both "m", "km/h" is "km"."""
    return re.split(r"[/^]", unit, maxsplit=1)[0]


def _one_unit(written: str) -> str | None:
    base, power, exponent = written.partition("^")
    unit = _UNIT.get(base) or _UNIT_FOLDED.get(base.casefold())
    if unit is None:
        return None
    return f"{unit}{power}{exponent}"


def _plain_number(written: str) -> str:
    """The number without its commas and trailing zeros: "1,200" is 1200, "2.0" is 2."""
    number = written.replace(",", "")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number or "0"
