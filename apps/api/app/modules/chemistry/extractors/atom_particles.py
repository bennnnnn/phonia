# ruff: noqa: RUF001, RUF002, RUF003 -- a charge is written with a minus sign or a dash.
"""An atom's particles read from what a question gives: A, Z, protons, neutrons, electrons.

"An atom 70X has 31 electrons. How many neutrons?" was answered 70 − 31 = 40, and
"magnesium, mass number 24, atomic number 12: protons, neutrons, electrons and the
arrangement" with the neutrons alone (2026-10-30, a Class 9 book). One reader takes every
fact a question states about one atom or ion, in any order and notation (``70X``,
``27Al``, ``Al-27``, ``Hg2+``, "atomic number 15", "18 neutrons", "magnesium"), and asks
the solver for every quantity it names that was not given.
"""

from __future__ import annotations

import re

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_facts import ELEMENT_NAMES

_N = r"(\d{1,3})"
_LINK = r"\s*(?:of\s+(?:an?\s+|the\s+)?(?:[a-z]+\s+)?|is\s+|=|:|equal\s+to\s+|as\s+)?\s*"
_FACTS: dict[str, tuple[re.Pattern[str], ...]] = {
    "mass_number": (
        re.compile(rf"\bmass\s+number{_LINK}{_N}\b", re.IGNORECASE),
        re.compile(rf"\b{_N}\s+(?:is\s+(?:its|the)\s+|as\s+(?:its|the)\s+)?mass\s+number", re.I),
    ),
    "atomic_number": (
        re.compile(rf"\batomic\s+number{_LINK}{_N}\b", re.IGNORECASE),
        re.compile(rf"\b{_N}\s+(?:is\s+(?:its|the)\s+|as\s+(?:its|the)\s+)?atomic\s+number", re.I),
    ),
    "protons": (
        re.compile(rf"\b{_N}\s+protons?\b", re.IGNORECASE),
        re.compile(rf"\bprotons?\s*(?:=|:|is|are)\s*{_N}\b", re.IGNORECASE),
    ),
    "neutrons": (
        re.compile(rf"\b{_N}\s+neutrons?\b", re.IGNORECASE),
        re.compile(rf"\bneutrons?\s*(?:=|:|is|are)\s*{_N}\b", re.IGNORECASE),
    ),
    "electrons": (
        re.compile(rf"\b{_N}\s+(?!valence|outer|shared|unpaired|lone)electrons?\b", re.I),
        re.compile(rf"(?<!valence\s)\belectrons?\s*(?:=|:|is|are)\s*{_N}\b", re.IGNORECASE),
    ),
}
# "70X", "27Al", "^{27}Al", "Al-27", "201Hg2+", "80Br–": a nuclide or an ion written out.
_NUCLIDE = re.compile(
    r"(?<![\w^{])(?:\^\{?)?(?P<mass>\d{1,3})\}?(?P<symbol>[A-Z][a-z]?)"
    r"(?P<charge>\d?[+\-−–])?(?![a-z])"
    r"|\b(?P<symbol2>[A-Z][a-z]?|[A-Za-z]{3,})-(?P<mass2>\d{1,3})\b"
)
_ION = re.compile(r"(?<![\w])(?P<symbol>[A-Z][a-z]?)(?P<charge>\d?[+\-−–])(?![\w])")
# A symbol that is also a unit or a grade ("10C" of charge, "24V", "100W", "10N", "40K",
# "B-12") is a nuclide only where the line is about atoms.
_UNIT_LETTERS = frozenset("CVWNAKJFHTSBPU")
_ABOUT_ATOMS = re.compile(r"\b(?:atoms?|nucle(?:us|i)|isotopes?|nuclides?|ions?|element)\b", re.I)
# Electricity, forces and beams: "How many electrons flow through a 24V battery?" is physics.
_PHYSICS = re.compile(
    r"\b(?:current|wires?|batter(?:y|ies)|volts?|voltage|watts?|bulbs?|capacitors?|coulombs?"
    r"|flows?|per\s+second|forces?|circuits?|resistors?|accelerated|potential\s+difference"
    r"|fields?|beams?|charged\s+particles?|orbits?|radius|wavelength|de\s+broglie|speed"
    r"|velocity|energy\s+levels?|drops?|jumps?|photons?|n\s*=)",
    re.IGNORECASE,
)
_COUNT = r"(?P<n>\d|one|two|three)"
_WORD_COUNT = {"one": 1, "two": 2, "three": 3}
# "gains 1 electron", "after losing two electrons": the change that makes the ion.
_GAIN_LOSS = re.compile(
    rf"\b(?P<verb>gain\w*|accept\w*|receiv\w*|los(?:e|es|ing|t)|donat\w*|giv\w*(?:\s+(?:up|away))?)"
    rf"\s+{_COUNT}\s+electrons?\b",
    re.IGNORECASE,
)
# "3 electrons in its outermost shell": a shell's count, never the atom's.
_SHELL_COUNT = re.compile(
    r"\b\d{1,2}\s+electrons?\s+in\s+(?:its|the|their)\s+(?:outer\w*|valence|last|\w+)\s+shell",
    re.IGNORECASE,
)
_CHARGE_WORDS = re.compile(r"\bcharge\s+(?:of\s+)?(?P<sign>[+\-−])\s?(?P<size>\d)\b", re.I)
_PARTICLE = re.compile(r"\b(?:protons?|neutrons?|electrons?|atomic\s+number|mass\s+number)\b", re.I)
# Each quantity a question can ask for, by the words that ask it.
_ASKED: dict[str, re.Pattern[str]] = {
    "protons": re.compile(r"\bprotons?\b", re.IGNORECASE),
    "neutrons": re.compile(r"\bneutrons?\b", re.IGNORECASE),
    "electrons": re.compile(
        r"(?<!valence\s)\belectrons?\b"
        r"(?!\s+(?:with|that|are\s+replaced|configuration|arrangement|distribution))",
        re.I,
    ),
    "atomic_number": re.compile(r"\batomic\s+number\b", re.IGNORECASE),
    "mass_number": re.compile(r"\bmass\s+number\b", re.IGNORECASE),
    "configuration": re.compile(
        r"\b(?:electronic|electron|its)\s+(?:configuration|arrangement|distribution)"
        r"|\barrangement\s+of\s+(?:the\s+)?electrons\b",
        re.IGNORECASE,
    ),
    "valence": re.compile(r"\bvalence\s+electrons?\b", re.IGNORECASE),
    "valency": re.compile(r"\bvalency\b", re.IGNORECASE),
    "name": re.compile(
        r"\b(?:name|identify)\s+(?:the\s+)?(?:element|species|atom)|\bwhich\s+element\b"
        r"|\bname\s+of\s+the\s+element|\b(?:its|the)\s+name\b",
        re.IGNORECASE,
    ),
    "kind": re.compile(r"\bneutral\b.*\b(?:cation|anion)\b", re.IGNORECASE | re.DOTALL),
    "charge": re.compile(r"\b(?:its|the|what)\s+(?:\w+\s+)?charge\b", re.IGNORECASE),
}
# Not one atom: amounts, reactions, several species, or a hypothetical particle.
_DECLINE = re.compile(
    r"\b(?:moles?|mol|grams?|molecules?|compounds?|reaction|isotopes\s+of|hypothetical"
    r"|replaced|table|respectively|ratio|percentage|abundance|average|decay\w*|emits?"
    r"|alpha|beta|gamma|daughter|product|fission|fusion|compared?|versus|vs|kg|block)\b"
    # A count of ions: "How many electrons are in 3 Na+ ions?"
    r"|\b\d+\s+\S+\s+ions\b",
    re.IGNORECASE,
)
_ION_WORD = re.compile(r"\bions?\b|\b\w+ide\b", re.IGNORECASE)
# Some of the electrons, not all, as the question asks them: valence, unpaired, outer,
# bonding, d-electrons. Read as the atom's count, "electrons in its valence shell" of Ga was
# certified 31 and "unpaired electrons in Cr3+" 21 (2026-10-30, Ethiopian Grade 9 and 11
# chemistry books). Said of a given ("3 electrons in its outermost shell. What is its
# valency?") it is a fact the reader uses.
_SOME_ELECTRONS = re.compile(
    r"\b(?:valence|unpaired|paired|outer(?:most)?|inner(?:most)?|core|bonding|non-?bonding"
    r"|lone)\b|\b[spdf](?:\s*-)?\s*electrons\b",
    re.IGNORECASE,
)
# A sentence that asks: it ends on "?" or opens with an order. Split first, then read each
# one, so a long run of spaces is read once, never once per position.
_SENTENCE_END = re.compile(r"(?<=[.?!\n])")
_ORDER = re.compile(r"(?:how\s+many|find|state)\b", re.IGNORECASE)
_ATOM = re.compile(r"\batom\b(?!ic)", re.IGNORECASE)
_SHELL_RULE_LAST = 20
# One number a one-line law already reads ("how many neutrons in carbon-14", "the charge
# of the ion"): that law answers it, in its own layout.
_ONE_LAWS = frozenset({"neutron_count", "ion_charge"})
_SIGN = {"+": 1, "-": -1, "−": -1, "–": -1}


def _one_law_reads(text: str) -> bool:
    from app.modules.chemistry.binding import bind_chemistry_intent

    bound = bind_chemistry_intent(text)
    return bound is not None and bound.chemistry_op in _ONE_LAWS


def _element(word: str) -> str | None:
    if word in BY_SYMBOL:
        return word
    return ELEMENT_NAMES.get(word.lower())


def _charge(text: str) -> int | None:
    if not text:
        return None
    size = int(text[:-1]) if text[:-1] else 1
    return size * _SIGN[text[-1]]


def _placeholder(letter: str, text: str) -> bool:
    """ "element X", "atom X", "X has": a letter standing for an unnamed element."""
    return (
        letter not in BY_SYMBOL
        and re.search(rf"\b(?:element|atom|ion|species)\s+{letter}\b|\b{letter}\s+has\b", text)
        is not None
    )


def particle_asks(text: str) -> int:
    """How many of an atom's quantities ``text`` asks for: an instant reply answering
    fewer drops the rest."""
    asking = _not_counts(text)
    stated = {name for name, patterns in _FACTS.items() if any(p.search(asking) for p in patterns)}
    return sum(
        1 for name, pattern in _ASKED.items() if name not in stated and pattern.search(asking)
    )


def _not_counts(text: str) -> str:
    """``text`` without counts that are no atom's total: a shell's, or electrons gained
    or lost. Neither gives the electrons nor asks for them."""
    return _SHELL_COUNT.sub(" ", _GAIN_LOSS.sub(" ", text))


def asks_more_particles(text: str, answers: str) -> bool:
    """``text`` asks for more of an atom's quantities than ``answers`` has lines: "What is
    the electronic configuration of magnesium? How many protons?" answered with the
    configuration alone."""
    lines = [line for line in answers.splitlines() if line.strip()]
    return particle_asks(text) > max(len(lines), 1)


def _gain_loss(text: str) -> int | None:
    """The ion's charge from "gains 2 electrons" (-2) or "loses one electron" (+1)."""
    found = _GAIN_LOSS.search(text)
    if found is None:
        return None
    size = _WORD_COUNT.get(found.group("n").lower()) or int(found.group("n"))
    gains = found.group("verb").lower().startswith(("gain", "accept", "receiv"))
    return -size if gains else size


def _species(text: str) -> set[str]:
    """Each atom or ion written by symbol, charge included: {"Na", "Na+"}."""
    found = {
        match.group(0)
        for match in re.finditer(r"(?<![\w])[A-Z][a-z]?(?:\d?[+\-−–])?(?![\w+\-−–])", text)
        if match.group(0).rstrip("+-−–0123456789") in BY_SYMBOL
    }
    return found | {f"{name}" for name in _named_elements(text)} if found else found


def _asked_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in _SENTENCE_END.split(text)
        if sentence.rstrip().endswith("?") or _ORDER.match(sentence.lstrip())
    ]


def _named_elements(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z]+", text)
    return {ELEMENT_NAMES[word.lower()] for word in words if word.lower() in ELEMENT_NAMES}


def extract_atom_particles(text: str) -> ChemistryIntent | None:
    """One atom or ion: the facts given, and the quantities asked that were not."""
    if _PARTICLE.search(text) is None or _DECLINE.search(text) or _PHYSICS.search(text):
        return None
    if any(_SOME_ELECTRONS.search(asked) for asked in _asked_sentences(text)):
        return None
    params: dict[str, float] = {}
    changed = _gain_loss(text)
    counted = _not_counts(text)
    for name, patterns in _FACTS.items():
        values = {int(m.group(1)) for pattern in patterns for m in pattern.finditer(counted)}
        if len(values) > 1:
            return None
        if values:
            params[name] = float(values.pop())
    symbol: str | None = None
    nuclides = list(_NUCLIDE.finditer(text))
    if len(nuclides) > 1:
        return None
    if nuclides:
        found = nuclides[0]
        written = found.group("symbol") or found.group("symbol2") or ""
        mass = int(found.group("mass") or found.group("mass2"))
        if params.get("mass_number", mass) != mass:
            return None
        params["mass_number"] = float(mass)
        symbol = _element(written)
        if symbol is None and not re.fullmatch(r"[A-Z]", written):
            return None
        if written in _UNIT_LETTERS and not _ABOUT_ATOMS.search(text):
            return None
        # A nucleus holds at least its protons and at most about three times as many
        # nucleons: "150 V" is a voltage, never vanadium-150.
        if (
            symbol is not None
            and not BY_SYMBOL[symbol].number <= mass <= 3 * BY_SYMBOL[symbol].number
        ):
            return None
        charge = _charge(found.group("charge") or "")
        if charge is not None:
            params["charge"] = float(charge)
    ions = [
        match
        for match in _ION.finditer(text)
        if _element(match.group("symbol")) or _placeholder(match.group("symbol"), text)
    ]
    if not nuclides and len(ions) == 1:
        symbol = _element(ions[0].group("symbol"))
        params["charge"] = float(_charge(ions[0].group("charge")) or 0)
    worded = _CHARGE_WORDS.search(text)
    if worded and "charge" not in params:
        params["charge"] = float(_SIGN[worded.group("sign")] * int(worded.group("size")))
    # Two species ("Na and Na+", "F- or Ne") are a comparison, not one atom.
    if len(_species(text)) > 1:
        return None
    named = _named_elements(text) - ({symbol} if symbol else set())
    if symbol is None and len(named) == 1:
        symbol = named.pop()
    elif named:
        return None
    # "the oxide ion", "a chloride ion": an ion named in words has a charge this reader
    # cannot see, so its electrons are not the atom's.
    unseen = "charge" not in params and "electrons" not in params and changed is None
    if _ION_WORD.search(text) and unseen:
        return None
    stated = set(params)
    if changed is not None:
        if params.get("charge", changed) != changed:
            return None
        params["charge"] = float(changed)
    asked = [
        name for name, pattern in _ASKED.items() if pattern.search(counted) and name not in stated
    ]
    # Two facts, or an atomic number stated alone for what it decides by itself (its
    # arrangement, valency, protons): "the valency of an element with atomic number 16".
    # An element named alone is the configuration reader's, past calcium too.
    facts = len(params) + (symbol is not None)
    by_number = "atomic_number" in params or "protons" in params
    alone = {"configuration", "valence", "valency", "protons", "electrons", "name", "atomic_number"}
    if not asked or (facts < 2 and not (by_number and set(asked) <= alone)):
        return None
    # The shell rule stops at calcium: Fe3+'s configuration is the aufbau reader's to decline.
    z = BY_SYMBOL[symbol].number if symbol else params.get("atomic_number", params.get("protons"))
    if {"configuration", "valence", "valency"} & set(asked) and (z or 0) > _SHELL_RULE_LAST:
        asked = [item for item in asked if item not in {"configuration", "valence", "valency"}]
        if not asked:
            return None
    if len(asked) == 1 and _one_law_reads(text):
        return None
    return ChemistryIntent(
        kind="structure",
        chemistry_op="atom_particles",
        params=params,
        formula=symbol,
        # "an atom" is neutral; an ion or a "species" says its charge or has none to assume.
        target=",".join(asked) + ("|atom" if _ATOM.search(text) else ""),
    )
