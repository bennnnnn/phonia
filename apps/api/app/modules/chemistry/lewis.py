"""Bounded single-center Lewis structures and VSEPR shapes.

A single carbon may be the center when the other non-hydrogen atoms are
terminal nonmetals (HCN). Expanded octets are allowed from period 3 onward,
and only when they lower the formal-charge total. The molecular angle is not
the ideal electron-domain angle once a lone pair is present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.modules.chemistry.elements import BY_SYMBOL, valence_electrons
from app.modules.chemistry.species import ChemicalSpecies, parse_species

# Electron-domain geometry and its ideal angle, keyed by steric number.
_ELECTRON_GEOMETRY = {
    2: ("linear", "180°"),
    3: ("trigonal planar", "120°"),
    4: ("tetrahedral", "109.5°"),
    5: ("trigonal bipyramidal", "90° and 120°"),
    6: ("octahedral", "90°"),
}
# Molecular shape and the school approximate bond angle. Lone pairs compress
# the ideal angle; water and ammonia use the usual textbook values, and the
# other lone-pair shapes stay "less than" the ideal angle instead of a fake
# single measurement.
_MOLECULAR_GEOMETRY: dict[tuple[int, int], tuple[str, str]] = {
    (2, 0): ("linear", "180°"),
    (3, 0): ("trigonal planar", "120°"),
    (3, 1): ("bent", "less than 120°"),
    (4, 0): ("tetrahedral", "109.5°"),
    (4, 1): ("trigonal pyramidal", "107°"),
    (4, 2): ("bent", "104.5°"),
    (5, 0): ("trigonal bipyramidal", "90° and 120°"),
    (5, 1): ("seesaw", "less than 90° and less than 120°"),
    (5, 2): ("T-shaped", "less than 90°"),
    (5, 3): ("linear", "180°"),
    (6, 0): ("octahedral", "90°"),
    (6, 1): ("square pyramidal", "less than 90°"),
    (6, 2): ("square planar", "90°"),
}
# Nonmetals and metalloids: the centres of a school VSEPR molecule. A metal centre is a salt
# unless its bonds are covalent (review, 2026-10-25: CaCl2, MgCl2 and CaF2 were verified as
# "linear, nonpolar" molecules; they are ionic lattices).
_NONMETAL_CENTERS = frozenset(
    {"B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Ge", "As", "Se", "Br", "Sb", "Te", "I"}
    | {"Kr", "Xe", "Rn"}
)
# A bond this polar is ionic (the Pauling difference school books use).
_IONIC_DIFFERENCE = 1.7
# Heavier group-14 atoms make no pi bonds: SiO2, GeO2, SnO2 are network solids, not O=Si=O.
_NO_PI_BONDS = frozenset({"Si", "Ge", "Sn", "Pb"})
# Shapes whose polarity depends on where unlike atoms sit: trans-SF4Cl2 and PCl3F2 with axial
# F are nonpolar, cis-SF4Cl2 is polar. With mixed terminals no single answer is true.
_ISOMER_POLARITY = frozenset({"trigonal bipyramidal", "octahedral", "square planar"})
# Atoms that can sit on one carbon in a school Lewis structure (HCN, H2CO).
_CARBON_TERMINALS = frozenset({"N", "O", "S", "F", "Cl", "Br", "I"})
_HYBRID = {2: "sp", 3: "sp2", 4: "sp3", 5: "sp3d", 6: "sp3d2"}


@dataclass(frozen=True)
class LewisStructure:
    """A central-atom Lewis description, not an arbitrary drawing."""

    formula: str
    central: str
    bond_orders: tuple[int, ...]
    central_lone_pairs: int
    terminal_elements: tuple[str, ...]
    geometry: str
    bond_angle: str
    electron_geometry: str
    ideal_angle: str
    polar: bool
    hybridization: str
    central_formal_charge: int
    resonance_forms: int
    electrons: int


def _formal_charge(element: str, lone_electrons: int, bonding_electrons: int) -> int:
    valence = valence_electrons(element)
    if valence is None:
        return 0
    return valence - lone_electrons - bonding_electrons // 2


# Atoms that can only be terminal (one bond). A hydrogen or halogen is never the center.
_TERMINAL_ONLY = frozenset({"H", "F", "Cl", "Br", "I"})


def _electronegativity(element: str) -> float:
    value = BY_SYMBOL[element].electronegativity
    return value if value is not None else 10.0


def _central_atom(species: ChemicalSpecies) -> str | None:
    """The one center of a covalent molecule; a salt's metal is none.

    An oxoacid's hydrogen sits on oxygen (H-O-N=O), not on the centre the builder would bond
    it to: HNO2 is bent at N, not trigonal planar, and HIO3 pyramidal. With hydrogen and oxygen
    both present only carbon (H2CO) or oxygen itself (H2O, H3O+) is a center, as with HOCl.
    """
    composition = species.composition
    center = _center_of(species)
    if center is None or _ionic(center, [atom for atom in composition if atom != center]):
        return None
    if "H" in composition and "O" in composition and center not in {"C", "O"}:
        return None
    return center


def _center_of(species: ChemicalSpecies) -> str | None:
    composition = species.composition
    candidates = [
        element
        for element, count in composition.items()
        if element != "H" and count == 1 and valence_electrons(element) is not None
    ]
    # HCN has two unique non-hydrogen atoms. Carbon is the center only when
    # every other non-hydrogen atom is a terminal nonmetal. HOCl is not guessed.
    if composition.get("C") == 1 and "C" in candidates:
        others = [element for element in composition if element not in {"C", "H"}]
        if others and all(element in _CARBON_TERMINALS for element in others):
            return "C"
    if len(candidates) == 1:
        center = candidates[0]
        # A repeated atom that is less electronegative than the lone one is the real
        # center (N-N-O in N2O, not O with two N). That is a chain, not one center.
        for element, count in composition.items():
            if element in _TERMINAL_ONLY or element == center or count < 2:
                continue
            if _electronegativity(element) <= _electronegativity(center):
                return None
        return center
    # Several unique atoms (SOCl2, POCl3, XeOF4, NOCl): the least electronegative is the
    # center. With hydrogen present the H may sit on any of them (HOCl), so do not guess.
    if len(candidates) > 1 and "H" not in composition:
        center = min(candidates, key=_electronegativity)
        for element, count in composition.items():
            if element in _TERMINAL_ONLY or element in candidates or count < 2:
                continue
            if _electronegativity(element) <= _electronegativity(center):
                return None
        return center
    # O3 is one element. H2O2 is a chain: repeated atoms plus hydrogen.
    non_hydrogen = [element for element in composition if element != "H"]
    if (
        len(non_hydrogen) == 1
        and "H" not in composition
        and valence_electrons(non_hydrogen[0]) is not None
    ):
        return non_hydrogen[0]
    return None


def _ionic(central: str, terminals: list[str]) -> bool:
    """A metal centre of group 1 or 2, or one whose bonds are ionic. Beryllium's are covalent
    in school chemistry: BeCl2 and BeF2 are the textbook linear molecules."""
    if central in _NONMETAL_CENTERS or central == "Be":
        return False
    if BY_SYMBOL[central].group in {1, 2}:
        return True
    center = _electronegativity(central)
    return any(_electronegativity(atom) - center >= _IONIC_DIFFERENCE for atom in terminals)


def _dipoles_cancel(terminals: list[str], lone_pairs: int, geometry: str) -> bool | None:
    """Whether the bond dipoles cancel; None when it depends on where unlike atoms sit."""
    identical = len(set(terminals)) == 1
    if not identical and geometry in _ISOMER_POLARITY:
        return None
    return identical and (lone_pairs == 0 or geometry in {"linear", "square planar"})


def _resonance_forms(terminals: list[str], bond_orders: list[int]) -> int:
    """Equivalent placements of unequal bonds on identical terminal atoms."""
    if len(terminals) < 2 or len(set(terminals)) != 1 or len(set(bond_orders)) < 2:
        return 1
    ways = math.factorial(len(bond_orders))
    counts: dict[int, int] = {}
    for order in bond_orders:
        counts[order] = counts.get(order, 0) + 1
    for count in counts.values():
        ways //= math.factorial(count)
    return ways


def lewis_structure(formula: str) -> LewisStructure | None:
    """Build one central-atom structure, or None when the recipe does not apply."""
    species = parse_species(formula, coefficient_already_removed=True)
    if species is None or species.electron:
        return None
    central = _central_atom(species)
    if central is None:
        return None
    terminals: list[str] = []
    for element, count in species.composition.items():
        copies = count - (1 if element == central else 0)
        if copies < 0 or valence_electrons(element) is None:
            return None
        terminals.extend([element] * copies)
    if not terminals:
        return None
    electrons = sum(
        (valence_electrons(element) or 0) * count for element, count in species.composition.items()
    )
    electrons -= species.charge
    if electrons < 0 or electrons % 2:
        return None
    bond_orders = [1] * len(terminals)
    used = 2 * len(terminals)
    if used > electrons:
        return None
    remaining = electrons - used
    lone_terminals = [0] * len(terminals)
    for index, element in enumerate(terminals):
        target = 2 if element == "H" else 8
        need = target - 2 * bond_orders[index]
        if need < 0 or need > remaining:
            return None
        lone_terminals[index] = need
        remaining -= need
    central_lone = remaining
    period = BY_SYMBOL[central].period

    def central_electrons() -> int:
        return central_lone + sum(2 * order for order in bond_orders)

    def charge_total() -> int:
        total = abs(_formal_charge(central, central_lone, sum(2 * order for order in bond_orders)))
        for index, element in enumerate(terminals):
            total += abs(_formal_charge(element, lone_terminals[index], 2 * bond_orders[index]))
        return total

    def best_donor() -> int | None:
        candidates = [
            index
            for index, element in enumerate(terminals)
            if element != "H" and lone_terminals[index] >= 2
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda index: (lone_terminals[index], -bond_orders[index]))

    if central not in {"B", "Be"}:
        guard = 0
        while central_electrons() < 8 and guard < 8:
            guard += 1
            donor = best_donor()
            if donor is None:
                if period >= 3:
                    break
                return None
            before = charge_total()
            lone_terminals[donor] -= 2
            bond_orders[donor] += 1
            if period >= 3 and charge_total() >= before:
                # AlCl3, SnCl2: a sextet or a lone pair beats a double bond that
                # only moves charge around. Period-2 atoms still need their octet.
                lone_terminals[donor] += 2
                bond_orders[donor] -= 1
                break
    if period >= 3 and central not in {"B", "Be"}:
        guard = 0
        while guard < 8:
            guard += 1
            donor = best_donor()
            if donor is None:
                break
            before = charge_total()
            lone_terminals[donor] -= 2
            bond_orders[donor] += 1
            if charge_total() >= before:
                lone_terminals[donor] += 2
                bond_orders[donor] -= 1
                break
    lone_pairs = central_lone // 2
    steric = len(terminals) + lone_pairs
    molecular = _MOLECULAR_GEOMETRY.get((steric, lone_pairs))
    if (
        molecular is not None
        and (steric, lone_pairs) in {(4, 1), (4, 2)}
        and not (period == 2 and set(terminals) == {"H"})
    ):
        # 104.5° and 107° are the water and ammonia values. H2S is about 92°, PCl3 about 100°,
        # OF2 about 103°: only "smaller than tetrahedral" is true for all of them.
        molecular = (molecular[0], "less than 109.5°")
    electron = _ELECTRON_GEOMETRY.get(steric)
    hybrid = _HYBRID.get(steric)
    if molecular is None or electron is None or hybrid is None or central_lone % 2:
        return None
    signed_charge = _formal_charge(central, central_lone, sum(2 * order for order in bond_orders))
    for index, element in enumerate(terminals):
        signed_charge += _formal_charge(element, lone_terminals[index], 2 * bond_orders[index])
    if signed_charge != species.charge:
        return None
    symmetric = _dipoles_cancel(terminals, lone_pairs, molecular[0])
    if symmetric is None or (central in _NO_PI_BONDS and max(bond_orders) > 1):
        return None
    return LewisStructure(
        formula=species.label,
        central=central,
        bond_orders=tuple(bond_orders),
        central_lone_pairs=lone_pairs,
        terminal_elements=tuple(terminals),
        geometry=molecular[0],
        bond_angle=molecular[1],
        electron_geometry=electron[0],
        ideal_angle=electron[1],
        polar=not symmetric,
        hybridization=hybrid,
        central_formal_charge=_formal_charge(
            central, central_lone, sum(2 * order for order in bond_orders)
        ),
        resonance_forms=_resonance_forms(terminals, bond_orders),
        electrons=electrons,
    )
