"""The anchor points of a titration curve: start, half-equivalence and equivalence."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.scene import TitrationAnchor, TitrationScene
from app.modules.chemistry.solvers.constants import KW, PKW, weak_dissociation
from app.modules.chemistry.solvers.display import num, p_value
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

# pH = pKa only while [H+] = Ka is a small fraction of the buffer concentration.
_HALF_EQ_ION_FRACTION = 0.05


_ION_SEARCH_STEPS = 80


def with_titration_scene(
    intent: ChemistryIntent, result: ChemistryResult, *, region: str, detail: str
) -> ChemistryResult:
    anchors = [
        anchor
        for anchor in (_start(intent), _half(intent), _equivalence(intent))
        if anchor is not None
    ]
    anchors.append(TitrationAnchor(label="solved", detail=detail, value=result.answer_value))
    return replace(
        result,
        scene=TitrationScene(title="Titration", region=region, anchors=anchors),
    )


def _amounts(intent: ChemistryIntent) -> tuple[float, float, float] | None:
    ma = intent.params.get("ma")
    va = intent.params.get("va_l")
    mb = intent.params.get("mb")
    if ma is None or va is None or mb is None or min(ma, va, mb) <= 0:
        return None
    return ma, va, mb


def _start(intent: ChemistryIntent) -> TitrationAnchor | None:
    amounts = _amounts(intent)
    ka = intent.params.get("ka")
    kb = intent.params.get("kb")
    if amounts is None:
        return None
    ma, _, mb = amounts
    if ka is not None and ka > 0:
        ph = _safeph_text(lambda: weak_dissociation(ka, ma))
    elif kb is not None and kb > 0:
        ph = _safeph_text(lambda: weak_dissociation(kb, mb), basic=True)
    else:
        ph = p_value(-math.log10(ma))
    return TitrationAnchor(label="start", ph=ph, volume="0 L") if ph else None


def half_equivalence_ion(constant: float, concentration: float) -> tuple[float, bool]:
    """The ion at half-equivalence, and whether pH = pKa (or pOH = pKb) still holds.

    The second value is true when that ion is under 5% of the buffer concentration.
    Otherwise the root is the charge-balance form of that equality.
    """
    if concentration <= 0 or constant <= 0:
        raise SolveServiceError("half-equivalence needs a positive buffer concentration")
    if constant < _HALF_EQ_ION_FRACTION * concentration:
        return constant, True
    lo = min(constant, concentration) * 1e-6
    hi = max(constant, concentration)
    for _ in range(_ION_SEARCH_STEPS):
        ion = (lo + hi) / 2
        other = KW / ion
        left = ion * (concentration + ion - other)
        right = constant * (concentration - ion + other)
        if left > right:
            hi = ion
        else:
            lo = ion
    return (lo + hi) / 2, False


def _half_equivalence_ph(constant: float, concentration: float, *, basic: bool) -> str:
    amount, approximate = half_equivalence_ion(constant, concentration)
    if approximate:
        value = PKW + math.log10(constant) if basic else -math.log10(constant)
    else:
        value = PKW + math.log10(amount) if basic else -math.log10(amount)
    return p_value(value)


def _half(intent: ChemistryIntent) -> TitrationAnchor | None:
    amounts = _amounts(intent)
    ka = intent.params.get("ka")
    kb = intent.params.get("kb")
    if amounts is None:
        return None
    ma, va, mb = amounts
    if ka is not None and ka > 0:
        half_volume = ma * va / (2 * mb)
        buffer = (ma * va / 2) / (va + half_volume)
        return TitrationAnchor(
            label="half-equivalence",
            ph=_half_equivalence_ph(ka, buffer, basic=False),
            volume=f"{num(half_volume)} L",
        )
    base_volume = intent.params.get("vb_l")
    if kb is not None and kb > 0 and base_volume is not None and base_volume > 0:
        half_volume = mb * base_volume / (2 * ma)
        buffer = (mb * base_volume / 2) / (base_volume + half_volume)
        return TitrationAnchor(
            label="half-equivalence",
            ph=_half_equivalence_ph(kb, buffer, basic=True),
            volume=f"{num(half_volume)} L",
        )
    return None


def _equivalence(intent: ChemistryIntent) -> TitrationAnchor | None:
    amounts = _amounts(intent)
    if amounts is None:
        return None
    ma, va, mb = amounts
    ka = intent.params.get("ka")
    kb = intent.params.get("kb")
    if kb is not None and ka is None:
        base_volume = intent.params.get("vb_l")
        if base_volume is None or base_volume <= 0:
            return None
        titrant = mb * base_volume / ma
        salt = (mb * base_volume) / (titrant + base_volume)
        ph = _safeph_text(lambda: weak_dissociation(KW / kb, salt))
    else:
        titrant = ma * va / mb
        if ka is not None and ka > 0:
            salt = (ma * va) / (va + titrant)
            ph = _safeph_text(lambda: weak_dissociation(KW / ka, salt), basic=True)
        else:
            ph = p_value(7.0)
    if ph is None:
        return None
    return TitrationAnchor(label="equivalence", ph=ph, volume=f"{num(titrant)} L")


def _safeph_text(root: Callable[[], float], *, basic: bool = False) -> str | None:
    try:
        amount = root()
    except SolveServiceError:
        return None
    if amount <= 0:
        return None
    value = PKW + math.log10(amount) if basic else -math.log10(amount)
    return p_value(value)
