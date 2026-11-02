"""One-product school reactions. A curved-arrow mechanism is not a result."""

from __future__ import annotations

from typing import Any

from app.modules.chemistry.smiles import parse_mol

_HALOGENS = frozenset({"F", "Cl", "Br", "I"})


def named_product(reaction: str, smiles: str, partner: str | None = None) -> str | None:
    """Return one canonical product SMILES, or None when the match is not unique."""
    molecule = parse_mol(smiles)
    if molecule is None:
        return None
    if reaction == "bromine":
        return _add_across_alkene(molecule, "Br", "Br")
    if reaction == "hbr":
        return _add_across_alkene(molecule, "Br", None)
    if reaction == "hcl":
        return _add_across_alkene(molecule, "Cl", None)
    if reaction == "hi":
        return _add_across_alkene(molecule, "I", None)
    if reaction == "hydrogenation":
        return _saturate_alkene(molecule)
    if reaction == "hydration":
        return _add_across_alkene(molecule, "O", None)
    if reaction == "hydroxide":
        return _substitute_primary_halide(molecule)
    if reaction == "esterification":
        return _ester(molecule, partner)
    return None


def _alkene_bond(molecule: Any) -> tuple[int, int] | None:
    from rdkit import Chem

    found: list[tuple[int, int]] = []
    for bond in molecule.GetBonds():
        if bond.GetBondType() != Chem.BondType.DOUBLE:
            continue
        left = bond.GetBeginAtom()
        right = bond.GetEndAtom()
        if left.GetSymbol() != "C" or right.GetSymbol() != "C":
            continue
        if left.GetIsAromatic() or right.GetIsAromatic():
            continue
        found.append((left.GetIdx(), right.GetIdx()))
    if len(found) != 1:
        return None
    return found[0]


def _saturate_alkene(molecule: Any) -> str | None:
    """Catalytic hydrogenation: one C=C becomes a single bond. Two alkenes are not one product."""
    from rdkit import Chem

    bond = _alkene_bond(molecule)
    if bond is None:
        return None
    edited = Chem.RWMol(molecule)
    edited.GetBondBetweenAtoms(*bond).SetBondType(Chem.BondType.SINGLE)
    return _canonical(edited)


def _substituents(molecule: Any, index: int, other: int) -> int | None:
    """Carbon neighbours of an alkene carbon, or None when a heteroatom is attached.

    Markovnikov's rule is counted in alkyl groups; a heteroatom (an enol ether, a vinyl
    halide) directs the addition by resonance instead, which this table does not model.
    """
    atom = molecule.GetAtomWithIdx(index)
    count = 0
    for neighbor in atom.GetNeighbors():
        if neighbor.GetIdx() == other:
            continue
        if neighbor.GetSymbol() != "C":
            return None
        count += 1
    return count


def _add_across_alkene(molecule: Any, first: str, second: str | None) -> str | None:
    """``first`` goes to the more substituted carbon; a tie is accepted only if it cannot matter."""
    from rdkit import Chem

    bond = _alkene_bond(molecule)
    if bond is None:
        return None
    left, right = bond
    left_subs = _substituents(molecule, left, right)
    right_subs = _substituents(molecule, right, left)
    if left_subs is None or right_subs is None:
        return None
    if second is not None and first == second:
        orientations = [(left, right)]  # Br2: the same atom goes to both carbons
    elif left_subs != right_subs:
        orientations = [(left, right) if left_subs > right_subs else (right, left)]
    else:
        orientations = [(left, right), (right, left)]
    products: set[str | None] = set()
    for rich, poor in orientations:
        edited = Chem.RWMol(molecule)
        edited.GetBondBetweenAtoms(left, right).SetBondType(Chem.BondType.SINGLE)
        _attach(edited, rich, first)
        if second is not None:
            _attach(edited, poor, second)
        products.add(_canonical(edited))
    if len(products) != 1:
        return None  # 2-pentene + HBr gives two products; picking one would be a guess
    return next(iter(products))


def _attach(molecule: Any, index: int, symbol: str) -> None:
    from rdkit import Chem

    added = molecule.AddAtom(Chem.Atom(symbol))
    molecule.AddBond(index, added, Chem.BondType.SINGLE)


def _substitute_primary_halide(molecule: Any) -> str | None:
    """SN2 by hydroxide, only when exactly one halogen is on a methyl or primary sp3 carbon."""
    from rdkit import Chem

    halogens = [atom for atom in molecule.GetAtoms() if atom.GetSymbol() in _HALOGENS]
    if len(halogens) != 1:
        return None
    halogen = halogens[0]
    neighbors = halogen.GetNeighbors()
    if len(neighbors) != 1:
        return None
    carbon = neighbors[0]
    if carbon.GetSymbol() != "C" or carbon.GetHybridization() != Chem.HybridizationType.SP3:
        return None
    # Methyl has no carbon neighbor. Two or more is secondary or tertiary.
    if sum(1 for atom in carbon.GetNeighbors() if atom.GetSymbol() == "C") > 1:
        return None
    edited = Chem.RWMol(molecule)
    edited.GetAtomWithIdx(halogen.GetIdx()).SetAtomicNum(8)
    return _canonical(edited)


def _ester(acid: Any, partner: str | None) -> str | None:
    from rdkit.Chem import AllChem

    if not partner:
        return None
    alcohol = parse_mol(partner)
    if alcohol is None:
        return None
    # RDKit's stubs omit AllChem.ReactionFromSmarts.
    reaction = AllChem.ReactionFromSmarts(  # type: ignore[attr-defined]
        "[C:1](=[O:2])[OX2H1].[OX2H1][CX4:3]>>[C:1](=[O:2])O[C:3]"
    )
    found: set[str] = set()
    for outcome in reaction.RunReactants((acid, alcohol)):
        smiles = _canonical(outcome[0])
        if smiles is not None:
            found.add(smiles)
    if len(found) != 1:
        return None
    return next(iter(found))


def _canonical(molecule: Any) -> str | None:
    from rdkit import Chem

    try:
        Chem.SanitizeMol(molecule)
    except (ValueError, RuntimeError):
        return None
    return Chem.MolToSmiles(molecule)
