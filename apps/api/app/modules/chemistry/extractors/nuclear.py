"""Nuclear chemistry: a nuclear equation's missing particle and a nuclide's mass defect."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _NUCLIDE,
    _search,
)
from app.modules.chemistry.schemas import ChemistryIntent


def _extract_nuclear_equation(text: str) -> ChemistryIntent | None:
    # Half-lives, decay constants and activities are physics' laws (physics/catalog/nuclear.py).
    match = re.search(r"nuclear equation\s*:?\s+(.+)$", text, re.IGNORECASE)
    if match:
        return ChemistryIntent(
            kind="nuclear", chemistry_op="nuclear_equation", equation=match.group(1).strip()
        )
    return None


def _extract_mass_defect(text: str) -> ChemistryIntent | None:
    if not re.search(r"\b(?:mass defect|binding energy)\b", text, re.IGNORECASE):
        return None
    nuclide = re.search(rf"\b({_NUCLIDE})\b", text)
    mass = _search(rf"\bnuclear mass\s*=\s*({_N})", text)
    if nuclide is None or mass is None:
        return None
    return ChemistryIntent(
        kind="nuclear",
        chemistry_op="mass_defect",
        formula=nuclide.group(1),
        params={"nuclear_mass": mass},
        units={"nuclear_mass": "u"},
    )
