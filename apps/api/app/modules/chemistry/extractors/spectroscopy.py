# ruff: noqa: RUF002
"""Spectroscopy: Beer–Lambert, IR and NMR tables, splitting, and the molecular ion."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _NUCLIDE,
    _search,
)
from app.modules.chemistry.schemas import ChemistryIntent


def _extract_beer_lambert(text: str) -> ChemistryIntent | None:
    if not re.search(r"\b(?:Beer[- ]Lambert|absorbance)\b", text, re.IGNORECASE):
        return None
    absorbance = _search(rf"(?:absorbance|\bA)\s*=\s*({_N})", text)
    epsilon = _search(rf"(?:ε|epsilon|molar absorptivity)\s*=\s*({_N})", text)
    path = _search(rf"(?:path length|\bb)\s*=\s*({_N})\s*cm", text)
    concentration = _search(
        rf"(?:concentration|\bc)\s*=\s*({_N})\s*(?:(?-i:M)(?![A-Za-z])|mol/L)", text
    )
    values = {
        "absorbance": absorbance,
        "epsilon": epsilon,
        "path": path,
        "concentration": concentration,
    }
    if sum(value is None for value in values.values()) != 1:
        return None
    return ChemistryIntent(
        kind="spectroscopy",
        chemistry_op="beer_lambert",
        params={key: value for key, value in values.items() if value is not None},
    )


def _extract_spectrum(text: str) -> ChemistryIntent | None:
    smiles = re.search(r"\bSMILES\s+(\S+)", text, re.IGNORECASE)
    formula = smiles.group(1).rstrip("?.!,") if smiles else None
    if re.search(r"\bIR ranges\b", text, re.IGNORECASE) and formula:
        return ChemistryIntent(kind="spectroscopy", chemistry_op="ir_ranges", formula=formula)
    if re.search(r"\bNMR ranges\b", text, re.IGNORECASE) and formula:
        return ChemistryIntent(kind="spectroscopy", chemistry_op="nmr_ranges", formula=formula)
    ir_peak = _search(rf"\bIR peak\s*(?:=|at)?\s*({_N})", text)
    if ir_peak is not None:
        return ChemistryIntent(
            kind="spectroscopy", chemistry_op="ir_peak", params={"peak": ir_peak}
        )
    nmr_peak = _search(rf"\bNMR peak\s*(?:=|at)?\s*({_N})", text)
    if nmr_peak is not None:
        return ChemistryIntent(
            kind="spectroscopy", chemistry_op="nmr_peak", params={"peak": nmr_peak}
        )
    if re.search(r"\bNMR splitting\b", text, re.IGNORECASE):
        neighbors = _search(rf"neighbors\s*=\s*({_N})", text)
        if neighbors is not None:
            return ChemistryIntent(
                kind="spectroscopy", chemistry_op="nmr_splitting", params={"neighbors": neighbors}
            )
    if re.search(r"\bmolecular ion\b", text, re.IGNORECASE):
        target = formula
        if target is None:
            plain = re.search(
                rf"molecular ion of\s+({_NUCLIDE}|[A-Z][A-Za-z0-9]+)", text, re.IGNORECASE
            )
            target = plain.group(1) if plain else None
        if target:
            return ChemistryIntent(
                kind="spectroscopy", chemistry_op="molecular_ion", formula=target
            )
    return None
