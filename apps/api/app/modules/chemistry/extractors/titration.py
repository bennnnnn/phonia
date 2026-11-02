"""Titrations, labelled or in words, and acid or base added to a buffer."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _floats,
    _search,
)
from app.modules.chemistry.request import CHEMICAL_FORMULA
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_facts import (
    NAMED_COMPOUNDS,
    NEUTRALIZING_ACIDS,
    NEUTRALIZING_BASES,
    STRONG_ACIDS,
    STRONG_BASES,
    WEAK_ACIDS,
    WEAK_BASES,
    is_formula,
)


def _extract_titration(text: str) -> ChemistryIntent | None:
    # Mixing an acid with a base is the same reaction a titration runs.
    if not re.search(r"\b(?:titrat|neutrali[sz]|mix(?:ing|ed|es)?\b)\w*", text, re.IGNORECASE):
        return None
    ma = _search(rf"\bMa\s*=\s*({_N})", text)
    va = _search(rf"\bVa\s*=\s*({_N})\s*L", text)
    mb = _search(rf"\bMb\s*=\s*({_N})", text)
    vb = _search(rf"\bVb\s*=\s*({_N})\s*L", text)
    if ma is None or va is None or mb is None:
        return _titration_in_words(text)
    params = {"ma": ma, "va_l": va, "mb": mb}
    if vb is not None:
        params["vb_l"] = vb
    ka = _search(rf"\bKa\s*=\s*({_N})", text, flags=0)
    kb = _search(rf"\bKb\s*=\s*({_N})", text, flags=0)
    if kb is not None and ka is None:
        params["kb"] = kb
        return ChemistryIntent(kind="acid_base", chemistry_op="titration_weak", params=params)
    if ka is not None or re.search(r"\bweak\b", text, re.IGNORECASE):
        if ka is None:
            return None
        params["ka"] = ka
        return ChemistryIntent(kind="acid_base", chemistry_op="titration_weak", params=params)
    return ChemistryIntent(kind="acid_base", chemistry_op="titration_strong", params=params)


def _extract_buffer_addition(text: str) -> ChemistryIntent | None:
    if not re.search(r"\bbuffer after adding\b", text, re.IGNORECASE):
        return None
    pka = _search(rf"\bpKa\s*=\s*({_N})", text)
    ha = _search(rf"\bHA\s*=\s*({_N})\s*mol", text)
    base = _search(rf"\bA-\s*=\s*({_N})\s*mol", text, flags=0)
    added = _search(rf"\badded\s*=\s*({_N})\s*mol", text)
    params = _floats(pka=pka, ha_moles=ha, a_moles=base, added_moles=added)
    if params is None:
        return None
    # "conjugate base A-" is not the reagent; only what is added counts.
    added_kinds = {
        kind.lower()
        for kind in re.findall(
            rf"\b(?:adding|added\s*=\s*{_N}\s*mol(?:\s+of)?)\s+(?:a\s+)?(?:strong\s+)?(acid|base)\b",
            text,
            re.IGNORECASE,
        )
    }
    if re.search(r"\badding\s+(?:HCl|HBr|HNO3|HI)\b", text):
        added_kinds.add("acid")
    if re.search(r"\badding\s+(?:NaOH|KOH|LiOH)\b", text):
        added_kinds.add("base")
    if len(added_kinds) != 1:
        return None
    target = added_kinds.pop()
    return ChemistryIntent(
        kind="acid_base",
        chemistry_op="buffer_addition",
        target=target,
        params=params,
    )


_SPECIES = rf"(?:{'|'.join(re.escape(name) for name in NAMED_COMPOUNDS)}|{CHEMICAL_FORMULA})"


# "25 mL of 0.10 M HCl", or a titrant named by concentration alone: "0.10 M NaOH".
_SOLUTION = re.compile(
    rf"(?:({_N})\s*(mL|L)\s+of\s+(?:an?\s+|the\s+)?)?({_N})\s*M\s+({_SPECIES})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


# "25.0 mL of NaOH is neutralized by...": a volume whose concentration is the unknown.
_VOLUME_OF = re.compile(
    rf"({_N})\s*(mL|L)\s+of\s+(?:an?\s+|the\s+)?({_SPECIES})(?![A-Za-z0-9])", re.IGNORECASE
)


# "after adding 10 mL of NaOH": the titrant's volume.
_ADDED = re.compile(
    rf"\b(?:adding|added|addition\s+of)\s+({_N})\s*(mL|L)\b"
    rf"(?:\s+of\s+(?:the\s+)?({_SPECIES})(?![A-Za-z0-9]))?",
    re.IGNORECASE,
)


def _species(token: str) -> str | None:
    named = NAMED_COMPOUNDS.get(token.lower())
    return named if named is not None else (token if is_formula(token) else None)


def _liters(value: str, unit: str) -> float:
    return float(value) / 1000 if unit.lower() == "ml" else float(value)


def _titration_in_words(text: str) -> ChemistryIntent | None:
    """A titration written in words: each volume belongs to the solution it is "of".

    "25 mL of 0.1 M HCl is titrated with 0.1 M NaOH. Find the pH after adding 10 mL of
    NaOH": HCl has 25 mL at 0.1 M, NaOH 0.1 M, and the 10 mL added is NaOH's. A volume no
    phrase ties to one solution declines rather than guess.
    """
    concentration: dict[str, float] = {}
    volume: dict[str, float] = {}
    # Where each solution phrase states its volume: "adding 10 mL of 0.1 M NaOH" is read
    # once, as the NaOH solution, not again as an added volume.
    stated_at: set[int] = set()
    typed_unit: dict[str, str] = {}
    for match in _SOLUTION.finditer(text):
        formula = _species(match.group(4))
        if formula is None or concentration.get(formula, float(match.group(3))) != float(
            match.group(3)
        ):
            return None
        concentration[formula] = float(match.group(3))
        if match.group(1) is not None:
            stated = _liters(match.group(1), match.group(2))
            if volume.get(formula, stated) != stated:
                return None
            volume[formula] = stated
            typed_unit[formula] = match.group(2)
            stated_at.add(match.start(1))
    if len(concentration) == 1 and re.search(r"\b(?:concentration|molarity)\b", text, re.I):
        return _unknown_concentration(text, concentration, volume, typed_unit)
    if len(concentration) == 2 and len(volume) == 1:
        needed = _unknown_volume(text, concentration, volume, typed_unit)
        if needed is not None:
            return needed
    if not re.search(r"\bpH\b", text):
        return None
    acids = [
        formula for formula in concentration if formula in STRONG_ACIDS or formula in WEAK_ACIDS
    ]
    bases = [
        formula for formula in concentration if formula in STRONG_BASES or formula in WEAK_BASES
    ]
    if len(acids) != 1 or len(bases) != 1 or len(concentration) != 2:
        return None
    acid, base = acids[0], bases[0]
    # The solvers count one OH- per formula unit: 0.1 M Ca(OH)2 is 0.2 M OH-, not 0.1.
    if STRONG_BASES.get(base, 1) != 1:
        return None
    for match in _ADDED.finditer(text):
        if match.start(1) in stated_at:
            continue
        named = _species(match.group(3)) if match.group(3) else None
        titrant = named or next((f for f in (acid, base) if f not in volume), None)
        added = _liters(match.group(1), match.group(2))
        # The same volume said twice is one statement; two different ones are ambiguous.
        if titrant not in (acid, base) or volume.get(titrant, added) != added:
            return None
        volume[titrant] = added
    if acid not in volume or base not in volume:
        return None
    params = {
        "ma": concentration[acid],
        "va_l": volume[acid],
        "mb": concentration[base],
        "vb_l": volume[base],
    }
    if acid in STRONG_ACIDS and base in STRONG_BASES:
        return ChemistryIntent(kind="acid_base", chemistry_op="titration_strong", params=params)
    ka = _search(rf"\bKa\s*=\s*({_N})", text, flags=0)
    kb = _search(rf"\bKb\s*=\s*({_N})", text, flags=0)
    if acid in WEAK_ACIDS and base in STRONG_BASES and ka is not None:
        return ChemistryIntent(
            kind="acid_base", chemistry_op="titration_weak", params={**params, "ka": ka}
        )
    if base in WEAK_BASES and acid in STRONG_ACIDS and kb is not None:
        return ChemistryIntent(
            kind="acid_base", chemistry_op="titration_weak", params={**params, "kb": kb}
        )
    return None


def _unknown_concentration(
    text: str,
    concentration: dict[str, float],
    volume: dict[str, float],
    typed_unit: dict[str, str],
) -> ChemistryIntent | None:
    """The concentration a neutralization finds: C₂ = C₁V₁ · ratio / V₂.

    One solution is known by its concentration and volume, the other by its volume alone
    ("25.0 mL of NaOH is neutralized by 20.0 mL of 0.100 M HCl"). The ratio counts protons
    and hydroxides: H2SO4 neutralizes two NaOH.
    """
    known = next(iter(concentration))
    volumes: dict[str, float] = {}
    typed = dict(typed_unit)
    for match in _VOLUME_OF.finditer(text):
        formula = _species(match.group(3))
        if formula is not None:
            volumes[formula] = _liters(match.group(1), match.group(2))
            typed[formula] = match.group(2)
    unknown = [formula for formula in volumes if formula != known]
    if len(unknown) != 1:
        return None
    if known not in volume:
        # "... is titrated with 0.1000 M NaOH and it takes 32.45 mL to reach the endpoint":
        # the one volume no solution owns is the titrant's.
        titrant = _titrant_volume(text, len(volumes))
        if titrant is None:
            return None
        volume[known] = _liters(*titrant)
        typed[known] = titrant[1]
    other = unknown[0]
    acid, base = (known, other) if known in NEUTRALIZING_ACIDS else (other, known)
    if acid not in NEUTRALIZING_ACIDS or base not in NEUTRALIZING_BASES:
        return None
    equivalents = {acid: NEUTRALIZING_ACIDS[acid], base: NEUTRALIZING_BASES[base]}
    return ChemistryIntent(
        kind="acid_base",
        chemistry_op="titration_concentration",
        formula=other,
        params={
            "known_concentration": concentration[known],
            "known_volume": volume[known],
            "unknown_volume": volumes[other],
            "ratio": equivalents[known] / equivalents[other],
        },
        # The volumes as typed, for the answer's Given rows (25.0 mL = 0.0250 L).
        units={
            "known_volume": typed.get(known, "L"),
            "unknown_volume": typed.get(other, "L"),
        },
    )


# "it takes 32.45 mL to reach the endpoint", "32.45 mL is required": a volume of no named
# solution, used in reaching the endpoint.
_TITRANT_VOLUME = re.compile(
    rf"\b(?:takes?|took|requires?|required|needs?|needed|uses?|used|consumes?|consumed)\s+"
    rf"({_N})\s*(mL|L)\b(?!\s+of\b)",
    re.IGNORECASE,
)
_ENDPOINT = re.compile(r"\b(?:end\s*point|equivalence\s+point|neutrali[sz]e)", re.IGNORECASE)
_ANY_VOLUME = re.compile(rf"(?<![A-Za-z0-9.]){_N}\s*(?:mL|L)\b")


def _titrant_volume(text: str, owned: int) -> tuple[str, str] | None:
    """The titrant's volume when the question gives it apart from the titrant's name."""
    if not _ENDPOINT.search(text):
        return None
    matches = list(_TITRANT_VOLUME.finditer(text))
    # Every volume of the text is either a named solution's or this one.
    if len(matches) != 1 or len(_ANY_VOLUME.findall(text)) != owned + 1:
        return None
    return matches[0].group(1), matches[0].group(2)


# "What volume of 0.250 M H2SO4 is needed ...", "How many mL of 0.10 M NaOH ...".
_VOLUME_OF_SOLUTION = re.compile(
    r"\b(?:what\s+volume|how\s+many\s+(?:mL|L|milliliters?|liters?))\s+of\s+"
    rf"(?:an?\s+|the\s+)?{_N}\s*M\s+({_SPECIES})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _unknown_volume(
    text: str,
    concentration: dict[str, float],
    volume: dict[str, float],
    typed_unit: dict[str, str],
) -> ChemistryIntent | None:
    """The volume that neutralizes a measured solution: V₂ = C₁V₁ · ratio / C₂.

    The asked solution is the one named by concentration alone, and the question asks its
    volume; the ratio counts protons and hydroxides as the concentration reader does.
    """
    asked = _VOLUME_OF_SOLUTION.search(text)
    if asked is None or not re.search(r"\bneutrali[sz]", text, re.IGNORECASE):
        return None
    other = _species(asked.group(1))
    known = next(iter(volume))
    if other is None or other == known or other not in concentration:
        return None
    acid, base = (known, other) if known in NEUTRALIZING_ACIDS else (other, known)
    if acid not in NEUTRALIZING_ACIDS or base not in NEUTRALIZING_BASES:
        return None
    equivalents = {acid: NEUTRALIZING_ACIDS[acid], base: NEUTRALIZING_BASES[base]}
    return ChemistryIntent(
        kind="acid_base",
        chemistry_op="titration_volume",
        formula=other,
        params={
            "known_concentration": concentration[known],
            "known_volume": volume[known],
            "unknown_concentration": concentration[other],
            "ratio": equivalents[known] / equivalents[other],
        },
        units={"known_volume": typed_unit.get(known, "L")},
    )
