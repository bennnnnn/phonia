"""A conversion asked in a textbook's words: one quantity and the one unit to give it in.

"What will be the temperature reading in Fahrenheit scale when the reading is 310 K?",
"The temperature of an object is 40 °C. What is this temperature in Fahrenheit scale?",
"How many centimeters are there in 9.3 m?": only "convert 310 K to fahrenheit" was read,
so these went to the model unchecked, and the 310 K one searched the web and cited a
homework site (2026-10-29, a grade 7 physics book).

The ask is one of a few whole shapes, never any "in <unit>" in a message: read that way,
"the circumference in inches of a circle with radius 3 cm" was answered 1.181 inches and
"how long should the next nap be in minutes" got a card (review, 2026-10-29).

- ``how many <unit> is | are (there) in | make | equals <quantity | that | it>``
- ``what (will) be the reading in <unit> scale when the reading is <quantity>``
- ``what is this | that | it | the <measure> in <unit>``, after a sentence that holds
  the quantity ("The temperature of an object is 40 °C.")
- ``express | write <quantity> in <unit>``

A message that changes the quantity ("drops by 10 °C", "a difference of 30 °C", "minus
40", "half of 10 km"), a rate ("3 miles a day", "per minute") or a reminder is the
model's, whatever its shape.
"""

from __future__ import annotations

import re

from app.modules.math.schemas import MathIntent

# "25 degrees Celsius": one unit, written in words.
_TEMPERATURE_WORDS = re.compile(
    r"\bdeg(?:rees?)?\s+(celsius|centigrade|fahrenheit|kelvin)\b", re.IGNORECASE
)
_UNIT = r"(?:°\s?[CFK]\b|[A-Za-zµμ°][A-Za-z0-9µμ°/^²³]*)"
_QUANTITY = rf"(?P<n>-?\d+(?:\.\d+)?)\s*(?P<src>{_UNIT})"
_SCALE = rf"(?:the\s+)?(?P<to>{_UNIT})(?:\s+scale)?"
_MEASURE = r"temperature|reading|length|distance|mass|weight|height|time|speed|volume|value"
_ASKS = (
    re.compile(
        rf"how\s+many\s+(?P<to>{_UNIT})\s+(?:are\s+there\s+in|is\s+there\s+in|are\s+in|"
        rf"are\s+there|is|are|in|make|makes|equals?|equal\s+to)\s+(?:{_QUANTITY}|that|this|it)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"what\s+(?:is|will\s+be|would\s+be)\s+the\s+(?:temperature\s+)?reading\s+(?:in|on)\s+"
        rf"{_SCALE}\s+(?:if|when)\s+the\s+(?:temperature\s+)?reading(?:\s+(?:in|on)\s+"
        rf"(?:the\s+)?{_UNIT}(?:\s+scale)?)?\s+is\s+{_QUANTITY}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"what(?:'s|\s+is|\s+was|\s+will\s+be)\s+(?:(?:this|that|it)(?:\s+(?:{_MEASURE}))?|"
        rf"(?:the|its)\s+(?:{_MEASURE}))\s+(?:in|on)\s+{_SCALE}",
        re.IGNORECASE,
    ),
    re.compile(rf"(?:express|write)\s+{_QUANTITY}\s+(?:in|as)\s+{_SCALE}", re.IGNORECASE),
)
# A change, a rate, a share or a reminder: the quantity is not simply the one written.
_NOT_A_READING = re.compile(
    r"\b(?:by|rise|rises|rose|drop|drops|dropped|fall|falls|fell|increases?|increased|"
    r"decreases?|decreased|change|changes|changed|difference|differ|below|above|minus|"
    r"negative|plus|per|each|every|half|twice|double|triple|times|average|normal|"
    r"remind|reminder|timer|alarm|schedule|should)\b"
    r"|\b(?:a|an|one)\s+(?:second|minute|hour|day|night|week|month|year)\b|\u2212",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Food calories are kilocalories, a ton is a short ton or a tonne: no one reading.
_UNSURE_UNITS = frozenset({"cal", "calorie", "calories", "ton", "tons"})
_CLAUSES = re.compile(r"(?<=[.?!])\s+|,\s+(?=(?:how|what|express|write)\b)", re.IGNORECASE)
_STATED = re.compile(rf"(?<![\w.]){_QUANTITY}\b")


def _converts(value: float, src: str, dest: str) -> float | None:
    from app.modules.math.solve import SolveServiceError
    from app.modules.math.unit_conversion import convert_unit

    try:
        return float(convert_unit(value, src, dest))
    except (SolveServiceError, ValueError):
        return None


def _same_unit(src: str, dest: str) -> bool:
    """ "°C" and "Celsius" are one unit: 0 and 1 of it are 0 and 1 of the other."""
    return _converts(0.0, src, dest) == 0.0 and _converts(1.0, src, dest) == 1.0


def _ask(clause: str) -> re.Match[str] | None:
    for pattern in _ASKS:
        match = pattern.fullmatch(clause)
        if match is not None:
            return match
    return None


def extract_worded_conversion(cleaned: str) -> MathIntent | None:
    """The one quantity in ``cleaned`` and the one other unit its ask names."""
    text = " ".join(_TEMPERATURE_WORDS.sub(r"\1", cleaned).split())
    numbers = _NUMBER.findall(text)
    if len(numbers) != 1 or "," in numbers[0] or _NOT_A_READING.search(text):
        return None
    clauses = [clause.strip(" ?.!") for clause in _CLAUSES.split(text) if clause.strip(" ?.!")]
    if not 1 <= len(clauses) <= 2:
        return None
    ask = _ask(clauses[-1])
    if ask is None:
        return None
    stated: re.Match[str] | None
    if ask.groupdict().get("n"):
        stated = ask
    elif len(clauses) == 2:
        stated = _STATED.search(clauses[0])
    else:
        return None
    if stated is None:
        return None
    src, dest = stated.group("src"), ask.group("to")
    if {src.lower(), dest.lower()} & _UNSURE_UNITS:
        return None
    if _converts(1.0, src, dest) is None or _same_unit(src, dest):
        return None
    return MathIntent(
        kind="unit",
        school_op="convert",
        percent_base=float(stated.group("n")),
        unit_from=src,
        unit_to=dest,
        operation="solve",
    )


# "2 hr + 20 min + 60 sec are equal to how many minutes?" (the same book): a sum of
# amounts in different units of one kind, asked in one unit.
_TERM = rf"\d+(?:\.\d+)?\s*{_UNIT}"
_SUM = rf"(?P<sum>{_TERM}(?:\s*\+\s*{_TERM})+)"
_SUM_ASKS = (
    re.compile(
        rf"{_SUM}\s+(?:is|are|equals?|makes?|are\s+equal\s+to|is\s+equal\s+to)\s+"
        rf"how\s+many\s+(?P<to>{_UNIT})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"how\s+many\s+(?P<to>{_UNIT})\s+(?:are\s+there\s+in|are\s+in|is|are|in|make)\s+{_SUM}",
        re.IGNORECASE,
    ),
)
_TERM_PARTS = re.compile(rf"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT})")


def extract_quantity_sum(cleaned: str) -> MathIntent | None:
    """The sum of amounts of one kind, in the unit its ask names: every amount is put in
    the last one's unit and added, "2 hr + 20 min + 60 sec" is 8460 sec."""
    text = " ".join(cleaned.split()).strip(" ?.!")
    asked = next((m for pattern in _SUM_ASKS if (m := pattern.fullmatch(text))), None)
    if asked is None:
        return None
    terms = list(_TERM_PARTS.finditer(asked.group("sum")))
    base, dest = terms[-1].group("unit"), asked.group("to")
    if {base.lower(), dest.lower()} & _UNSURE_UNITS or _converts(1.0, base, dest) is None:
        return None
    total = 0.0
    for term in terms:
        value = _converts(float(term.group("n")), term.group("unit"), base)
        if value is None:
            return None
        total += value
    return MathIntent(
        kind="unit",
        school_op="convert",
        percent_base=total,
        unit_from=base,
        unit_to=dest,
        operation="solve",
    )
