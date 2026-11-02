"""Organic chemistry: functional groups, stereochemistry, isomers, and named reactions."""

from __future__ import annotations

import re

from app.modules.chemistry.schemas import ChemistryIntent


def _extract_organic(text: str) -> ChemistryIntent | None:
    if re.search(r"\bfunctional groups\b", text, re.IGNORECASE):
        smiles = re.search(r"\bSMILES\s+(\S+)", text, re.IGNORECASE)
        if smiles:
            return ChemistryIntent(
                kind="organic", chemistry_op="functional_groups", formula=smiles.group(1)
            )
    if re.search(r"\bstereochemistry\b", text, re.IGNORECASE):
        smiles = re.search(r"\bSMILES\s+(\S+)", text, re.IGNORECASE)
        if smiles:
            return ChemistryIntent(
                kind="organic", chemistry_op="stereochemistry", formula=smiles.group(1)
            )
    if re.search(r"\bisomer\b", text, re.IGNORECASE):
        pair = re.search(r"\bSMILES\s+(\S+)\s+and\s+(\S+)", text, re.IGNORECASE)
        if pair:
            return ChemistryIntent(
                kind="organic",
                chemistry_op="isomers",
                formula=pair.group(1),
                target=pair.group(2).rstrip("?"),
            )
    return None


_REACTIONS = {
    "hbr addition": "hbr",
    "hcl addition": "hcl",
    "hi addition": "hi",
    "bromine addition": "bromine",
    "acid hydration": "hydration",
    "catalytic hydrogenation": "hydrogenation",
    "hydroxide substitution": "hydroxide",
    "esterification": "esterification",
}


def _extract_named_reaction(text: str) -> ChemistryIntent | None:
    lowered = text.lower()
    key = next((name for name in _REACTIONS if name in lowered), None)
    if key is None:
        return None
    # Peroxide/radical HBr is anti-Markovnikov. This path only verifies the ionic rule.
    if _REACTIONS[key] == "hbr" and re.search(r"\b(?:peroxides?|radicals?|roor)\b", lowered):
        return None
    smiles = re.findall(r"\bSMILES\s+(\S+)", text, re.IGNORECASE)
    if not smiles:
        return None
    partner = smiles[1].rstrip("?.!,") if len(smiles) > 1 else None
    return ChemistryIntent(
        kind="organic",
        chemistry_op="named_reaction",
        formula=smiles[0].rstrip("?.!,"),
        target=_REACTIONS[key],
        equation=partner,
    )
