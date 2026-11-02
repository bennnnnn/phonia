"""Analytical chemistry: calibration, gravimetric analysis, standard addition, statistics."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _floats,
    _search,
)
from app.modules.chemistry.schemas import ChemistryIntent


def _extract_analytical(text: str) -> ChemistryIntent | None:
    limit = _extract_detection_limit(text)
    if limit is not None:
        return limit
    column = _extract_column(text)
    if column is not None:
        return column
    if re.search(r"\bcalibration curve\b", text, re.IGNORECASE):
        slope = _search(rf"\bslope\s*=\s*({_N})", text)
        intercept = _search(rf"\bintercept\s*=\s*({_N})", text)
        signal = _search(rf"\bsignal\s*=\s*({_N})", text)
        params = _floats(slope=slope, intercept=intercept, signal=signal)
        if params is not None:
            return ChemistryIntent(kind="analytical", chemistry_op="calibration", params=params)
    if re.search(r"\bGravimetric\b", text, re.IGNORECASE):
        mass = _search(rf"precipitate mass\s*=\s*({_N})", text)
        factor = _search(rf"\bfactor\s*=\s*({_N})", text)
        if mass is not None and factor is not None:
            return ChemistryIntent(
                kind="analytical",
                chemistry_op="gravimetric",
                params={"precipitate_mass": mass, "factor": factor},
            )
    if re.search(r"\bStandard addition\b", text, re.IGNORECASE):
        params = _floats(
            sample_signal=_search(rf"sample signal\s*=\s*({_N})", text),
            spiked_signal=_search(rf"spiked signal\s*=\s*({_N})", text),
            standard_concentration=_search(rf"standard concentration\s*=\s*({_N})", text),
            standard_volume=_search(rf"standard volume\s*=\s*({_N})", text),
            sample_volume=_search(rf"sample volume\s*=\s*({_N})", text),
        )
        if params is not None:
            return ChemistryIntent(
                kind="analytical", chemistry_op="standard_addition", params=params
            )
    return None


def _extract_statistics(text: str) -> ChemistryIntent | None:
    if re.search(r"\bstandard error\b", text, re.IGNORECASE):
        samples = _number_list(text)
        if len(samples) >= 2:
            return ChemistryIntent(
                kind="analytical", chemistry_op="standard_error", samples=samples
            )
    if re.search(r"\bstandard deviation\b", text, re.IGNORECASE) and not re.search(
        r"\brelative standard deviation\b", text, re.IGNORECASE
    ):
        samples = _number_list(text)
        if len(samples) >= 2:
            return ChemistryIntent(
                kind="analytical", chemistry_op="standard_deviation", samples=samples
            )
    if re.search(r"\bpercent error\b", text, re.IGNORECASE):
        experimental = _search(rf"experimental\s*=\s*({_N})", text)
        accepted = _search(rf"accepted\s*=\s*({_N})", text)
        params = _floats(experimental=experimental, accepted=accepted)
        if params is not None:
            return ChemistryIntent(kind="analytical", chemistry_op="percent_error", params=params)
    if re.search(r"\brelative uncertainty\b", text, re.IGNORECASE):
        params = _floats(
            a=_search(rf"\ba\s*=\s*({_N})", text),
            da=_search(rf"\bda\s*=\s*({_N})", text),
            b=_search(rf"\bb\s*=\s*({_N})", text),
            db=_search(rf"\bdb\s*=\s*({_N})", text),
        )
        if params is not None:
            return ChemistryIntent(
                kind="analytical", chemistry_op="relative_uncertainty", params=params
            )
    if re.search(r"\b(?:retention factor|\bRf\b)\b", text, re.IGNORECASE):
        spot = _search(rf"spot\s*=\s*({_N})", text)
        front = _search(rf"(?:solvent front|front)\s*=\s*({_N})", text)
        if spot is not None and front is not None:
            return ChemistryIntent(
                kind="analytical",
                chemistry_op="chromatography_rf",
                params={"spot": spot, "front": front},
            )
    return None


def _labeled(text: str, label: str) -> float | None:
    return _search(rf"\b{label}\s*=\s*({_N})", text)


def _extract_detection_limit(text: str) -> ChemistryIntent | None:
    quantitation = re.search(
        r"\b(?:LOQ|limit of quantitation|limit of quantification)\b", text, re.IGNORECASE
    )
    detection = re.search(r"\b(?:LOD|limit of detection|detection limit)\b", text, re.IGNORECASE)
    if quantitation is None and detection is None:
        return None
    slope = _search(rf"\b(?:slope|m)\s*=\s*({_N})", text)
    deviation = _search(rf"\b(?:standard deviation|sd|s)\s*=\s*({_N})", text)
    if slope is None or deviation is None:
        return None
    return ChemistryIntent(
        kind="analytical",
        chemistry_op="loq" if quantitation is not None else "lod",
        params={"slope": slope, "sd": deviation},
    )


def _extract_column(text: str) -> ChemistryIntent | None:
    if re.search(r"\bplate height\b", text, re.IGNORECASE):
        length = _search(rf"\b(?:L|length)\s*=\s*({_N})", text)
        plates = _labeled(text, "N")
        if length is None or plates is None:
            return None
        return ChemistryIntent(
            kind="analytical",
            chemistry_op="plate_height",
            params={"length": length, "plates": plates},
        )
    if re.search(r"\b(?:plate number|theoretical plates)\b", text, re.IGNORECASE):
        retention = _labeled(text, "tR")
        width = _search(rf"\b(?:baseline width|width|w)\s*=\s*({_N})", text)
        if retention is None or width is None:
            return None
        return ChemistryIntent(
            kind="analytical",
            chemistry_op="plate_number",
            params={"tr": retention, "width": width},
        )
    if re.search(r"(?<![A-Za-z])Rs(?![A-Za-z])|\bpeak resolution\b", text):
        earlier = _labeled(text, "tR1")
        later = _labeled(text, "tR2")
        first_width = _labeled(text, "w1")
        second_width = _labeled(text, "w2")
        if earlier is None or later is None or first_width is None or second_width is None:
            return None
        return ChemistryIntent(
            kind="analytical",
            chemistry_op="resolution",
            params={
                "tr1": earlier,
                "tr2": later,
                "w1": first_width,
                "w2": second_width,
            },
        )
    if re.search(r"\b(?:selectivity|separation factor)\b", text, re.IGNORECASE):
        first = _labeled(text, "k1")
        second = _labeled(text, "k2")
        if first is not None and second is not None:
            return ChemistryIntent(
                kind="analytical",
                chemistry_op="selectivity",
                params={"k1": first, "k2": second},
            )
        earlier = _labeled(text, "tR1")
        later = _labeled(text, "tR2")
        dead = _labeled(text, "tM")
        if earlier is None or later is None or dead is None:
            return None
        return ChemistryIntent(
            kind="analytical",
            chemistry_op="selectivity",
            params={"tr1": earlier, "tr2": later, "tm": dead},
        )
    if re.search(r"\bcapacity factor\b", text, re.IGNORECASE):
        retention = _labeled(text, "tR")
        dead = _labeled(text, "tM")
        if retention is None or dead is None:
            return None
        return ChemistryIntent(
            kind="analytical",
            chemistry_op="capacity_factor",
            params={"tr": retention, "tm": dead},
        )
    return None


def _number_list(text: str) -> list[float]:
    """The delimited list of plain numbers after ``:`` or ``of``; empty if anything else is in it.

    Counts and charges elsewhere in the sentence ("5 measurements", ``Cu2+``) are not data.
    """
    colon = text.find(":")
    if colon >= 0:
        tail = text[colon + 1 :]
    else:
        marker = re.search(r"\bof\b", text, re.IGNORECASE)
        tail = text[marker.end() :] if marker else text
    tokens = [
        token
        for token in re.split(r"[,;\s]+", tail.strip(" .?!"))
        if token and token.lower() not in {"and", "&"}
    ]
    if not tokens or not all(re.fullmatch(_N, token) for token in tokens):
        return []
    return [float(token) for token in tokens]
