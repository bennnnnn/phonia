"""SMILES validation, molecular properties, and coordinates.

Every RDKit call in the chemistry package starts here (``parse_mol``), so the size cap and
the formula mapping apply once and RDKit's own stderr logging is silenced once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cache, lru_cache
from typing import Any

logger = logging.getLogger(__name__)

MAX_SMILES_LENGTH = 500
# Three-dimensional embedding is O(atoms^2) or worse and its SDF must fit what the phone accepts
# (``MAX_SDF_LENGTH`` in ``apps/mobile/lib/chemistry/molecule3dFence.ts``), so a molecule past
# either limit is skipped here instead of being silently dropped by the client.
MAX_3D_HEAVY_ATOMS = 120
MAX_SDF_CHARS = 50_000
_EMBED_SEED = 0xF00D  # the same molecule gives the same picture on every turn

# Formulas a student types where SMILES belongs. RDKit cannot read them (it has no ``H`` outside
# brackets and reads ``CO2`` as an unclosed ring), so the few molecules everyone draws are mapped.
_FORMULA_SMILES: dict[str, str] = {
    "H-H": "[H][H]",
    "H2": "[H][H]",
    "O2": "O=O",
    "N2": "N#N",
    "F2": "FF",
    "Cl2": "ClCl",
    "Br2": "BrBr",
    "I2": "II",
    "H2O": "O",
    "CO2": "O=C=O",
    "NH3": "N",
    "CH4": "C",
    "HCl": "Cl",
    "NaCl": "[Na+].[Cl-]",
}


@cache
def _load_rdkit() -> None:
    """Silence RDKit's own logging. An unparsable SMILES is an ordinary answer here, and RDKit
    writes a multi-line error to stderr for every one (``H2O`` alone prints four lines)."""
    from rdkit import rdBase

    rdBase.DisableLog("rdApp.*")


def parse_mol(smiles: str, *, map_formulas: bool = True) -> Any | None:
    """An RDKit molecule from user SMILES, or None when empty, oversized or invalid.

    ``map_formulas=False`` reads the text strictly as SMILES: ``H2O`` is then invalid instead of
    being mapped to water.
    """
    _load_rdkit()
    from rdkit import Chem

    cleaned = normalize_smiles_input(smiles) if map_formulas else smiles.strip()
    if not cleaned or len(cleaned) > MAX_SMILES_LENGTH:
        return None
    return Chem.MolFromSmiles(cleaned)


def normalize_smiles_input(raw: str) -> str:
    """Map the few common formulas that are not SMILES to SMILES RDKit can parse."""
    key = raw.strip()
    return _FORMULA_SMILES.get(key, key)


@dataclass(frozen=True)
class MoleculeProperties:
    """Verified molecular properties from RDKit."""

    smiles: str  # canonical SMILES
    formula: str  # molecular formula (Hill notation)
    molecular_weight: float  # g/mol
    valid: bool = True
    error: str | None = None

    @classmethod
    def failure(cls, smiles: str, error: str) -> MoleculeProperties:
        return cls(smiles, "", 0.0, valid=False, error=error)


@dataclass(frozen=True)
class MoleculeCoordinates:
    """3D coordinates of a molecule as an SDF (MOL block) for the phone's molecule card."""

    smiles: str
    # Empty when coordinates could not be generated.
    sdf: str = ""
    error: str | None = None


@dataclass(frozen=True)
class MolecularDescriptors:
    """RDKit-computed molecular descriptors for drug-likeness assessment."""

    smiles: str
    molecular_weight: float
    log_p: float  # partition coefficient (lipophilicity)
    tpsa: float  # topological polar surface area
    h_bond_donors: int  # Lipinski H-bond donors
    h_bond_acceptors: int  # Lipinski H-bond acceptors
    rotatable_bonds: int
    ring_count: int
    error: str | None = None

    @classmethod
    def failure(cls, smiles: str, error: str) -> MolecularDescriptors:
        return cls(smiles, 0, 0, 0, 0, 0, 0, 0, error=error)


@lru_cache(maxsize=512)
def validate_smiles(smiles: str) -> MoleculeProperties:
    """Validate a SMILES string and compute molecular properties.

    Returns MoleculeProperties with valid=False if the SMILES is invalid.
    """
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    cleaned = normalize_smiles_input(smiles)
    if not cleaned or len(cleaned) > MAX_SMILES_LENGTH:
        return MoleculeProperties.failure(cleaned, "SMILES too long or empty")
    try:
        mol = parse_mol(cleaned)
        if mol is None:
            return MoleculeProperties.failure(cleaned, "invalid SMILES")
        return MoleculeProperties(
            smiles=Chem.MolToSmiles(mol),
            formula=rdMolDescriptors.CalcMolFormula(mol),
            molecular_weight=float(rdMolDescriptors._CalcMolWt(mol)),
        )
    except Exception as exc:
        logger.info("RDKit validate failed for %r: %s", cleaned, exc)
        return MoleculeProperties.failure(cleaned, str(exc))


def drawing_smiles(smiles: str) -> str:
    """The SMILES the phone draws: the Kekulé form, every ring bond single or double.

    smiles-drawer counts an aromatic bond as single when it adds implicit hydrogens, so an
    aromatic heteroatom or a ring carbon with ``=O`` got hydrogens it does not have (caffeine
    was drawn with ``CH₂`` and ``HC`` in its rings). Spelled-out bonds draw right. Falls back
    to the input when RDKit cannot kekulize it.
    """
    from rdkit import Chem

    mol = parse_mol(smiles)
    if mol is None:
        return smiles
    try:
        Chem.Kekulize(mol, clearAromaticFlags=True)
        return str(Chem.MolToSmiles(mol, kekuleSmiles=True))
    except Exception:
        logger.info("RDKit kekulize failed for %r", smiles, exc_info=True)
        return smiles


def element_counts(smiles: str) -> dict[str, int] | None:
    """Atoms per element with implicit hydrogens; None for invalid or isotope-labelled SMILES."""
    from rdkit import Chem

    mol = parse_mol(smiles)
    if mol is None:
        return None
    counts: dict[str, int] = {}
    for atom in Chem.AddHs(mol).GetAtoms():
        if atom.GetIsotope():
            return None  # ``[13C]`` is not the most-common isotope this table assumes
        counts[atom.GetSymbol()] = counts.get(atom.GetSymbol(), 0) + 1
    return counts


def most_common_isotope(symbol: str) -> tuple[float, int] | None:
    """``(exact mass, mass number)`` of an element's most abundant isotope."""
    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    try:
        number = table.GetAtomicNumber(symbol)
        return table.GetMostCommonIsotopeMass(number), table.GetMostCommonIsotope(number)
    except (RuntimeError, ValueError):
        return None


def generate_3d_coordinates(smiles: str) -> MoleculeCoordinates:
    """Generate 3D coordinates as an SDF string for the molecule card.

    ETKDG embedding with a fixed seed and one thread (this runs in a worker pool, where
    ``numThreads=0`` would take every core), a random-coordinate retry for the molecules the
    default start cannot place, and a UFF fallback where MMFF has no parameters (metals,
    unusual valences). Returns MoleculeCoordinates with empty sdf on failure or when the
    molecule or its SDF is too large for the phone.
    """
    from rdkit import Chem
    from rdkit.Chem import rdDistGeom, rdForceFieldHelpers

    parsed = parse_mol(smiles)
    if parsed is None:
        return MoleculeCoordinates(smiles=normalize_smiles_input(smiles), error="invalid SMILES")
    canonical = Chem.MolToSmiles(parsed)
    if parsed.GetNumHeavyAtoms() > MAX_3D_HEAVY_ATOMS:
        return MoleculeCoordinates(smiles=canonical, error="too large for a 3D view")
    try:
        mol = Chem.AddHs(parsed)
        params: Any = rdDistGeom.ETKDGv3()  # the stubs mistype its attributes
        params.randomSeed = _EMBED_SEED
        params.numThreads = 1
        if rdDistGeom.EmbedMolecule(mol, params) != 0:
            params.useRandomCoords = True
            if rdDistGeom.EmbedMolecule(mol, params) != 0:
                return MoleculeCoordinates(smiles=canonical, error="3D embedding failed")
        # -1 means MMFF has no parameters for an atom; UFF covers the periodic table.
        if rdForceFieldHelpers.MMFFOptimizeMolecule(mol) == -1:
            rdForceFieldHelpers.UFFOptimizeMolecule(mol)
        # Keep explicit H: RemoveHs made water a lone oxygen in the 3D card.
        sdf = Chem.MolToMolBlock(mol)
    except Exception as exc:
        logger.info("RDKit 3D coords failed for %r: %s", canonical, exc)
        return MoleculeCoordinates(smiles=canonical, error=str(exc))
    if len(sdf) > MAX_SDF_CHARS:
        return MoleculeCoordinates(smiles=canonical, error="3D structure is too large to send")
    return MoleculeCoordinates(smiles=canonical, sdf=sdf)


def compute_descriptors(smiles: str) -> MolecularDescriptors:
    """Compute molecular descriptors for a SMILES using RDKit.

    Returns MolecularDescriptors with error set on failure.
    """
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    cleaned = normalize_smiles_input(smiles)
    try:
        mol = parse_mol(cleaned)
        if mol is None:
            return MolecularDescriptors.failure(cleaned, "invalid SMILES")
        return MolecularDescriptors(
            smiles=Chem.MolToSmiles(mol),
            molecular_weight=round(float(rdMolDescriptors._CalcMolWt(mol)), 2),
            log_p=round(float(rdMolDescriptors.CalcCrippenDescriptors(mol)[0]), 2),
            tpsa=round(float(rdMolDescriptors.CalcTPSA(mol)), 2),
            h_bond_donors=int(rdMolDescriptors.CalcNumHBD(mol)),
            h_bond_acceptors=int(rdMolDescriptors.CalcNumHBA(mol)),
            rotatable_bonds=int(rdMolDescriptors.CalcNumRotatableBonds(mol)),
            ring_count=int(rdMolDescriptors.CalcNumRings(mol)),
        )
    except Exception as exc:
        return MolecularDescriptors.failure(cleaned, str(exc))
