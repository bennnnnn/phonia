"""Stoichiometry, molar mass, and periodic-table helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.smiles import (
    element_counts,
    most_common_isotope,
    parse_mol,
    validate_smiles,
)

__all__ = [
    "LimitingReagentResult",
    "StoichiometryResult",
    "formula_atoms",
    "limiting_reagent",
    "molar_mass",
    "monoisotopic_mass",
    "stoichiometry",
]


@dataclass(frozen=True)
class StoichiometryResult:
    """Result of a stoichiometry calculation."""

    answer: str  # human-readable answer
    limiting_reagent: str | None = None
    product_amount: float | None = None
    error: str | None = None


def stoichiometry(
    equation: str,
    known_reactant: str,
    known_amount: float,
    target_product: str | None = None,
) -> StoichiometryResult:
    """Calculate product yield from a balanced equation and known reactant amount.

    If target_product is None, uses the first product.
    """
    balanced = balance_equation(equation)
    if not balanced.balanced:
        return StoichiometryResult("", error=balanced.error)

    if known_reactant not in balanced.reactants:
        return StoichiometryResult("", error=f"{known_reactant} not found in reactants")

    reactant_coeff = balanced.reactants[known_reactant]

    if target_product is None:
        target_product = next(iter(balanced.products))
    if target_product not in balanced.products:
        return StoichiometryResult("", error=f"{target_product} not found in products")

    product_coeff = balanced.products[target_product]
    # Mole ratio: product_coeff / reactant_coeff
    product_amount = known_amount * product_coeff / reactant_coeff
    answer = (
        f"{known_amount} mol {known_reactant} produces {product_amount:.4g} mol {target_product}"
    )
    return StoichiometryResult(
        answer=answer,
        product_amount=product_amount,
    )


_SMILES_ONLY_CHARS = frozenset("=#[@]")


def _mass_from_hill(atoms: dict[str, int]) -> float | None:
    """Sum atomic masses. None when any symbol is missing from the table."""
    total = 0.0
    for elem, count in atoms.items():
        element = BY_SYMBOL.get(elem)
        if element is None:
            return None
        total += element.mass * count
    # Full precision: a molar mass is rounded where it is shown, never before the arithmetic
    # (4 g of H2 is 1.984 mol, not 4 / 2.02 = 1.980).
    return total


def _closed_ring_smiles(raw: str) -> bool:
    """True when digits pair up as ring closures (``C1CCCCC1``) in a valid SMILES.

    A Hill parse would read those digits as atom counts and drop the hydrogens
    (cyclohexane as C6, 72.07 instead of 84.16). Hill formulas such as ``C6H12O6`` or
    ``CO2`` are never valid SMILES, so they still take the formula route.
    """
    if not any(ch.isdigit() for ch in raw):
        return False
    return parse_mol(raw, map_formulas=False) is not None


def _prefer_smiles(raw: str) -> bool:
    """True for organic SMILES that a Hill parse would misread (``CCO`` → C₂O)."""
    if any(ch in _SMILES_ONLY_CHARS for ch in raw):
        return True
    if _closed_ring_smiles(raw):
        return True
    letters = sum(1 for ch in raw if ch.isalpha())
    if letters >= 3 and not any(ch.isdigit() for ch in raw):
        atoms = parse_formula(raw)
        if atoms and all(len(elem) == 1 for elem in atoms):
            return True
    return False


def formula_atoms(formula_or_smiles: str) -> dict[str, int] | None:
    """Element counts behind :func:`molar_mass`, including SMILES hydrogens.

    A Hill parse of ``CCO`` is C₂O and drops the six hydrogens RDKit counts.
    A substitution or an atom tally has to use this, not ``parse_formula`` alone,
    or the printed working will not add up to the mass.
    """
    cleaned = formula_or_smiles.strip()
    if not cleaned:
        return None
    hill_atoms = parse_formula(cleaned)
    if hill_atoms and not _prefer_smiles(cleaned):
        return hill_atoms
    counted = element_counts(cleaned)
    if counted:
        return counted
    return hill_atoms or None


def molar_mass(formula_or_smiles: str) -> float:
    """Calculate the molar mass of a compound from its formula or SMILES.

    Hill formulas (``CO``, ``C``, ``H2O``) are summed from the element table so
    RDKit cannot saturate them into hydrides (methanol / methane). Organic
    SMILES such as ``CCO`` still go through RDKit.
    """
    cleaned = formula_or_smiles.strip()
    if not cleaned:
        raise ValueError("cannot compute molar mass for empty string")

    hill_atoms = parse_formula(cleaned)
    if hill_atoms and not _prefer_smiles(cleaned):
        mass = _mass_from_hill(hill_atoms)
        if mass is not None:
            return mass

    props = validate_smiles(cleaned)
    if props.valid:
        return props.molecular_weight

    if hill_atoms:
        mass = _mass_from_hill(hill_atoms)
        if mass is not None:
            return mass
    raise ValueError(f"cannot compute molar mass for {formula_or_smiles}")


@dataclass(frozen=True)
class MonoisotopicMass:
    """The mass-spectrometry molecular ion: every atom its most abundant isotope."""

    exact: float
    nominal: int
    counts: dict[str, int]


def monoisotopic_mass(formula_or_smiles: str) -> MonoisotopicMass:
    """Exact and nominal mass of the most abundant isotopologue (M+ in a mass spectrum)."""
    cleaned = formula_or_smiles.strip()
    if not cleaned:
        raise ValueError("cannot compute a mass for empty string")
    hill_atoms = parse_formula(cleaned)
    counts: dict[str, int] | None = None
    if hill_atoms and not _prefer_smiles(cleaned):
        counts = hill_atoms
    if counts is None:
        counts = element_counts(cleaned) or hill_atoms or None
    if not counts:
        raise ValueError(f"cannot compute a mass for {formula_or_smiles}")
    exact = 0.0
    nominal = 0
    for symbol, count in counts.items():
        isotope = most_common_isotope(symbol)
        if isotope is None:
            raise ValueError(f"no isotope data for {symbol}")
        exact += isotope[0] * count
        nominal += isotope[1] * count
    return MonoisotopicMass(exact, nominal, dict(counts))


@dataclass(frozen=True)
class LimitingReagentResult:
    """Result of a limiting reagent calculation."""

    answer: str
    limiting_reagent: str | None = None
    product_amount: float | None = None
    error: str | None = None
    tied: tuple[str, ...] = ()  # other reactants that run out at exactly the same time


def limiting_reagent(
    equation: str,
    reactant_amounts: dict[str, float],
    target_product: str | None = None,
) -> LimitingReagentResult:
    """Determine the limiting reagent and product yield.

    reactant_amounts maps formula → moles available. Every reactant must have an
    amount: leaving one out would make another look limiting.
    """
    balanced = balance_equation(equation)
    if not balanced.balanced:
        return LimitingReagentResult(answer="", error=balanced.error)

    if target_product is None:
        target_product = next(iter(balanced.products))
    if target_product not in balanced.products:
        return LimitingReagentResult(answer="", error=f"{target_product} not found in products")
    for reactant in reactant_amounts:
        if reactant not in balanced.reactants:
            return LimitingReagentResult(answer="", error=f"{reactant} not found in reactants")
    missing = [name for name in balanced.reactants if name not in reactant_amounts]
    if missing:
        return LimitingReagentResult(
            answer="", error=f"an amount is needed for every reactant, missing {missing[0]}"
        )

    product_coeff = balanced.products[target_product]
    # For each reactant, compute how much product it could make.
    yields = {
        reactant: amount * product_coeff / balanced.reactants[reactant]
        for reactant, amount in reactant_amounts.items()
    }
    smallest = min(yields.values())
    limiting = [name for name, value in yields.items() if math.isclose(value, smallest)]
    best_reactant, *tied = limiting
    return LimitingReagentResult(
        answer=(
            f"Limiting reagent: {best_reactant}. Product ({target_product}): {smallest:.4g} mol"
        ),
        limiting_reagent=best_reactant,
        product_amount=smallest,
        tied=tuple(tied),
    )
