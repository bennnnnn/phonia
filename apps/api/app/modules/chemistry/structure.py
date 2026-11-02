"""School oxidation states.

The assignment order returns None when more than one element is still unknown.
"""

from __future__ import annotations

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.lewis import LewisStructure, lewis_structure
from app.modules.chemistry.species import parse_species

__all__ = ["LewisStructure", "lewis_structure", "oxidation_states"]

# H is minus one only next to elements clearly less electronegative than it (metals, B, Si,
# Ge): NaBH4 and B2H6 have hydride, while PH3, AsH3 and H2Te keep the textbook plus one on H.
_NONMETALS = frozenset({"C", "N", "O", "F", "P", "S", "Cl", "As", "Se", "Br", "Sb", "Te", "I"})
_HALOGENS = frozenset({"Cl", "Br", "I"})
# Common polyatomic ions, tried only after the element rules leave several unknowns.
_POLYATOMIC: tuple[tuple[dict[str, int], int], ...] = (
    ({"S": 1, "O": 4}, -2),
    ({"P": 1, "O": 4}, -3),
    ({"C": 1, "O": 3}, -2),
    ({"N": 1, "O": 3}, -1),
    ({"S": 1, "O": 3}, -2),
    ({"N": 1, "O": 2}, -1),
    ({"C": 1, "N": 1}, -1),
    ({"O": 1, "H": 1}, -1),
    ({"N": 1, "H": 4}, 1),
)


def _consume(composition: dict[str, int], atoms: dict[str, int]) -> dict[str, int] | None:
    left = dict(composition)
    for element, count in atoms.items():
        if left.get(element, 0) < count:
            return None
        left[element] -= count
        if left[element] == 0:
            del left[element]
    return left


def oxidation_states(formula: str) -> dict[str, int] | None:
    """School oxidation numbers, or None when the rules do not decide."""
    species = parse_species(formula, coefficient_already_removed=True)
    if species is None or species.electron:
        return None
    composition = species.composition
    charge = species.charge
    if len(composition) == 1:
        element, count = next(iter(composition.items()))
        if count == 0 or charge % count != 0:
            return None
        return {element: charge // count}

    assigned: dict[str, int] = {}
    if "F" in composition:
        assigned["F"] = -1
    for element in composition:
        group = BY_SYMBOL[element].group
        if element != "H" and group == 1:
            assigned[element] = 1
        elif group == 2:
            assigned[element] = 2
    if "H" in composition:
        others = [element for element in composition if element != "H"]
        assigned["H"] = -1 if others and all(element not in _NONMETALS for element in others) else 1

    def unassigned() -> list[str]:
        return [element for element in composition if element not in assigned]

    if "O" in unassigned() and len(unassigned()) > 1:
        assigned["O"] = -2
    if "O" not in composition and "F" not in composition:
        # Only the most electronegative halogen is minus one: in ICl it is Cl, not whichever
        # element the formula happens to list first.
        halogens = sorted(
            (element for element in unassigned() if element in _HALOGENS),
            key=lambda element: BY_SYMBOL[element].electronegativity or 0.0,
            reverse=True,
        )
        if halogens and len(unassigned()) > 1:
            assigned[halogens[0]] = -1
    remaining = unassigned()
    if len(remaining) > 1:
        return _polyatomic_oxidation(composition, charge)
    if len(remaining) == 1:
        element = remaining[0]
        known = sum(assigned[item] * composition[item] for item in assigned)
        rest = charge - known
        if composition[element] == 0 or rest % composition[element] != 0:
            return None
        assigned[element] = rest // composition[element]
    known = sum(assigned[element] * composition[element] for element in composition)
    if set(assigned) != set(composition) or known != charge:
        return None
    if any(state > _highest_state(element) for element, state in assigned.items()):
        # S2O8²⁻ would give S +7 and CrO5 Cr +10 because the peroxo O is minus one, not minus two.
        return None
    return assigned


def _highest_state(element: str) -> int:
    """Largest oxidation number the group allows; f-block elements are not bounded."""
    group = BY_SYMBOL[element].group
    if group is None:
        return 99
    return group if group <= 12 else group - 10


def _polyatomic_oxidation(composition: dict[str, int], charge: int) -> dict[str, int] | None:
    """Assign a known ion, then the one element left outside it."""
    for atoms, poly_charge in _POLYATOMIC:
        if any(composition.get(element, 0) != count for element, count in atoms.items()):
            continue
        left = _consume(composition, atoms)
        if left is None or len(left) != 1:
            continue
        element, count = next(iter(left.items()))
        rest = charge - poly_charge
        if count == 0 or rest % count != 0:
            continue
        body = "".join(
            symbol if atom_count == 1 else f"{symbol}{atom_count}"
            for symbol, atom_count in atoms.items()
        )
        sign = "+" if poly_charge > 0 else "-"
        magnitude = abs(poly_charge)
        ion = f"{body}{sign}" if magnitude == 1 else f"{body}^{magnitude}{sign}"
        inner = oxidation_states(ion)
        if inner is None:
            continue
        return {element: rest // count, **inner}
    return None
