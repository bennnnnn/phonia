"""Counted items: "two 10 Ω resistors", "two heaters, each rated 2 kW", "two 5 kg blocks".

A value stated once for several items is that value in each. Read as one item, two 10 Ω
resistors in parallel across 5 V drew 0.5 A, not 1 A, and two 5 kg blocks weighed 49.1 N
(2026-10-31, the model reader's translated questions and their review). Values and their
units come from the shared givens scanner, whose prefixes are case-sensitive ("500 mΩ" is
half an ohm, not 500 MΩ). The resistor network readers repeat a counted resistance; every
solve is held to the counts at the claim check (``physics.counted``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.physics.givens import Given, scan_givens
from app.services.law_binding.units import dimension_of
from app.services.number_text import count_word_pattern, number_word_value

# Any count a school question writes: "fifteen 40 W bulbs" and "a dozen 60 W bulbs" were read
# as one bulb (2026-11-01). A solve that cannot use the count declines (``physics.counted``).
_DOZEN = r"(?:half\s+a\s+|a\s+)?dozen"
_COUNT = (
    rf"{_DOZEN}|{count_word_pattern(low=2, high=20)}"
    r"|(?<![\d.,])(?:[2-9]|[1-9]\d)(?![\d.,])"
)
_SAME = r"(?:(?:identical|equal|similar)\s+)?"
# "two resistors", "each of the three lamps", "two identical heaters", "a pair of cells",
# "both capacitors", "two of them". The noun is a plural word, or "of them".
_COUNT_RE = re.compile(
    rf"\b(?P<count>{_COUNT}|a\s+pair\s+of|both)\s+{_SAME}",
    re.IGNORECASE,
)
_NOUN_RE = re.compile(
    r"\s*(?P<noun>of\s+(?:them|these|those)|others|[a-z]+(?:es|s))\b", re.IGNORECASE
)
# A counted value's items may be named a few words on: "two 100 W electric bulbs", "two 1.5 V
# dry cells", "three 40 W tube lights" were each read as one item (2026-11-01). The words
# between are the items' own, never a verb or a preposition ("two 4 Ω in series").
_LINKING = (
    r"(?:are|is|was|were|be|in|on|at|of|and|or|to|for|from|with|by|across|each|connected"
    r"|placed|joined|wired|used|run|left|switched|lit|kept)"
)
_LATER_NOUN_RE = re.compile(
    rf"\s*(?:(?!{_LINKING}\b)[a-z][a-z-]*\s+){{1,3}}?(?P<noun>[a-z]{{2,}}(?:es|s))\b",
    re.IGNORECASE,
)
# "each" before a value in its own clause: "each 10 Ω", "each rated 2 kW", "each of the two
# resistors has a resistance of 10 Ω".
# "each" before a value; not "each other" (toward each other at 20 m/s), and not an "each"
# that closes a value of its own ("1 µC each are 1 m apart").
_EACH_BEFORE = re.compile(r"\beach\b(?!\s+other\b)[^\d.;:?!\n]{0,60}\Z", re.IGNORECASE)
# "10 Ω each", then the clause goes on: "each, ...", "each are connected". Not "3 hours each
# day": that is a rate, not items.
_EACH_AFTER = re.compile(
    r"\s*each\b(?=\s*(?:[.,;:?!)]|\Z|(?:are|is|were|was|and|in|on|at|connected|placed|"
    r"joined|wired|arranged)\b))",
    re.IGNORECASE,
)
# A plural noun ("each of the resistors has 4 Ω"); not "across".
_PLURAL = re.compile(r"[a-z]{2,}[^s]s")
# The words that may stand between "each" and its value.
_EACH_LINKS = frozenset(
    "is are has have with of rated at having weighs weighing a an the its their one them "
    "these those value rating carries carrying holds stores draws pulls exerts and "
    "resistance capacitance mass weight power emf voltage charge stiffness spring constant "
    "length current speed velocity temperature volume area energy heat frequency force "
    "capacity rating".split()
)
# A value written straight after identical items: "three identical resistors of 6 Ω".
_ATTACHED = re.compile(
    r"\s*,?\s*(?:of|with|having|rated(?:\s+at)?)\s+(?:(?:a|an)\s+)?"
    r"(?:(?:resistance|capacitance|mass|weight|power|emf|voltage|charge|stiffness|spring|"
    r"constant)\s+){0,2}(?:of\s+)?",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.!?;](?=\s|$)|\n")
# A value that belongs to one item: "a 12 V battery", "the 20 Ω resistor".
_ONE_ITEM_BEFORE = re.compile(r"\b(?:a|an|one|the|another)\s+\Z", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CountedItems:
    """Items the question counts; ``count`` None when it says "each" but not how many."""

    noun: str
    count: int | None
    # The values stated once for every item, as the givens scanner reads them.
    each: tuple[Given, ...]


def _count(word: str) -> int:
    lower = word.lower()
    if lower.startswith(("a pair", "both")):
        return 2
    if lower.endswith("dozen"):
        return 6 if lower.startswith("half") else 12
    return int(lower) if lower.isdigit() else number_word_value(lower) or 0


def _unit_end(text: str, given: Given) -> int:
    """Where a given's unit ends (its number when it has none)."""
    if not given.unit:
        return given.end
    found = text.find(given.unit, given.end)
    return given.end if found < 0 else found + len(given.unit)


def _sentence(text: str, at: int) -> tuple[int, int]:
    edges = [0, *(found.end() for found in _SENTENCE_END.finditer(text)), len(text)]
    return max(edge for edge in edges if edge <= at), min(edge for edge in edges if edge > at)


def _each_governs(text: str, given: Given, nouns: frozenset[str], closing: set[int]) -> bool:
    """Whether "each" is said of a value: "10 Ω each", or "each" before it with only
    linking words, kinds of quantity, counts and the counted nouns between ("each rated
    2 kW", "each of the two resistors has a resistance of 10 Ω"; not "each are connected
    across 12 V"). An "each" that closes a value of its own says nothing of the next one
    ("1 µC each are 1 m apart")."""
    if _EACH_AFTER.match(text, _unit_end(text, given)):
        return True
    window = max(0, given.start - 60)
    before = _EACH_BEFORE.search(text[window : given.start])
    if before is None or window + before.start() in closing:
        return False
    # The word right after "each" names the item ("each resistor is 10 Ω").
    words = re.findall(r"[a-z]+", before.group(0).lower())[2:]
    return all(
        word in _EACH_LINKS or word in nouns or number_word_value(word) or _PLURAL.fullmatch(word)
        for word in words
    )


def counted_items(text: str) -> list[CountedItems]:
    """Every count of items in ``text``, each with the values stated for all of them."""
    givens = [given for given in scan_givens(text) if given.dimension is not None]
    counts: list[tuple[int, int, str, int, list[Given]]] = []
    for found in _COUNT_RE.finditer(text):
        if any(given.start == found.start("count") for given in givens):
            continue  # "5 kg": a value, not a count
        position, own = found.end(), []
        inside = next((given for given in givens if given.start == position), None)
        if inside is not None:  # "two 10 Ω resistors", "two 5 kg blocks"
            own.append(inside)
            position = _unit_end(text, inside)
        named = _NOUN_RE.match(text, position)
        if named is None and inside is not None:
            named = _LATER_NOUN_RE.match(text, position)
        if named is None:
            continue
        if found.group(0).rstrip().lower().endswith(("identical", "equal", "similar")):
            attached = _ATTACHED.match(text, named.end())
            after = next((g for g in givens if attached and g.start == attached.end()), None)
            if after is not None:
                own.append(after)
        count = _count(found.group("count"))
        counts.append((found.start(), named.end(), named.group("noun").lower(), count, own))
    plural = {noun for _, _, noun, _, _ in counts}
    # "Two resistors ... Each resistor is 3 Ω": the noun said once more, singular.
    nouns = frozenset(plural | {re.sub(r"(?:es|s)$", "", noun) for noun in plural})
    closing: set[int] = set()
    for given in givens:
        said = _EACH_AFTER.match(text, _unit_end(text, given))
        if said is not None:
            closing.add(said.end() - len("each"))
    each = [given for given in givens if _each_governs(text, given, nouns, closing)]
    found_items: list[CountedItems] = []
    for start, end, noun, count, own in counts:
        sentence = _sentence(text, start)
        mine = [g for g in each if sentence[0] <= g.start < sentence[1] and g.start >= end]
        found_items.append(CountedItems(noun, count, tuple(dict.fromkeys([*own, *mine]))))
    claimed = {given for item in found_items for given in item.each}
    loose = tuple(given for given in each if given not in claimed)
    if loose and len(found_items) == 1:
        # "Two resistors ... Each is 3 Ω", "Each resistor is 10 Ω. Two of them ...": the one
        # count names the items "each" is said of.
        only = found_items[0]
        found_items = [CountedItems(only.noun, only.count, (*only.each, *loose))]
    elif loose:
        found_items.append(CountedItems("", None, loose))
    return found_items


def resistance_ohms(given: Given) -> float | None:
    """A given's value in ohms, or None when it is no resistance."""
    if given.dimension != dimension_of("ohm") or given.si is None:
        return None
    return given.si


def resistances(text: str) -> list[Given]:
    """Every resistance ``text`` states, prefixes read ("500 mΩ", "2 kΩ")."""
    return [given for given in scan_givens(text) if resistance_ohms(given) is not None]


def counted_resistors(text: str) -> tuple[int, float] | None:
    """(count, ohms) of items stated once for all of them with a resistance ("three 9 Ω
    resistors", "two lamps of resistance 6 Ω each"), or None. Two counted groups ("two
    10 Ω resistors and three 20 Ω resistors") are no one network this reads."""
    groups = [
        (item.count, ohms)
        for item in counted_items(text)
        if item.count is not None
        for given in item.each
        if (ohms := resistance_ohms(given)) is not None
    ]
    return groups[0] if len(groups) == 1 else None


def one_item_value(text: str, given: Given) -> bool:
    """Whether a value belongs to one item: "a 12 V battery", "the 20 Ω resistor"."""
    return _ONE_ITEM_BEFORE.search(text[max(0, given.start - 12) : given.start]) is not None
