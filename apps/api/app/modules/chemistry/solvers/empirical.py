"""Empirical and molecular formulas from percent composition."""

from __future__ import annotations

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.formula import hill_formula, parse_formula
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import (
    atomic_mass,
    inp,
    molar_mass_working,
    num,
    verified,
)
from app.modules.chemistry.solvers.params import require
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.stoichiometry import (
    formula_atoms,
    molar_mass,
)
from app.services.solving import SolveServiceError


def _written_order(counts: dict[str, int]) -> str:
    """A carbon-hydrogen compound in Hill order (CH3); a salt as the question names its
    elements, cation first: 1.00 g Ca, 0.300 g C and 1.20 g O is CaCO3, not CCaO3."""
    if "C" in counts and "H" in counts:
        return hill_formula(counts)
    return "".join(f"{element}{'' if count == 1 else count}" for element, count in counts.items())


def _integer_ratio(ratios: dict[str, float]) -> dict[str, int] | None:
    for multiplier in range(1, 9):
        scaled = {element: ratio * multiplier for element, ratio in ratios.items()}
        if all(abs(value - round(value)) <= 0.1 for value in scaled.values()):
            return {element: round(value) for element, value in scaled.items()}
    return None


def _empirical_counts(
    percents: dict[str, float], *, grams: bool = False
) -> tuple[dict[str, int], list[str]]:
    """Integer atom ratio and the per-element working (grams → moles → ratio).

    ``grams`` reads the values as each element's mass in a sample, not as percentages.
    """
    if not percents or any(value <= 0 for value in percents.values()):
        raise SolveServiceError("percent composition must be positive")
    if not grams and abs(sum(percents.values()) - 100) > 1.5:
        raise SolveServiceError("percentages must add to about 100")
    masses: dict[str, float] = {}
    moles: dict[str, float] = {}
    for element, percent in percents.items():
        info = BY_SYMBOL.get(element)
        if info is None:
            raise SolveServiceError(f"unknown element {element}")
        masses[element] = info.mass
        moles[element] = percent / masses[element]
    smallest = min(moles.values())
    ratios = {element: value / smallest for element, value in moles.items()}
    counts = _integer_ratio(ratios)
    if counts is None:
        raise SolveServiceError("percentages do not form a simple integer ratio")
    working = [
        f"{element}: {inp(percents[element])} g / {atomic_mass(masses[element])} g/mol = "
        f"{num(moles[element])} mol; / {num(smallest)} = {num(ratios[element])}"
        f" -> {counts[element]}"
        for element in percents
    ]
    return counts, working


# A milligram-scale balance plus table rounding. More than this and the masses do not close.
_CLOSURE_GRAMS = 0.002


def solve_combustion(intent: ChemistryIntent) -> ChemistryResult:
    """Empirical formula of a C/H/O compound from the sample, CO2, and H2O masses."""
    sample = require(intent, "sample_mass", positive=True)
    co2 = require(intent, "co2_mass", positive=True)
    water = require(intent, "h2o_mass", positive=True)
    carbon = molar_mass("C")
    hydrogen = molar_mass("H")
    oxygen = molar_mass("O")
    co2_mass = molar_mass("CO2")
    water_mass = molar_mass("H2O")
    moles_c = co2 / co2_mass
    moles_h = 2 * water / water_mass
    mass_c = moles_c * carbon
    mass_h = moles_h * hydrogen
    mass_o = sample - mass_c - mass_h
    hydrocarbon = intent.target == "CH"
    if mass_o < -_CLOSURE_GRAMS or (hydrocarbon and mass_o > _CLOSURE_GRAMS):
        raise SolveServiceError("the combustion masses do not close")
    moles = {"C": moles_c, "H": moles_h}
    if mass_o > _CLOSURE_GRAMS:
        moles["O"] = mass_o / oxygen
    ratios = {element: value / min(moles.values()) for element, value in moles.items()}
    counts = _integer_ratio(ratios)
    if counts is None:
        raise SolveServiceError("the combustion masses do not form a simple integer ratio")
    formula = hill_formula(counts)
    working = [
        f"n(C) = {inp(co2)} / {molar_mass_working(co2_mass)} = {num(moles_c)} mol",
        f"n(H) = 2 * {inp(water)} / {molar_mass_working(water_mass)} = {num(moles_h)} mol",
    ]
    if "O" in moles:
        working.append(f"m(O) = {inp(sample)} - {num(mass_c)} - {num(mass_h)} = {num(mass_o)} g")
        working.append(
            f"n(O) = {num(mass_o)} / {molar_mass_working(oxygen)} = {num(moles['O'])} mol"
        )
    else:
        working.append("the sample mass is the carbon and hydrogen, so there is no oxygen")
    ratio = ", ".join(
        f"{element} {counts[element]}" for element in ("C", "H", "O") if element in counts
    )
    working.append(f"{ratio} -> {formula}")
    return verified(
        "Verified combustion analysis",
        (f"sample = {inp(sample)} g", f"CO2 = {inp(co2)} g", f"H2O = {inp(water)} g"),
        "Empirical formula",
        *stated("combustion_analysis"),
        working,
        formula,
        formula,
    )


_WATER_COEFFICIENT_TOLERANCE = 0.05


def solve_hydrate(intent: ChemistryIntent) -> ChemistryResult:
    """Water coefficient of salt·nH2O from the hydrate mass, anhydrous mass, and salt formula."""
    hydrate = require(intent, "hydrate_mass", positive=True)
    anhydrous = require(intent, "anhydrous_mass", positive=True)
    formula = intent.formula
    if not formula or not parse_formula(formula):
        raise SolveServiceError("a hydrate needs the anhydrous formula")
    if anhydrous >= hydrate:
        raise SolveServiceError("the anhydrous mass must be less than the hydrate mass")
    salt = molar_mass(formula)
    water = molar_mass("H2O")
    water_mass = hydrate - anhydrous
    coefficient = (water_mass / water) / (anhydrous / salt)
    nearest = round(coefficient)
    if nearest < 1 or abs(coefficient - nearest) > _WATER_COEFFICIENT_TOLERANCE:
        raise SolveServiceError("the water coefficient is not a small integer")
    shown = formula if nearest == 1 else f"{formula}\u00b7{nearest}H2O"
    return verified(
        "Verified hydrate",
        (
            f"hydrate = {inp(hydrate)} g",
            f"anhydrous {formula} = {inp(anhydrous)} g",
        ),
        "Waters of hydration",
        *stated("hydrate_water"),
        (
            f"m(H2O) = {inp(hydrate)} - {inp(anhydrous)} = {num(water_mass)} g",
            f"n = ({num(water_mass)} / {molar_mass_working(water)})"
            f" / ({inp(anhydrous)} / {molar_mass_working(salt)}) = {nearest}",
        ),
        shown,
        shown,
    )


# Element masses must add up to the stated sample mass within this share of it.
_SAMPLE_CLOSURE = 0.01


def solve_empirical(intent: ChemistryIntent) -> ChemistryResult:
    grams = intent.units.get("basis") == "g"
    counts, working = _empirical_counts(dict(intent.species), grams=grams)
    formula = hill_formula(counts)
    if grams:
        formula = _written_order(counts)
        sample = intent.params.get("sample_mass")
        total = sum(intent.species.values())
        if sample is not None and abs(total - sample) > _SAMPLE_CLOSURE * sample:
            raise SolveServiceError("the element masses do not add up to the sample mass")
        given: tuple[str, ...] = tuple(
            f"{element} = {inp(mass)} g" for element, mass in intent.species.items()
        )
        if sample is not None:
            given = (*given, f"sample = {inp(sample)} g")
        return verified(
            "Verified empirical formula",
            given,
            "Empirical formula",
            *stated("empirical_formula"),
            working,
            formula,
            formula,
        )
    given = tuple(f"{element} = {inp(percent)}%" for element, percent in intent.species.items())
    return verified(
        "Verified empirical formula",
        (*given, "assume a 100 g sample, so each percent is grams"),
        "Empirical formula",
        *stated("empirical_formula"),
        working,
        formula,
        formula,
    )


def solve_molecular(intent: ChemistryIntent) -> ChemistryResult:
    molar = intent.params.get("molar_mass")
    if molar is None or molar <= 0:
        raise SolveServiceError("molecular molar mass must be positive")
    if intent.species:
        counts, working = _empirical_counts(dict(intent.species))
        given = [f"{element} = {inp(percent)}%" for element, percent in intent.species.items()]
    elif intent.formula and (stated_counts := formula_atoms(intent.formula)):
        # The empirical formula may be given outright: "the empirical formula is CH2O".
        counts, working = dict(stated_counts), []
        given = [f"empirical formula = {intent.formula}"]
    else:
        raise SolveServiceError("a molecular formula needs a composition or an empirical formula")
    empirical = hill_formula(counts)
    empirical_mass = molar_mass(empirical)
    multiple = molar / empirical_mass
    factor = round(multiple)
    if factor < 1 or abs(multiple - factor) > 0.05:
        raise SolveServiceError("molar mass is not an integer multiple of the empirical mass")
    molecular_counts = {element: count * factor for element, count in counts.items()}
    formula = hill_formula(molecular_counts)
    return verified(
        "Verified molecular formula",
        (*given, f"M = {inp(molar)} g/mol"),
        "Molecular formula",
        *stated("molecular_formula"),
        (
            *working,
            f"empirical formula = {empirical}, M = {molar_mass_working(empirical_mass)} g/mol",
            f"n = {inp(molar)} / {molar_mass_working(empirical_mass)} = {factor}",
            f"molecular formula = ({empirical}){factor} = {formula}",
        ),
        formula,
        formula,
    )
