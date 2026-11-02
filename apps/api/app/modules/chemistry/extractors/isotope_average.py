# ruff: noqa: RUF002 -- the weighted sum is written with a multiplication sign.
"""An average atomic mass: isotopes, their abundances, and any mass the question states.

"The atomic masses of the two stable isotopes of boron, ¹⁰B (20%) and ¹¹B (80%) are 10 and
11 respectively" was averaged from the isotope table's 10.0129 u and 11.0093 u (2026-10-31,
an Ethiopian Grade 7 book): a stated mass was read only when written with its unit. A value
the question gives beats the table, however it is given: in its isotope's own clause
("35Cl (34.969 u, 75.77%)", "chlorine-35 has a mass of 34.97"), as a list in the isotopes'
order ("are 10 and 11 respectively", "with abundances of 75% and 25%"), or as a table whose
header line names its columns.

Only what is certainly an input is read, and only when the question asks the average and
nothing else (``isotope_question``). A number counted in grams, g/mol, moles or atoms is a
sample's, never an isotope's mass. Masses are stated for every isotope or for none: one stray
number beside the last isotope is a misreading, not a mass.
"""

from __future__ import annotations

import re

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.extractors.isotope_question import (
    NUMBER,
    NUMBER_RE,
    asks_only_the_average,
    states_the_average,
    without_quoted,
)
from app.modules.chemistry.isotopes import ISOTOPE_MASSES
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_facts import ELEMENT_NAMES

_AVERAGE_ASK = re.compile(
    r"\b(?:(?:average|relative|mean)\s+)?atomic\s+(?:mass|weight)\b", re.IGNORECASE
)

# "35Cl", "^35Cl", "Cl-35" or "chlorine-35".
_ISOTOPE = re.compile(
    r"(?<![A-Za-z0-9.])(?P<before>\d{1,3})(?P<symbol>[A-Z][a-z]?)(?![a-z])"
    r"|\b(?P<element>[A-Z][a-z]?|[A-Za-z]{3,})-(?P<after>\d{1,3})\b"
)

# Case matters: "235U" is uranium, not 235 u.
_UNIT = r"(?:u|amu|Da)\b"
# Counted in grams, g/mol, moles or particles: a sample or a molar mass, never an isotope's.
_NOT_A_MASS = (
    r"(?!\s*(?i:[km]?g|grams?|kilograms?|mol|moles?|atoms?|molecules?|particles?|ions?"
    r"|nuclei|formula\s+units?)\b)"
)
# A mass noun, never "mass number": "mass", "masses", "isotopic mass", "atomic masses".
_MASS_NOUN = r"(?i:\b(?:relative\s+)?(?:atomic\s+|isotopic\s+)?mass(?:es)?\b)(?!\s+(?i:numbers?)\b)"

_ABUNDANCE = re.compile(rf"({NUMBER})\s*%")
# "34.969 u", or a number the text calls a mass: "a mass of 34.97", "with mass 6.015 amu".
_STATED_MASS = re.compile(
    rf"{_MASS_NOUN}\s*(?:(?i:of|is|=|:|equal\s+to)\s*)?({NUMBER}){_NOT_A_MASS}(?:\s*{_UNIT})?"
    rf"|({NUMBER})\s*{_UNIT}"
)

# One value of a list, with its percent sign or unit if written.
_ITEM = re.compile(rf"({NUMBER})(?:\s*(%|{_UNIT}))?{_NOT_A_MASS}")
# Values for every isotope at once: "10 and 11", "34.97 u, 36.97 u", "75%, 20% and 5%".
_LIST = re.compile(
    rf"(?<![\w.^-]){_ITEM.pattern}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+){_ITEM.pattern})+"
)
_RESPECTIVELY = re.compile(r"\s*\)?\s*,?\s*(?i:respectively)\b")
_LIST_LEAD = re.compile(r"(?i:\b(?:masses|abundances))\s*(?:(?i:of|are|:|=)\s*)?$")
_MASS_NOUN_RE = re.compile(_MASS_NOUN)
# Between a mass noun and its list only words naming the isotopes may stand: "The atomic
# masses of the two stable isotopes of boron, 10B (20%) and 11B (80%) are 10 and 11". Any
# other word ("nucleon numbers", "A =", "neutrons") makes the list something else.
_BRIDGE_WORDS = frozenset(
    {"of", "the", "a", "an", "two", "three", "four", "both", "these", "its", "their", "stable"}
    | {"natural", "naturally", "occurring", "isotope", "isotopes", "and", "are", "is", "were"}
    | {"have", "has", "approximately"}
)
_PARENTHETICAL = re.compile(r"\([^()]*\)")
# A sentence or a clause ends at a full stop, question mark or semicolon no digit follows.
_CLAUSE_END = re.compile(r"[.?!;](?!\d)|\n")

# A table's header line, which names its columns in order.
_COLUMN = re.compile(
    r"(?i:\b(?P<number>mass\s+numbers?)|\b(?P<mass>(?:atomic\s+|isotopic\s+)?mass(?:es)?)"
    r"|\b(?P<abundance>(?:relative\s+|natural\s+|percent(?:age)?\s+)?abundances?))\b"
)
# A stated mass this far from its mass number belongs to something else.
_MASS_NUMBER_GAP = 1.0


def _isotopes(text: str) -> list[tuple[str, int, int, int]]:
    """Each isotope written in the text: (symbol, mass number, start, end)."""
    found: list[tuple[str, int, int, int]] = []
    for match in _ISOTOPE.finditer(text):
        token = match.group("symbol") or match.group("element")
        symbol = token if token in BY_SYMBOL else ELEMENT_NAMES.get(token.lower())
        number = int(match.group("before") or match.group("after"))
        if symbol is None or number < BY_SYMBOL[symbol].number:
            return []
        found.append((symbol, number, match.start(), match.end()))
    return found


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _one_abundance(segment: str) -> float | None:
    values = [float(match.group(1)) for match in _ABUNDANCE.finditer(segment)]
    return values[0] if len(values) == 1 else None


def _masses_in(segment: str) -> list[float]:
    return [float(match.group(1) or match.group(2)) for match in _STATED_MASS.finditer(segment)]


# A mass written with its unit ("35 u", "6.02 amu"): if no isotope took it, it was not read.
_UNIT_MASS = re.compile(rf"(?<![\w.]){NUMBER}\s*{_UNIT}")
_PERCENTAGE = re.compile(rf"{NUMBER}\s*%")
# A sample's grams, moles or atoms ("a mass of 10 g"); a molar mass in g/mol is a mass.
_SAMPLE = re.compile(
    r"\s*(?i:[km]?g|grams?|kilograms?|mol|moles?|atoms?|molecules?|particles?|ions?|nuclei"
    r"|formula\s+units?)\b(?!\s*(?i:/|per\s)\s*(?i:mol))"
)


def _unread_mass(read: str, isotopes: list[tuple[str, int, int, int]]) -> bool:
    """Whether the text states a mass no isotope took: a number with a mass unit, or a number
    near an isotope's mass number that a mass noun leads past only words naming the isotopes
    ("the relative masses of 6Li and 7Li are 6.0 and 7.0", "molar masses 6.015 g/mol and
    7.016 g/mol"), never a sample's grams nor "(1 mark)" or "to 2 decimal places" after
    "the relative atomic mass of hydrogen". The table's masses would then answer another
    question (2026-11-01: four questions stating their masses were averaged from the
    table)."""
    for _symbol, _number, start, end in isotopes:
        read = _blank(read, start, end)
    if _UNIT_MASS.search(read):
        return True
    read = _PERCENTAGE.sub(lambda match: " " * len(match.group()), read)
    symbol = isotopes[0][0]
    mass_numbers = [number for _symbol, number, _start, _end in isotopes]
    for found in NUMBER_RE.finditer(read):
        if _SAMPLE.match(read, found.end()) or not _names_masses(
            _clause_before(read, found.start()), symbol
        ):
            continue
        value = float(found.group())
        if any(abs(value - number) <= _MASS_NUMBER_GAP for number in mass_numbers):
            return True
    return False


def _clause_before(text: str, start: int) -> str:
    ends = [match.end() for match in _CLAUSE_END.finditer(text, 0, start)]
    return text[ends[-1] if ends else 0 : start]


_POSSESSIVE = re.compile(r"(?<=[A-Za-z])['\u2019]s\b")


def _names_masses(lead: str, symbol: str) -> bool:
    """Whether a mass noun leads the list, past only words naming the isotopes."""
    nouns = list(_MASS_NOUN_RE.finditer(lead))
    if not nouns:
        return False
    bridge = _PARENTHETICAL.sub(" ", _ISOTOPE.sub(" ", lead[nouns[-1].end() :]))
    # "lithium's isotopes" names them as "the isotopes of lithium" does.
    bridge = _POSSESSIVE.sub("", bridge)
    if re.sub(r"[A-Za-z\s,^]", "", bridge):
        return False
    known = _BRIDGE_WORDS | {symbol.lower(), BY_SYMBOL[symbol].name.lower()}
    return all(word.lower() in known for word in re.findall(r"[A-Za-z]+", bridge))


def _lists(
    text: str, count: int, symbol: str
) -> tuple[list[float] | None, list[float] | None, str]:
    """Masses and abundances given as lists in the isotopes' order, and the text without them.

    A list counts only when it names every isotope and says it is theirs: "respectively"
    follows it, or "masses" or "abundances" leads it. Percent signs make it the abundances;
    bare numbers or units, the masses, when a mass noun leads them (``_names_masses``).
    """
    masses: list[float] | None = None
    abundances: list[float] | None = None
    blanked = text
    for match in _LIST.finditer(text):
        items = list(_ITEM.finditer(match.group()))
        lead = _clause_before(text, match.start())
        if len(items) != count or not (
            _RESPECTIVELY.match(text, match.end()) or _LIST_LEAD.search(lead)
        ):
            continue
        values = [float(item.group(1)) for item in items]
        signs = {item.group(2) == "%" for item in items}
        if signs == {True} and abundances is None:
            abundances = values
        elif signs == {False} and masses is None and _names_masses(lead, symbol):
            masses = values
        else:
            continue
        blanked = _blank(blanked, match.start(), match.end())
    return masses, abundances, blanked


def _table(
    text: str, isotopes: list[tuple[str, int, int, int]]
) -> tuple[list[float], list[float]] | None:
    """Masses and abundances from rows under a header line naming the columns.

    "Isotope | Mass (u) | Abundance (%)" over "24Mg | 23.985 | 78.99": each row holds one
    number per named column. Abundances that add to 1 are fractions of the whole.
    """
    above = text[: text.rfind("\n", 0, isotopes[0][2]) + 1].splitlines()
    # A markdown table's |---|---| rule sits between the header and the rows.
    while above and not above[-1].strip(" \t|-:"):
        above.pop()
    if not above:
        return None
    columns = [match.lastgroup for match in _COLUMN.finditer(above[-1])]
    if columns.count("mass") != 1 or columns.count("abundance") != 1:
        return None
    masses: list[float] = []
    abundances: list[float] = []
    for _symbol, _number, start, end in isotopes:
        # Each isotope opens its own row.
        if text[text.rfind("\n", 0, start) + 1 : start].strip(" \t|"):
            return None
        line_end = text.find("\n", end)
        row = text[end : len(text) if line_end < 0 else line_end]
        values = [float(match.group()) for match in NUMBER_RE.finditer(row)]
        if len(values) != len(columns):
            return None
        masses.append(values[columns.index("mass")])
        abundances.append(values[columns.index("abundance")])
    if abs(sum(abundances) - 1) <= 0.001:
        abundances = [value * 100 for value in abundances]
    return masses, abundances


def extract_average_atomic_mass(text: str) -> ChemistryIntent | None:
    """Isotopes with their abundances: Σ mass × abundance / 100."""
    if not _AVERAGE_ASK.search(text):
        return None
    isotopes = _isotopes(text)
    if len(isotopes) < 2 or len({symbol for symbol, *_ in isotopes}) != 1:
        return None
    spans = [(start, end) for _, _, start, end in isotopes]
    read = without_quoted(text, spans)
    if states_the_average(read) or not asks_only_the_average(read, spans):
        return None
    table = _table(read, isotopes)
    listed_masses: list[float] | None
    listed_abundances: list[float] | None
    if table is not None:
        listed_masses, listed_abundances = table
        read = " " * len(read)
    else:
        listed_masses, listed_abundances, read = _lists(read, len(isotopes), isotopes[0][0])
    abundances: dict[str, float] = {}
    masses: dict[str, float] = {}
    stated_count = 0
    for index, (symbol, number, _start, end) in enumerate(isotopes):
        # The isotope's own clause: up to the next isotope or the clause's end.
        stop = isotopes[index + 1][2] if index + 1 < len(isotopes) else len(read)
        clause_end = _CLAUSE_END.search(read, end, stop)
        segment = read[end : clause_end.start() if clause_end else stop]
        abundance = _one_abundance(segment)
        said = _masses_in(segment)
        if len(said) > 1:
            return None  # two masses for one isotope: which one is its, the reader cannot tell
        stated = said[0] if said else None
        if listed_abundances is not None:
            if abundance is not None:
                return None  # given twice: which one holds is not ours to pick
            abundance = listed_abundances[index]
        if listed_masses is not None:
            if stated is not None:
                return None
            stated = listed_masses[index]
        if stated is not None:
            if abs(stated - number) > _MASS_NUMBER_GAP:
                return None
            stated_count += 1
        mass = stated if stated is not None else ISOTOPE_MASSES.get((symbol, number))
        label = f"{symbol}-{number}"
        if abundance is None or mass is None or label in abundances:
            return None
        abundances[label] = abundance
        masses[label] = mass
    if stated_count not in {0, len(isotopes)}:
        return None
    if stated_count == 0 and _unread_mass(read, isotopes):
        return None
    if abs(sum(abundances.values()) - 100) > 0.1:
        return None
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="average_atomic_mass",
        target=isotopes[0][0],
        species=abundances,
        params=masses,
    )
