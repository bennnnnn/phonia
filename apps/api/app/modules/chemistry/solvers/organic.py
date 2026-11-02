"""Organic chemistry: functional groups, stereochemistry, isomers, names, and named reactions."""

from __future__ import annotations

from dataclasses import replace

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.organic import group_pattern, isomer_relationship, organic_facts
from app.modules.chemistry.reactions import named_product
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError


def solve_functional_groups(intent: ChemistryIntent) -> ChemistryResult:
    facts = organic_facts(intent.formula or "")
    if facts is None or not facts.groups:
        raise SolveServiceError("no functional group recognized")
    shown = "\n".join(facts.groups)
    return verified(
        "Verified functional groups",
        (facts.canonical_smiles,),
        "Functional groups",
        *stated("functional_groups"),
        tuple(f"{group}: {group_pattern(group)}" for group in facts.groups),
        shown,
        shown,
        verbatim=True,
    )


def solve_stereochemistry(intent: ChemistryIntent) -> ChemistryResult:
    facts = organic_facts(intent.formula or "")
    if facts is None:
        raise SolveServiceError("SMILES could not be read")
    parts = [*facts.chirality, *facts.double_bond_stereo]
    shown = "\n".join(parts) if parts else "no stereocenter"
    return verified(
        "Verified stereochemistry",
        (facts.canonical_smiles,),
        "CIP stereochemistry",
        *stated("stereochemistry"),
        (
            f"{len(facts.chirality)} possible stereocenter(s) and "
            f"{len(facts.double_bond_stereo)} stereo double bond(s) in {facts.canonical_smiles}",
            "atoms are numbered from 1 in the order the SMILES is written",
        ),
        shown,
        shown,
        verbatim=True,
    )


def solve_isomers(intent: ChemistryIntent) -> ChemistryResult:
    left, right = intent.formula or "", intent.target or ""
    relationship = isomer_relationship(left, right)
    first, second = organic_facts(left), organic_facts(right)
    if relationship is None or first is None or second is None:
        raise SolveServiceError("both structures must be valid SMILES")
    return verified(
        "Verified isomer relationship",
        (left, right),
        "Isomer relationship",
        *stated("isomers"),
        (
            f"formula: {first.formula} and {second.formula}",
            f"canonical SMILES: {first.canonical_smiles} and {second.canonical_smiles}",
        ),
        relationship,
        relationship,
        verbatim=True,
    )


def solve_iupac_name(_intent: ChemistryIntent) -> ChemistryResult:
    raise SolveServiceError("IUPAC names come from PubChem, not a local solver")


def solve_structure(_intent: ChemistryIntent) -> ChemistryResult:
    raise SolveServiceError("A named compound's structure comes from PubChem, not a local solver")


_REACTIONS = {
    "bromine": (
        "bromine addition across the C=C",
        "Br adds to both carbons of the double bond",
    ),
    "hbr": (
        "HBr addition to the C=C (Markovnikov)",
        "H goes to the carbon with more hydrogens, Br to the more substituted carbon",
    ),
    "hcl": (
        "HCl addition to the C=C (Markovnikov)",
        "H goes to the carbon with more hydrogens, Cl to the more substituted carbon",
    ),
    "hi": (
        "HI addition to the C=C (Markovnikov)",
        "H goes to the carbon with more hydrogens, I to the more substituted carbon",
    ),
    "hydrogenation": (
        "catalytic hydrogenation of the C=C",
        "H adds to both carbons of the double bond",
    ),
    "hydration": (
        "acid-catalysed hydration of the C=C (Markovnikov)",
        "H goes to the carbon with more hydrogens, OH to the more substituted carbon",
    ),
    "hydroxide": (
        "hydroxide substitution (SN2)",
        "OH- replaces the halogen on a primary sp3 carbon",
    ),
    "esterification": (
        "Fischer esterification",
        "the acid's OH and the alcohol's H leave as water; the acyl carbon bonds to the alcohol O",
    ),
}


def solve_named_reaction(intent: ChemistryIntent) -> ChemistryResult:
    product = named_product(intent.target or "", intent.formula or "", intent.equation)
    if product is None:
        raise SolveServiceError("the reaction did not give one product")
    name, rule = _REACTIONS.get(intent.target or "", (intent.target or "reaction", ""))
    shown = f"product SMILES {product}"
    given = [f"reaction: {name}", f"substrate SMILES: {intent.formula or ''}"]
    if intent.equation:
        given.append(f"partner SMILES: {intent.equation}")
    result = verified(
        "Verified named reaction",
        given,
        "Product",
        *stated("named_reaction"),
        (rule, f"only one product results: {product}") if rule else (shown,),
        shown,
        shown,
        verbatim=True,
    )
    return replace(result, structure_smiles=product)
