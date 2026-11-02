"""Deterministic organic checks that RDKit can decide without a reaction engine.

Functional groups use SMARTS. Stereochemistry uses RDKit CIP. Isomer class
compares formula and canonical SMILES. IUPAC names are not invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

from app.modules.chemistry.smiles import parse_mol

# Every pattern excludes what it is not on the atoms themselves, so one group never hides
# another elsewhere in the molecule (pyruvic acid is an acid *and* a ketone).
_CARBONYL_C = "[CX3;H1,$([CX3][#6])]"  # a carbonyl carbon carrying H or C, so not a carbonate/urea
_GROUPS: tuple[tuple[str, str], ...] = (
    ("carboxylic acid", f"{_CARBONYL_C}(=O)[OX2H1]"),
    ("ester", f"{_CARBONYL_C}(=O)[OX2H0][#6;!$([CX3]=O)]"),
    ("anhydride", "[CX3](=O)[OX2][CX3](=O)"),
    ("acyl halide", f"{_CARBONYL_C}(=O)[F,Cl,Br,I]"),
    ("amide", f"[NX3]{_CARBONYL_C}=O"),
    ("aldehyde", "[$([CX3;H1](=O)[#6]),$([CX3;H2]=O)]"),
    ("ketone", "[#6][CX3](=O)[#6]"),
    ("phenol", "[OX2H]c"),
    ("alcohol", "[OX2H][CX4]"),
    ("thiol", "[SX2H][#6]"),
    (
        "amine",
        "[NX3;+0;H2,H1;!$(N=*);!$(N-C=[O,S,N]);!$(N-S=O);!$(N-[#7,#8]);$(N-[#6])]",
    ),
    (
        "tertiary amine",
        "[NX3;+0;H0;!$(N=*);!$(N-C=[O,S,N]);!$(N-S=O);!$(N-[#7,#8]);$(N-[#6])]",
    ),
    ("nitro", "[NX3+](=O)[O-]"),
    ("nitrile", "[CX2]#[NX1]"),
    ("alkyne", "[CX2]#[CX2]"),
    ("alkene", "[CX3;!a]=[CX3;!a]"),
    ("ether", "[OD2]([#6;!$([CX3]=[O,S,N])])[#6;!$([CX3]=[O,S,N])]"),
    ("haloalkane", "[CX4][F,Cl,Br,I]"),
    ("aryl halide", "c[F,Cl,Br,I]"),
    ("aromatic", "a"),
)


def group_pattern(name: str) -> str | None:
    """The SMARTS a functional group is matched with, for showing the working."""
    return dict(_GROUPS).get(name)


@dataclass(frozen=True)
class OrganicFacts:
    """Verified structure facts. Mechanisms stay outside this result."""

    groups: tuple[str, ...]
    chirality: tuple[str, ...]
    double_bond_stereo: tuple[str, ...]
    formula: str
    canonical_smiles: str


@cache
def _queries() -> tuple[tuple[str, Any], ...]:
    from rdkit import Chem

    compiled = tuple((name, Chem.MolFromSmarts(smarts)) for name, smarts in _GROUPS)
    broken = [name for name, query in compiled if query is None]
    if broken:  # a typo in a pattern above, not a user error
        raise RuntimeError(f"invalid SMARTS for {', '.join(broken)}")
    return compiled


def _stereo_facts(molecule: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """R/S per stereocenter and E/Z per double bond, 1-based like the atoms in a drawing."""
    from rdkit import Chem
    from rdkit.Chem import rdCIPLabeler

    rdCIPLabeler.AssignCIPLabels(molecule)
    centers: list[str] = []
    bonds: list[str] = []
    for info in Chem.FindPotentialStereo(molecule):
        specified = info.specified == Chem.StereoSpecified.Specified
        if info.type == Chem.StereoType.Atom_Tetrahedral:
            atom = molecule.GetAtomWithIdx(info.centeredOn)
            label = atom.GetProp("_CIPCode") if specified and atom.HasProp("_CIPCode") else None
            centers.append(
                f"atom {atom.GetIdx() + 1} ({atom.GetSymbol()}): {label or 'unspecified'}"
            )
        elif info.type == Chem.StereoType.Bond_Double:
            bond = molecule.GetBondWithIdx(info.centeredOn)
            begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
            ends = f"{begin.GetSymbol()}{begin.GetIdx() + 1}={end.GetSymbol()}{end.GetIdx() + 1}"
            label = bond.GetProp("_CIPCode") if specified and bond.HasProp("_CIPCode") else None
            bonds.append(f"{ends}: {label or 'unspecified'}")
    return tuple(centers), tuple(bonds)


def organic_facts(smiles: str) -> OrganicFacts | None:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    molecule = parse_mol(smiles)
    if molecule is None:
        return None
    found = [name for name, query in _queries() if molecule.HasSubstructMatch(query)]
    chirality, stereo = _stereo_facts(molecule)
    return OrganicFacts(
        groups=tuple(found),
        chirality=chirality,
        double_bond_stereo=stereo,
        formula=rdMolDescriptors.CalcMolFormula(molecule),
        canonical_smiles=Chem.MolToSmiles(molecule),
    )


def isomer_relationship(left: str, right: str) -> str | None:
    """Identical, stereoisomers, constitutional isomers, or different compounds."""
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    first = parse_mol(left)
    second = parse_mol(right)
    if first is None or second is None:
        return None
    if rdMolDescriptors.CalcMolFormula(first) != rdMolDescriptors.CalcMolFormula(second):
        return "different compounds"
    iso_left = Chem.MolToSmiles(first)
    iso_right = Chem.MolToSmiles(second)
    if iso_left == iso_right:
        return "identical"
    plain_left = Chem.MolToSmiles(first, isomericSmiles=False)
    plain_right = Chem.MolToSmiles(second, isomericSmiles=False)
    if plain_left == plain_right:
        return "stereoisomers"
    return "constitutional isomers"
