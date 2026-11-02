"""Construct one half-reaction from a written redox pair and its medium.

Water, H+ or OH-, and electrons may be added. Several species on a side are a
different equation and are not completed here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from math import gcd

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.equations import written_is_balanced
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import ChemicalSpecies, canonical_label, parse_reaction
from app.modules.chemistry.structure import oxidation_states
from app.services.solving import SolveServiceError

_ADDED = ("H2O", "H+", "OH-", "e-")


@dataclass(frozen=True)
class _Built:
    equation: str
    element: str
    electrons: int


def solve_half_reaction(intent: ChemistryIntent) -> ChemistryResult:
    equation = intent.equation or ""
    medium = intent.target
    if medium not in {"acidic", "basic"}:
        raise SolveServiceError("a half-reaction needs an acidic or basic medium")
    pair = _pair(equation)
    if pair is None:
        raise SolveServiceError("a half-reaction needs one species on each side")
    built = _construct(*pair, medium)
    if not written_is_balanced(built.equation):
        raise SolveServiceError("the half-reaction did not balance")
    left, right = pair
    return verified(
        "Verified half-reaction",
        (
            f"Pair: {canonical_label(left)} -> {canonical_label(right)}",
            f"Medium: {medium}",
        ),
        "Balanced half-reaction",
        *stated("half_reaction"),
        (
            f"the oxidation number of {built.element} changes",
            f"add H2O, then {'OH-' if medium == 'basic' else 'H+'}, then {built.electrons} e-",
        ),
        built.equation,
        built.equation,
    )


def _pair(equation: str) -> tuple[ChemicalSpecies, ChemicalSpecies] | None:
    reaction = parse_reaction(equation)
    if reaction is None or len(reaction.reactants) != 1 or len(reaction.products) != 1:
        return None
    left = replace(reaction.reactants[0].species, phase=None)
    right = replace(reaction.products[0].species, phase=None)
    if left.electron or right.electron:
        return None
    return left, right


def _construct(left: ChemicalSpecies, right: ChemicalSpecies, medium: str) -> _Built:
    element, left_count, right_count = _redox_element(left, right)
    divisor = gcd(left_count, right_count)
    reactant_coefficient = right_count // divisor
    product_coefficient = left_count // divisor
    reactants = {canonical_label(left): reactant_coefficient}
    products = {canonical_label(right): product_coefficient}
    _balance_oxygen(left, right, reactant_coefficient, product_coefficient, reactants, products)
    _balance_hydrogen(left, right, reactant_coefficient, product_coefficient, reactants, products)
    electrons = _balance_charge(
        left, right, reactant_coefficient, product_coefficient, reactants, products
    )
    if medium == "basic":
        _to_basic(reactants, products)
    _cancel_water(reactants, products, left, right)
    return _Built(
        f"{_side(reactants, canonical_label(left))} -> {_side(products, canonical_label(right))}",
        element,
        electrons,
    )


def is_single_redox_change(left: ChemicalSpecies, right: ChemicalSpecies) -> bool | None:
    """True when one element changes oxidation number.

    False when those numbers are known and none change, so the ordinary balancer
    can keep the equation. None when the numbers are ambiguous.
    """
    changed = _changed_elements(left, right)
    if changed is None:
        return None
    if not changed:
        return False
    if len(changed) == 1:
        return True
    return None


def _redox_element(left: ChemicalSpecies, right: ChemicalSpecies) -> tuple[str, int, int]:
    left_states = _state_map(left)
    right_states = _state_map(right)
    if left_states is None or right_states is None:
        raise SolveServiceError("oxidation states are ambiguous")
    shared = set(left.composition) & set(right.composition)
    extras = (set(left.composition) | set(right.composition)) - shared - {"H", "O"}
    if extras:
        raise SolveServiceError("an element in the pair is not on both sides")
    changed = [element for element in shared if left_states[element] != right_states[element]]
    if len(changed) != 1:
        raise SolveServiceError("the pair is not one redox change")
    element = changed[0]
    return element, left.composition[element], right.composition[element]


def _changed_elements(left: ChemicalSpecies, right: ChemicalSpecies) -> list[str] | None:
    left_states = _state_map(left)
    right_states = _state_map(right)
    if left_states is None or right_states is None:
        return None
    shared = set(left.composition) & set(right.composition)
    extras = (set(left.composition) | set(right.composition)) - shared - {"H", "O"}
    if extras:
        return None
    return [element for element in shared if left_states[element] != right_states[element]]


def _state_map(species: ChemicalSpecies) -> dict[str, Fraction] | None:
    """Oxidation numbers, including a fractional average for one element."""
    known = oxidation_states(canonical_label(species))
    if known is not None:
        return {element: Fraction(state) for element, state in known.items()}
    if len(species.composition) != 1:
        return None
    element, count = next(iter(species.composition.items()))
    if count == 0:
        return None
    return {element: Fraction(species.charge, count)}


def _balance_oxygen(
    left: ChemicalSpecies,
    right: ChemicalSpecies,
    reactant_coefficient: int,
    product_coefficient: int,
    reactants: dict[str, int],
    products: dict[str, int],
) -> None:
    oxygen_left = reactant_coefficient * left.composition.get("O", 0)
    oxygen_right = product_coefficient * right.composition.get("O", 0)
    # The difference is water still needed. Add it to a pair that is already water.
    if oxygen_left > oxygen_right:
        products["H2O"] = products.get("H2O", 0) + (oxygen_left - oxygen_right)
    elif oxygen_right > oxygen_left:
        reactants["H2O"] = reactants.get("H2O", 0) + (oxygen_right - oxygen_left)


def _balance_hydrogen(
    left: ChemicalSpecies,
    right: ChemicalSpecies,
    reactant_coefficient: int,
    product_coefficient: int,
    reactants: dict[str, int],
    products: dict[str, int],
) -> None:
    hydrogen_left = reactant_coefficient * left.composition.get("H", 0) + 2 * _extra(
        reactants, "H2O", canonical_label(left), reactant_coefficient
    )
    hydrogen_right = product_coefficient * right.composition.get("H", 0) + 2 * _extra(
        products, "H2O", canonical_label(right), product_coefficient
    )
    # The difference is protons still needed. Add them when the pair itself is H+.
    if hydrogen_right > hydrogen_left:
        reactants["H+"] = reactants.get("H+", 0) + (hydrogen_right - hydrogen_left)
    elif hydrogen_left > hydrogen_right:
        products["H+"] = products.get("H+", 0) + (hydrogen_left - hydrogen_right)


def _balance_charge(
    left: ChemicalSpecies,
    right: ChemicalSpecies,
    reactant_coefficient: int,
    product_coefficient: int,
    reactants: dict[str, int],
    products: dict[str, int],
) -> int:
    charge_left = reactant_coefficient * left.charge + _extra(
        reactants, "H+", canonical_label(left), reactant_coefficient
    )
    charge_right = product_coefficient * right.charge + _extra(
        products, "H+", canonical_label(right), product_coefficient
    )
    electrons = charge_left - charge_right
    if electrons > 0:
        reactants["e-"] = electrons
    elif electrons < 0:
        products["e-"] = -electrons
    else:
        raise SolveServiceError("the pair does not transfer electrons")
    return abs(electrons)


def _extra(counts: dict[str, int], label: str, primary: str, coefficient: int) -> int:
    """Ions added for balance, excluding a pair species that already uses that label."""
    total = counts.get(label, 0)
    if label == primary:
        return total - coefficient
    return total


def _to_basic(reactants: dict[str, int], products: dict[str, int]) -> None:
    """Replace H+ with water and hydroxide, then cancel water that appears twice."""
    protons_left = reactants.pop("H+", 0)
    protons_right = products.pop("H+", 0)
    if protons_left:
        reactants["H2O"] = reactants.get("H2O", 0) + protons_left
        products["OH-"] = products.get("OH-", 0) + protons_left
    elif protons_right:
        products["H2O"] = products.get("H2O", 0) + protons_right
        reactants["OH-"] = reactants.get("OH-", 0) + protons_right


def _cancel_water(
    reactants: dict[str, int],
    products: dict[str, int],
    left: ChemicalSpecies,
    right: ChemicalSpecies,
) -> None:
    """Drop water that the pair and the oxygen balance both introduced.

    Cancelling the written water when the other species has no oxygen leaves a
    different pair, such as H+ -> H2 in place of H2O -> H2.
    """
    cancel = min(reactants.get("H2O", 0), products.get("H2O", 0))
    if cancel == 0:
        return
    left_label = canonical_label(left)
    right_label = canonical_label(right)
    erases_left = left_label == "H2O" and reactants.get("H2O", 0) <= cancel
    erases_right = right_label == "H2O" and products.get("H2O", 0) <= cancel
    if (erases_left and right.composition.get("O", 0) == 0) or (
        erases_right and left.composition.get("O", 0) == 0
    ):
        raise SolveServiceError("the written water cancels")
    reactants["H2O"] -= cancel
    products["H2O"] -= cancel


def _side(counts: dict[str, int], primary: str) -> str:
    ordered = (primary, *(label for label in _ADDED if label != primary))
    labels = [label for label in ordered if counts.get(label, 0) > 0]
    return " + ".join(
        label if counts[label] == 1 else f"{counts[label]} {label}" for label in labels
    )
