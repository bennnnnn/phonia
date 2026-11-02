# ruff: noqa: RUF002
"""Amounts: moles, mass and particles, formulas from composition, an element's share."""

from __future__ import annotations

import re

from app.modules.chemistry.elements import BY_SYMBOL, ELEMENTS
from app.modules.chemistry.equations import written_is_balanced
from app.modules.chemistry.extractors.parsing import (
    _N,
    _equation,
    _search,
)
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.request import (
    CHEMICAL_FORMULA,
    EQUATION_RE,
    FORMULA_END,
    SAMPLE_FORMULA,
)
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species import DIATOMIC_ELEMENTS
from app.modules.chemistry.species_facts import (
    ELEMENT_NAMES,
    NAMED_COMPOUNDS,
    element_symbol,
    is_formula,
    without_formulas,
)
from app.modules.chemistry.stoichiometry import molar_mass

_PHASE_SUFFIX = re.compile(r"\((?:aq|s|l|g)\)$")


def _bare_formula(label: str) -> str | None:
    """The label without a phase. Charge stays, so ``NH4`` does not name ``NH4+``."""
    bare = _PHASE_SUFFIX.sub("", label)
    return None if bare == label else bare


def _named_outside(text: str, label: str) -> bool:
    outside = EQUATION_RE.sub(" ", text)
    tokens = [label]
    bare = _bare_formula(label)
    if bare is not None:
        tokens.append(bare)
    # A following charge or phase belongs to a different species: KCl is not KCl+,
    # and H2O is not H2O(l).
    pattern = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9+^-]|\((?i:aq|s|l|g)\))"
    return any(re.search(pattern.format(re.escape(token)), outside) for token in tokens)


def _desired_product(text: str, products: dict[str, int]) -> str | None:
    """The one product the question names, or the only product when it names none.

    The returned label is the one written in the equation, phase included.
    """
    mentioned = [product for product in products if _named_outside(text, product)]
    if len(mentioned) == 1:
        return mentioned[0]
    if len(products) == 1:
        return next(iter(products))
    return None


def _extract_atom_economy(text: str) -> ChemistryIntent | None:
    if re.search(r"\batom economy\b", text, re.IGNORECASE) is None:
        return None
    equation = _equation(text)
    if equation is None or not written_is_balanced(equation):
        return None
    from app.modules.chemistry.species import parse_reaction

    reaction = parse_reaction(equation)
    if reaction is None:
        return None
    products = {term.species.label: term.coefficient for term in reaction.products}
    target = _desired_product(text, products)
    if target is None:
        return None
    return ChemistryIntent(
        kind="amounts", chemistry_op="atom_economy", equation=equation, target=target
    )


# "how many oxygen atoms", "how many atoms of oxygen", "how many moles of O atoms": the
# element word counts that element's atoms; "moles of … atoms" asks for an amount.
_MOLES_TO_PARTICLES = re.compile(
    r"(?:how many|calculate|find)?\s*(?:the\s+number\s+of\s+)?"
    r"(?:(?P<amount>moles?)\s+of\s+)?(?:(?P<element>[A-Za-z]+)\s+)?"
    r"(?P<noun>molecules|particles|atoms|formula units)(?:\s+of\s+(?P<element_after>[A-Za-z]+))?"
    rf"\s+(?:are\s+)?(?:there\s+)?(?:in|from)?\s*(?P<moles>{_N})\s*mol(?:e|es)?\s+(?:of\s+)?"
    rf"(?P<formula>{SAMPLE_FORMULA}){FORMULA_END}",
    re.IGNORECASE,
)


def _particles_from_moles(match: re.Match[str]) -> ChemistryIntent | None:
    """N = n Nₐ for whole formula units or every atom; one element's atoms or their moles."""
    noun = match.group("noun").lower()
    moles = float(match.group("moles"))
    formula = match.group("formula")
    word = match.group("element") or match.group("element_after")
    element = None if word is None else element_symbol(word)
    if element is not None:
        atoms = parse_formula(formula)
        count = atoms.get(element, 0)
        if noun != "atoms":
            # "oxygen molecules in O2" are the molecules; "oxygen molecules in CO2" is not a
            # count the formula gives.
            if set(atoms) != {element}:
                return None
            element = None
        elif count == 0:
            return None
        else:
            return ChemistryIntent(
                kind="amounts",
                chemistry_op="element_moles" if match.group("amount") else "element_atoms",
                formula=formula,
                target=element,
                params={"moles": moles, "count": float(count)},
                units={"moles": "mol"},
            )
    if match.group("amount"):
        # "moles of atoms" with no element named is a ratio the question has not fixed.
        return None
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="moles_to_particles",
        params={"moles": moles},
        units={"particle": noun},
        formula=formula,
    )


_MASS_UNITS = {
    "mg": "mg",
    "milligram": "mg",
    "milligrams": "mg",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
}
_MOLES_IN_UNIT = re.compile(
    r"\bhow\s+many\s+(?P<unit>mg|milligrams?|kg|kilograms?)\s+(?:is|are|in|of|does|do)\s+"
    rf"(?P<moles>{_N})\s*mol(?:e|es)?\s+(?:of\s+)?(?P<formula>{SAMPLE_FORMULA}){FORMULA_END}",
    re.IGNORECASE,
)
# "the molar mass of Ca(NO3)2", "the molar mass of glucose": a formula, or a compound's name.
_MOLAR_MASS_OF = re.compile(
    r"(?:molar\s+mass|molecular\s+weight)\s+(?:of\s+)?(?:the\s+)?"
    rf"(?P<formula>{SAMPLE_FORMULA}{FORMULA_END}|"
    + "|".join(rf"\b{re.escape(name)}\b" for name in sorted(NAMED_COMPOUNDS, key=len, reverse=True))
    + ")",
    re.IGNORECASE,
)
# "the percent composition of carbon in CO2", "mass percent of N in NH4NO3": the element first.
_ELEMENT_PERCENT_IN = re.compile(
    rf"(?:percent(?:age)?\s+(?:composition|by\s+mass)|(?:mass\s+)?percent(?:age)?\s+by\s+mass"
    rf"|mass\s+percent(?:age)?)\s+(?:of\s+)?(?P<element>[A-Z][a-z]?|[a-z]+)\s+(?:in|of)\s+"
    rf"(?P<formula>{SAMPLE_FORMULA}){FORMULA_END}",
    re.IGNORECASE,
)
# "What % of Fe2O3 is iron?", "what percentage of CO2 by mass is carbon": the compound first.
# "What % of the atoms in Fe2O3 are iron" counts atoms, not mass, and is not read.
_COMPOUND_PERCENT_IS = re.compile(
    r"\bwhat\s+(?:%|percent(?:age)?)\s+(?:by\s+mass\s+)?of\s+(?:the\s+mass\s+of\s+)?"
    rf"(?P<formula>{SAMPLE_FORMULA}){FORMULA_END}\s+(?:by\s+mass\s+)?is\s+(?:made\s+up\s+of\s+)?"
    r"(?P<element>[A-Z][a-z]?|[a-z]+)(?:\s+by\s+mass)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _percent_composition(text: str) -> ChemistryIntent | None:
    """One element's mass percent in a formula, named by symbol or in words."""
    match = _ELEMENT_PERCENT_IN.search(text) or _COMPOUND_PERCENT_IS.search(text)
    if match is None:
        return None
    word = match.group("element")
    symbol = word if word in BY_SYMBOL else ELEMENT_NAMES.get(word.lower())
    formula = match.group("formula")
    if symbol is None or symbol not in parse_formula(formula):
        return None
    return ChemistryIntent(
        kind="amounts", chemistry_op="percent_composition", target=symbol, formula=formula
    )


def _extract_amounts(text: str) -> ChemistryIntent | None:
    economy = _extract_atom_economy(text)
    if economy is not None:
        return economy
    mass_formula = _MOLAR_MASS_OF.search(text)
    if mass_formula:
        token = mass_formula.group("formula")
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="molar_mass",
            formula=NAMED_COMPOUNDS.get(token.lower(), token),
        )

    composition = _percent_composition(text)
    if composition is not None:
        return composition

    if re.search(r"\bpercent yield\b", text, re.IGNORECASE):
        actual = _search(rf"actual(?:\s+yield)?\s*(?:=|of)?\s*({_N})\s*g", text)
        theoretical = _search(rf"theoretical(?:\s+yield)?\s*(?:=|of)?\s*({_N})\s*g", text)
        if actual is not None and theoretical is not None:
            return ChemistryIntent(
                kind="amounts",
                chemistry_op="percent_yield",
                params={"actual": actual, "theoretical": theoretical},
            )

    mass_to_moles = re.search(
        rf"(?:how many|calculate|find|determine)?\s*(?:the\s+)?moles?\s+"
        rf"(?:are\s+)?(?:in|from|of)?\s*({_N})\s*g(?:rams?)?\s+(?:of\s+)?"
        rf"({SAMPLE_FORMULA}){FORMULA_END}",
        text,
        re.IGNORECASE,
    )
    if mass_to_moles:
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="mass_to_moles",
            params={"mass": float(mass_to_moles.group(1))},
            units={"mass": "g"},
            formula=mass_to_moles.group(2),
        )

    moles_to_mass = re.search(
        rf"(?:mass|grams?)\s+(?:of\s+)?({_N})\s*mol(?:e|es)?\s+(?:of\s+)?"
        rf"({SAMPLE_FORMULA}){FORMULA_END}",
        text,
        re.IGNORECASE,
    )
    if moles_to_mass:
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="moles_to_mass",
            params={"moles": float(moles_to_mass.group(1))},
            units={"moles": "mol"},
            formula=moles_to_mass.group(2),
        )
    # "How many mg is 0.0150 mol of NaOH?": the mass asked in milligrams or kilograms.
    in_unit = _MOLES_IN_UNIT.search(text)
    if in_unit:
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="moles_to_mass",
            params={"moles": float(in_unit.group("moles"))},
            units={"moles": "mol", "answer": _MASS_UNITS[in_unit.group("unit").lower()]},
            formula=in_unit.group("formula"),
        )

    moles_to_particles = _MOLES_TO_PARTICLES.search(text)
    if moles_to_particles:
        return _particles_from_moles(moles_to_particles)

    particles_to_moles = re.search(
        rf"(?:how many|calculate|find)?\s*moles?\s+(?:are\s+)?(?:in|from)?\s*"
        rf"({_N})\s*(?P<noun>molecules|particles|atoms|formula units)\s+(?:of\s+)?"
        rf"({SAMPLE_FORMULA}){FORMULA_END}",
        text,
        re.IGNORECASE,
    )
    if particles_to_moles:
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="particles_to_moles",
            params={"particles": float(particles_to_moles.group(1))},
            units={"particle": particles_to_moles.group("noun").lower()},
            formula=particles_to_moles.group(3),
        )
    return _extract_particle_mass(text)


_PARTICLE_NOUN = r"(?P<noun>atoms?|molecules?|formula\s+units?)"
_NAMED = "|".join(re.escape(name) for name in sorted(NAMED_COMPOUNDS, key=len, reverse=True))
# What the particles are of: a named compound, a formula, or one word (an element's name).
_PARTICLE_SUBSTANCE = (
    rf"(?:the\s+)?(?:element\s+)?(?P<what>{_NAMED}|{SAMPLE_FORMULA}{FORMULA_END}|"
    r"[A-Za-z]+(?![A-Za-z0-9]))"
)
# Only these words may stand between a mass ask and the count it is of: "the mass of",
# "how many grams is", "the mass, in grams, of". "Grams of water form from 3.01e23
# molecules of H2" asks about another substance, so it is not read.
_ASK_TO_COUNT = r"(?:\s*,?\s*(?:in\s+grams|of|in|is|are|do|does|would|will|be)\b)*\s*,?\s*"
_COUNT_TO_MASS = re.compile(
    rf"\b(?:mass|how\s+many\s+(?:grams|g)|grams)\b{_ASK_TO_COUNT}"
    rf"(?P<count>{_N})\s*{_PARTICLE_NOUN}\s+of\s+{_PARTICLE_SUBSTANCE}",
    re.IGNORECASE,
)
_MASS_TO_COUNT = re.compile(
    rf"\b(?:how\s+many|(?:the\s+)?number\s+of)\s+{_PARTICLE_NOUN}\s+(?:are\s+|is\s+)?"
    r"(?:there\s+)?(?:present\s+|contained\s+)?in\s+(?:an?\s+)?"
    rf"(?P<mass>{_N})\s*(?:g|grams?)\s+(?:sample\s+)?of\s+(?:pure\s+)?{_PARTICLE_SUBSTANCE}",
    re.IGNORECASE,
)
_NUMBER = re.compile(_N)


def _particle_substance(noun: str, word: str) -> str | None:
    """The formula a count of particles is of, or None when the words leave it open.

    Atoms are one element's ("atoms of iron"): atoms of O2 or of water are not. Molecules
    and formula units are a compound's, or a diatomic element's ("molecules of oxygen").
    """
    element = element_symbol(word)
    if noun.lower().startswith("atom"):
        return element
    named = NAMED_COMPOUNDS.get(word.lower())
    if named is not None:
        return named
    if element is not None:
        # Elements whose particles are molecules of two atoms: "molecules of oxygen" are O2.
        return f"{element}2" if element in DIATOMIC_ELEMENTS else None
    return word if is_formula(word) else None


def _one_number(text: str) -> bool:
    """The text states one number outside its formulas: the count or the mass read."""
    return len(_NUMBER.findall(without_formulas(text))) == 1


def _extract_particle_mass(text: str) -> ChemistryIntent | None:
    """A particle count to its mass, m = (N / Nₐ)M, or a mass to its count, N = (m / M)Nₐ.

    "The mass of 1.20 × 10^24 atoms of iron", "How many molecules are in 10 g of CO2?". A
    written equation means the count or the mass is a reactant's, so this is stoichiometry
    and not read here, and so is a question that states anything else.
    """
    if EQUATION_RE.search(text) or not _one_number(text):
        return None
    to_mass = _COUNT_TO_MASS.search(text)
    if to_mass is not None:
        noun = to_mass.group("noun")
        formula = _particle_substance(noun, to_mass.group("what"))
        if formula is None:
            return None
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="particles_to_mass",
            params={"particles": float(to_mass.group("count")), "molar_mass": molar_mass(formula)},
            formula=formula,
        )
    to_count = _MASS_TO_COUNT.search(text)
    if to_count is None:
        return None
    noun = " ".join(to_count.group("noun").lower().split())
    word = to_count.group("what")
    formula = _particle_substance(noun, word)
    if formula is None and noun.startswith("atom") and is_formula(word):
        # "How many atoms are in 10 g of CO2?" counts every atom, as a mole question does.
        formula = word
    if formula is None:
        return None
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="mass_to_particles",
        params={"mass": float(to_count.group("mass"))},
        units={"mass": "g", "particle": noun.removesuffix("s") + "s"},
        formula=formula,
    )


def _extract_empirical(text: str) -> ChemistryIntent | None:
    percents = _percents(text)
    if len(percents) < 2:
        return _empirical_from_masses(text)
    if re.search(r"\bmolecular formula\b", text, re.IGNORECASE):
        molar = _search(rf"(?:molar mass|M)\s*=\s*({_N})", text)
        if molar is None:
            return None
        return ChemistryIntent(
            kind="amounts",
            chemistry_op="molecular_formula",
            params={"molar_mass": molar},
            species=percents,
        )
    if re.search(r"\bempirical formula\b", text, re.IGNORECASE):
        return ChemistryIntent(kind="amounts", chemistry_op="empirical_formula", species=percents)
    return None


# "a 2.50 g sample has 1.00 g Ca, 0.300 g C and 1.20 g O": each element's grams.
_ELEMENT_GRAMS = re.compile(rf"({_N})\s*g(?:rams?)?\s+(?:of\s+)?([A-Za-z]+)(?![A-Za-z0-9])")
_SAMPLE_GRAMS = re.compile(
    rf"({_N})\s*g(?:rams?)?\s+(?:sample|of\s+(?:the\s+)?(?:sample|compound))\b"
)


def _empirical_from_masses(text: str) -> ChemistryIntent | None:
    """An empirical formula from each element's mass in a sample.

    Every mass stated is an element's or the sample's, and a stated sample mass must be
    their sum: masses that do not close are another compound's analysis.
    """
    if not _EMPIRICAL_ASK.search(text) or re.search(r"\bmolecular formula\b", text, re.I):
        return None
    masses: dict[str, float] = {}
    for match in _ELEMENT_GRAMS.finditer(text):
        word = match.group(2)
        symbol = word if word in BY_SYMBOL else _ELEMENT_BY_NAME.get(word.lower())
        if symbol is None:
            continue
        if symbol in masses:
            return None
        masses[symbol] = float(match.group(1))
    samples = _SAMPLE_GRAMS.findall(text)
    stated = len(re.findall(rf"{_N}\s*g(?:rams?)?\b", text))
    if len(masses) < 2 or len(samples) > 1 or stated != len(masses) + len(samples):
        return None
    params = {"sample_mass": float(samples[0])} if samples else {}
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="empirical_formula",
        species=masses,
        params=params,
        units={"basis": "g"},
    )


_ELEMENT_BY_NAME = {element.name.lower(): element.symbol for element in ELEMENTS}
_ELEMENT_BY_NAME.update({"aluminium": "Al", "caesium": "Cs", "sulphur": "S"})


def _percents(text: str) -> dict[str, float]:
    """``40% C`` or ``40% carbon`` by element. A word that is no element is skipped."""
    found: dict[str, float] = {}
    for match in re.finditer(rf"({_N})\s*%\s*([A-Za-z]+)(?![A-Za-z])", text):
        word = match.group(2)
        symbol = word if word in BY_SYMBOL else _ELEMENT_BY_NAME.get(word.lower())
        if symbol is not None:
            found[symbol] = float(match.group(1))
    return found


_SPECIES = rf"(?:{'|'.join(re.escape(name) for name in NAMED_COMPOUNDS)}|{CHEMICAL_FORMULA})"


_ELEMENT_IN = re.compile(
    r"\b(?:how\s+many\s+grams\s+of|(?:what|find|calculate|determine)\s+(?:is\s+)?the\s+mass\s+of)"
    r"\s+(?P<element>[A-Za-z]+)\s+(?:(?:is|are)\s+)?(?:there\s+)?(?:present\s+|contained\s+)?"
    rf"in\s+(?:an?\s+)?(?P<mass>{_N})\s*(?:g|grams?)\s+(?:sample\s+)?of\s+(?:the\s+)?"
    rf"(?P<species>{_SPECIES})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _extract_element_mass(text: str) -> ChemistryIntent | None:
    """ "How many grams of oxygen are in 10 g of H2O?": m(O) = m × nA(O) / M(H2O)."""
    match = _ELEMENT_IN.search(text)
    if match is None:
        return None
    element = element_symbol(match.group("element"))
    token = match.group("species")
    formula = NAMED_COMPOUNDS.get(token.lower()) or (token if is_formula(token) else None)
    if element is None or formula is None:
        return None
    count = parse_formula(formula).get(element, 0)
    if count == 0:
        return None
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="element_mass",
        formula=formula,
        target=element,
        params={
            "sample_mass": float(match.group("mass")),
            "count": float(count),
            "atomic_mass": BY_SYMBOL[element].mass,
            "molar_mass": molar_mass(formula),
        },
    )


_COMBUSTION = re.compile(r"\b(?:combustion|burned|burnt)\b", re.IGNORECASE)
_EMPIRICAL_ASK = re.compile(r"\bempirical formula\b", re.IGNORECASE)
_FOREIGN_ELEMENT = re.compile(
    r"\b(?:nitrogen|sulfur|sulphur|phosphorus|chlorine|bromine|iodine|fluorine)\b",
    re.IGNORECASE,
)
_CHO = re.compile(
    r"carbon\s*,\s*hydrogen\s*,?\s*(?:and\s+)?oxygen|\bC\s*,\s*H\s*,?\s*(?:and\s+)?O\b",
    re.IGNORECASE,
)
_HYDROCARBON = re.compile(r"\bonly\s+carbon\s+and\s+hydrogen\b", re.IGNORECASE)


def _grams_of(text: str, name: str) -> float | None:
    match = re.search(
        rf"({_N})\s*g(?:rams?)?\s+(?:of\s+)?(?:the\s+)?(?:{name})\b",
        text,
        re.IGNORECASE,
    )
    return None if match is None else float(match.group(1))


def _extract_combustion(text: str) -> ChemistryIntent | None:
    """C/H/O combustion masses to an empirical formula. Another element is not this op."""
    if _COMBUSTION.search(text) is None or _EMPIRICAL_ASK.search(text) is None:
        return None
    if _FOREIGN_ELEMENT.search(text) is not None:
        return None
    hydrocarbon = _HYDROCARBON.search(text) is not None and _CHO.search(text) is None
    if not hydrocarbon and _CHO.search(text) is None:
        return None
    sample = _grams_of(text, "sample")
    co2 = _grams_of(text, "CO2|carbon dioxide")
    water = _grams_of(text, "H2O|water")
    if sample is None or co2 is None or water is None:
        return None
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="combustion_analysis",
        target="CH" if hydrocarbon else None,
        params={"sample_mass": sample, "co2_mass": co2, "h2o_mass": water},
    )


_HYDRATE_ASK = re.compile(
    r"\bwaters?\s+of\s+hydration\b|\bwater\s+of\s+crystallization\b|\bhow\s+many\s+waters\b",
    re.IGNORECASE,
)


def _extract_hydrate(text: str) -> ChemistryIntent | None:
    """n in salt·nH2O from the hydrate mass, the anhydrous mass, and the salt formula."""
    if re.search(r"\bhydrate\b", text, re.IGNORECASE) is None or _HYDRATE_ASK.search(text) is None:
        return None
    formulas = {
        match.group(1)
        for match in re.finditer(
            rf"\b(?:anhydrous|hydrate of)\s+({CHEMICAL_FORMULA})(?![A-Za-z0-9])",
            text,
        )
        if match.group(1) != "H2O" and parse_formula(match.group(1))
    }
    if len(formulas) != 1:
        return None
    formula = next(iter(formulas))
    hydrate = _grams_of(text, "sample|hydrate")
    anhydrous = _grams_of(text, "anhydrous")
    if hydrate is None or anhydrous is None:
        return None
    return ChemistryIntent(
        kind="amounts",
        chemistry_op="hydrate_water",
        formula=formula,
        params={"hydrate_mass": hydrate, "anhydrous_mass": anhydrous},
    )
