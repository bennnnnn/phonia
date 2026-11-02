"""The units, cues and resistor lists a circuit question is read by."""

from __future__ import annotations

import re

from app.modules.physics.extractors.counted_parts import counted_resistors, resistances
from app.modules.physics.extractors.stated_values import positioned_values
from app.modules.physics.extractors.unit_patterns import AMP_PATTERN, OHM_PATTERN

_CIRCUIT_CUES = (
    "ohm",
    "voltage",
    "volts",
    "resistor",
    "ampere",
    # Round 3. Each of these is electrical vocabulary and nothing else -
    # unlike "charge" (a card is charged) and "current" (the current date),
    # which stay out and are reached by co-occurrence below.
    "capacitance",
    "capacitor",
    "farad",
    "coulomb",
    "internal resistance",
    "terminal voltage",
    "electromotive force",
    "time constant",
    "parallel plate",
)

_VOLT_PATTERN = r"V|volts?"

_VOLT_CUE = r"V|[Vv]olts?"

_AMP_CUE = r"A|[Aa]mp(?:s|ere|eres)?"

_OHM_CUE = r"[Oo]hms?|\u03a9"


def _circuit_pair(first: str, second: str) -> re.Pattern[str]:
    """A number in `first`'s unit within 80 chars of a number in `second`'s.

    No IGNORECASE: the bare letters below are the SI symbols, and the spelled
    out forms carry their own case classes. `_has_cue_either_case` is what
    makes this reachable from the pre-filter.
    """
    # A prefix stays the unit's: "20 mA from a 3 V supply", "a 4.7 kΩ resistor".
    prefix = "(?:k|m|M|µ|μ)?"
    return re.compile(
        rf"\d\s*{prefix}(?:{first})(?![A-Za-z0-9]).{{0,80}}?\d\s*{prefix}(?:{second})(?![A-Za-z0-9])"
    )


_CHARGE_FLOW_RE = re.compile(
    rf"\bcharge\b.{{0,60}}?\d\s*(?:{AMP_PATTERN})(?![A-Za-z0-9])"
    rf"|\d\s*(?:{AMP_PATTERN})(?![A-Za-z0-9]).{{0,60}}?\bcharge\b",
    re.IGNORECASE,
)

_WATT_PATTERN = r"W|watts?|kW|kilowatts?"

_ELECTRICAL_ENERGY_RE = re.compile(
    rf"\b(?:energy|consumes?|consumed|uses?|used|costs?)\b.{{0,80}}?"
    rf"\d\s*(?:{_WATT_PATTERN})(?![A-Za-z0-9])"
    rf"|\d\s*(?:{_WATT_PATTERN})(?![A-Za-z0-9]).{{0,80}}?"
    rf"\b(?:energy|consumes?|consumed|uses?|used|costs?)\b",
    re.IGNORECASE,
)

_COULOMB_PATTERN = (
    r"uC|µC|μC|nC|pC|mC|C|microcoulombs?|nanocoulombs?|picocoulombs?|millicoulombs?|coulombs?"
)

_FARAD_PATTERN = r"mF|uF|µF|nF|pF|F|farads?|microfarads?|nanofarads?|picofarads?"

_CIRCUIT_TIME_UNITS = r"seconds?|secs?|sec|s|minutes?|mins?|min|hours?|hrs?|hr|h"

_TERMINAL_ASK_RE = re.compile(
    r"\bterminal\b|\bacross the terminals\b|\blost volts\b|\bp\.?d\.? across\b",
    re.IGNORECASE,
)

# Everyday words first: a phone battery at 20 percent, circuit training three
# times a week, a resistance band. Each is a circuit only beside an electrical
# value; "amps" is a word, not the inside of "lamps".
_EVERYDAY_CIRCUIT_RE = re.compile(
    r"\A(?=.*\b(?:batter(?:y|ies)|circuits?|resistances?)\b)"
    rf"(?=.*\d\s*(?:k|m|M)?(?:{_VOLT_CUE}|{_AMP_CUE}|{_OHM_CUE}|W|[Ww]atts?)(?![A-Za-z0-9]))",
    re.DOTALL,
)
_AMPS_WORD_RE = re.compile(r"\bamps\b", re.IGNORECASE)

_CIRCUIT_CUE_RES: tuple[re.Pattern[str], ...] = (
    _EVERYDAY_CIRCUIT_RE,
    _AMPS_WORD_RE,
    _circuit_pair(_VOLT_CUE, rf"{_AMP_CUE}|{_OHM_CUE}"),
    _circuit_pair(rf"{_AMP_CUE}|{_OHM_CUE}", _VOLT_CUE),
    _circuit_pair(_AMP_CUE, _OHM_CUE),
    _circuit_pair(_OHM_CUE, _AMP_CUE),
    _CHARGE_FLOW_RE,
    _ELECTRICAL_ENERGY_RE,
)

_MAX_NETWORK_RESISTORS = 4

# At most one value past the limit, which is enough to refuse a longer network.
# An unbounded list made every number of a pasted CSV restart the whole scan:
# seconds of backtracking at 20,000 characters.
_RESISTOR_LIST_RE = re.compile(
    r"((?<!\d)\d+(?:\.\d+)?(?:\s*(?:,|and)\s*\d+(?:\.\d+)?)"
    rf"{{1,{_MAX_NETWORK_RESISTORS}}})\s*(?:ohms?|\u03a9)",
    re.IGNORECASE,
)


_MAX_COUNTED_RESISTORS = 6


# "each with a resistance of 10 Ω", "lamps of resistance 6 Ω" state a resistance; they do
# not ask for one.
_STATED_RESISTANCE_RE = re.compile(
    r"\b(?:a|an|the\s+same|of|with(?:\s+a)?)\s+resistance\s+(?:of\s+)?(?=\d)"
)


def network_asks(lower: str) -> tuple[bool, bool]:
    """Whether a network question asks for a current, and whether for a resistance."""
    asks_current = re.search(r"\bcurrents?\b", lower) is not None
    unstated = _STATED_RESISTANCE_RE.sub(" ", lower)
    return asks_current, re.search(r"\bresistances?\b", unstated) is not None


def resistor_values(text: str) -> list[float]:
    """Every resistance in a network, however the units are distributed.

    A count repeats its value: "three 9 Ω resistors" are 9, 9 and 9 Ω.
    Read as one 9 Ω resistor, a parallel bank across 6 V drew 0.667 A, not 2 A.
    """
    counted = counted_resistors(text)
    if counted is not None:
        count, value = counted
        if len(resistances(text)) != 1:
            # Other resistors beside the counted ones: a network this does not read.
            return []
        return [value] * count
    listed = _RESISTOR_LIST_RE.search(text)
    if listed is not None:
        return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", listed.group(1))]
    if _UNKNOWN_RESISTOR_RE.search(text) and not _VALUED_R_RE.search(text):
        # "a 3 Ω resistor and a resistor R": the network's total is not the known ones'.
        return []
    return _stated_resistances(text)


# A resistor the question has not valued: "a resistor R", "an unknown resistor"; not "a
# resistor R of 6 Ω" or "R = 4 Ω".
_UNKNOWN_RESISTOR_RE = re.compile(r"\b[Rr]esistors?\s+R\b(?!\s*[=_\d])|\bunknown\s+resist")
_VALUED_R_RE = re.compile(r"\bR\s*(?:=|is\b|of\b)")
# A part named without a value of its own: "an identical resistor", "a lamp of the same
# resistance", "another resistor" with no value after it. Read as the one resistor stated,
# "a 6 Ω resistor in parallel with an identical resistor across 12 V" drew 2 A (it is 4 A).
_PART_NOUNS = (
    r"(?:ones?|resistors?|lamps?|bulbs?|heaters?|coils?|wires?|conductors?|elements?"
    r"|components?|appliances?)"
)
_UNVALUED_PART_RE = re.compile(
    rf"\b(?:identical|similar|equal|matching)\s+{_PART_NOUNS}\b"
    r"|\bsame\s+(?:value|resistance|rating)\b"
    rf"|\b(?:another|second)\s+{_PART_NOUNS}\b(?!\s+(?:of\s+)?(?:resistance\s+)?(?:of\s+)?\d)"
)


def unvalued_part(lower: str) -> bool:
    """The question names a resistive part it gives no value of its own."""
    return _UNVALUED_PART_RE.search(lower) is not None


# A place that introduces a part: "a 6 Ω", "another 6 Ω", or the part named first — "a
# resistor of 6 Ω", "another lamp of resistance 6 Ω". The words between the article and
# the value are read whole against this list, so "the 6 Ω resistor" (a part named again)
# is never an introduction.
_INTRODUCERS = frozenset({"a", "an", "another", "one"})
_DEFINITES = frozenset({"the", "this", "that"})
_PART_NOUN_WORDS = frozenset(
    {
        *("resistor", "lamp", "bulb", "heater", "coil", "wire", "conductor", "element"),
        *("of", "resistance", "carbon", "fixed", "small", "large", "second", "electric"),
    }
)
# Between two values of one list: "6 Ω, 6 Ω and 3 Ω", "a 6 Ω and a 6 Ω resistor". Read as
# words, so no pattern scans a long run of spaces.
_LIST_WORD_RE = re.compile(r",|[^\s,]+")
_LIST_UNITS = frozenset({"\u03a9", "\u03c9", "ohm", "ohms"})
_LIST_JOINERS = ([","], [",", "and"], ["and"], [",", "or"], ["or"])


def _joins_list(between: str) -> bool:
    words = _LIST_WORD_RE.findall(between.lower())
    if words[:1] and words[0] in _LIST_UNITS:
        words = words[1:]
    if words[:1] in (["resistor"], ["resistors"]):
        words = words[1:]
    if words[-1:] in (["a"], ["an"], ["the"], ["another"]):
        words = words[:-1]
    return words in _LIST_JOINERS


def _stated_resistances(text: str) -> list[float]:
    """Each resistance stated, or none when one may be named twice.

    A value stated in two places is two resistors only when each place introduces one
    ("a 6 Ω resistor … another 6 Ω resistor"), or when both are in one list ("the 6 Ω,
    6 Ω and 3 Ω resistors"). Anywhere else the second place may name the first: "the p.d.
    across the 50 Ω resistor", "R1 (50 Ω)", "which resistor, 50 Ω or 100 Ω" each added a
    resistor to a certified total (2026-10-30, a Grade 10 physics book and its reviews)."""
    found = positioned_values(text, OHM_PATTERN)
    values = [value for _, value, _ in found]
    starts = [start for start, _, _ in found]
    ends = [_value_end(text, start) for start in starts]
    group = [0] * len(found)
    for index in range(1, len(found)):
        joined = _joins_list(text[ends[index - 1] : starts[index]])
        group[index] = group[index - 1] if joined else group[index - 1] + 1
    befores = [text[max(0, start - 60) : start] for start in starts]
    for value in set(values):
        places = [index for index, other in enumerate(values) if other == value]
        if len({group[index] for index in places}) < 2:
            continue
        if not all(_introduces(befores[index]) for index in places):
            return _one_part_named_again(text, values, befores)
    return values


def _one_part_named_again(text: str, values: list[float], befores: list[str]) -> list[float]:
    """One resistor stated, then named again by "the", "this" or "that" ("a 6 Ω resistor …
    the current in the 6 Ω resistor"), is one value; anything else is unread. An internal
    resistance is the cell's own part, never the resistor it equals: "internal resistance
    2 Ω … a 2 Ω resistor" read as one drew 6 A from 12 V (it is 3 A)."""
    if len(set(values)) != 1 or "internal" in text.lower():
        return []
    if not all(_names_again(before) for before in befores[1:]):
        return []
    return values[:1]


def _introduces(before: str) -> bool:
    """The words just before a value introduce a new part: an article, then only words of
    the part's own name ("a", "another resistor of", "a lamp of resistance")."""
    return _article_before(before, _INTRODUCERS, _PART_NOUN_WORDS)


def _names_again(before: str) -> bool:
    """The words just before a value name a part already met: "the", "this" or "that", then
    only words of the part's own name ("through the", "across this", "the same")."""
    return _article_before(before, _DEFINITES, _PART_NOUN_WORDS | {"same"})


def _article_before(before: str, articles: frozenset[str], name_words: frozenset[str]) -> bool:
    """Walking back from a value, one of ``articles`` is reached through at most four
    ``name_words``."""
    words = before.lower().split()
    for count, word in enumerate(reversed(words)):
        if word in articles:
            return True
        if word not in name_words or count >= 4:
            return False
    return False


def _value_end(text: str, start: int) -> int:
    """Where the number at ``start`` ends (its unit is part of the join that follows)."""
    match = re.match(r"\d+(?:\.\d+)?", text[start:])
    return start + (match.end() if match else 0)


# "R1 = 10 Ω", "R_2=20Ω": a resistor's name before its value, a given and not algebra.
_NAMED_RESISTOR_RE = re.compile(r"\bR_?\{?(\d{1,2})\}?\s*=\s*(?=\d)")


def without_resistor_names(text: str) -> str | None:
    """The question with its "R1 =" labels taken off, so the network reads as the same
    sentence written without them ("10 Ω is in series with 20 Ω").

    None when a name is used again ("R1 and R2 are in parallel", "the current through
    R2"): a network wired, or a value asked, by name, which this reader does not map.
    """
    labels = [match.group(1) for match in _NAMED_RESISTOR_RE.finditer(text)]
    if not labels:
        return text
    if len(set(labels)) != len(labels):
        return None
    for label in labels:
        if len(re.findall(rf"\bR_?\{{?{label}\}}?(?!\d)", text)) != 1:
            return None
    return _NAMED_RESISTOR_RE.sub("", text)
