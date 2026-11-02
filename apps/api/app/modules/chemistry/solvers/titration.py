# ruff: noqa: RUF001 -- textbook chemistry uses multiplication and minus signs.
"""Strong and weak titration regions."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.acid_base import (
    ph_text,
)
from app.modules.chemistry.solvers.constants import KW, PKW, weak_dissociation
from app.modules.chemistry.solvers.display import inp, num, p_value, verified
from app.modules.chemistry.solvers.params import require
from app.modules.chemistry.solvers.titration_curve import half_equivalence_ion, with_titration_scene
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

# Volumes and moles are typed decimals, so equal amounts differ only by float noise.
_TOLERANCE = 1e-9

# [H+] once water's own ions are counted, from c, the strong acid left over (negative when
# base is left over). It keeps a 1e-8 M excess near pH 7 instead of at pH 8.
_WITH_WATER = "[H+] = (c + √(c^2 + 4Kw)) / 2"


def _with_water_line(net: float, hydrogen: float) -> str:
    """The step that counts water's own ions, with c named; it read as an unexplained "net"."""
    left = (
        f"{num(net)} mol/L of acid left over" if net >= 0 else f"{num(net)} mol/L (base left over)"
    )
    return f"With water's own ions, {_WITH_WATER} = {num(hydrogen)} mol/L, where c = {left}"


def _titration_moles(intent: ChemistryIntent) -> tuple[float, float, float, float | None]:
    ma = require(intent, "ma", positive=True)
    va = require(intent, "va_l", positive=True)
    mb = require(intent, "mb", positive=True)
    vb = intent.params.get("vb_l")
    if vb is not None and vb < 0:
        raise SolveServiceError("Vb cannot be negative")
    return ma, va, mb, vb


def solve_titration_strong(intent: ChemistryIntent) -> ChemistryResult:
    ma, va, mb, vb = _titration_moles(intent)
    if vb is None:
        volume = ma * va / mb
        shown = f"Vb = {num(volume)} L"
        return _done(
            intent,
            "Verified strong titration",
            (f"Ma = {inp(ma)} mol/L", f"Va = {inp(va)} L", f"Mb = {inp(mb)} mol/L"),
            "Equivalence volume",
            "Strong acid–strong base equivalence",
            "MaVa = MbVb",
            (f"Vb = ({inp(ma)})({inp(va)}) / {inp(mb)}",),
            shown,
            shown,
            region="equivalence",
            detail=f"equivalence volume {num(volume)} L",
        )
    acid_moles = ma * va
    base_moles = mb * vb
    total = va + vb
    scale = max(acid_moles, base_moles)
    # Net strong acid per litre (negative past equivalence). Solving [H+]^2 - net[H+] - Kw = 0
    # keeps water's own ions in the answer, so pH 7 at equivalence and no absurd pH 7.7
    # a hair before it.
    net = (acid_moles - base_moles) / total
    hydrogen = (net + math.sqrt(net * net + 4 * KW)) / 2
    lines = [
        f"n(H+) = MaVa = ({inp(ma)})({inp(va)}) = {num(acid_moles)} mol",
        f"n(OH-) = MbVb = ({inp(mb)})({inp(vb)}) = {num(base_moles)} mol",
        f"V = Va + Vb = {inp(va)} + {inp(vb)} = {num(total)} L",
    ]
    if abs(acid_moles - base_moles) <= _TOLERANCE * scale:
        ph = p_value(7.0)
        region = "equivalence"
        detail = "equivalence: pH = 7 at 25 °C"
        lines.append("n(H+) = n(OH-), only water's own ions remain, so pH = 7 at 25 °C")
    else:
        ph = ph_text(hydrogen)
        if acid_moles > base_moles:
            region = "before equivalence"
            detail = f"before equivalence: [H+] = {num(hydrogen)}"
            lines.append(f"[H+] = (n(H+) − n(OH-)) / V = {num(net)} mol/L")
        else:
            region = "after equivalence"
            detail = f"after equivalence: [OH-] = {num(-net)}"
            lines.append(f"[OH-] = (n(OH-) − n(H+)) / V = {num(-net)} mol/L")
        lines.append(_with_water_line(net, hydrogen))
        lines.append(f"pH = −log10({num(hydrogen)}) = {ph}")
    return _done(
        intent,
        "Verified strong titration",
        (
            f"Ma = {inp(ma)} mol/L",
            f"Va = {inp(va)} L",
            f"Mb = {inp(mb)} mol/L",
            f"Vb = {inp(vb)} L",
        ),
        "pH",
        *stated("titration_strong"),
        lines,
        f"pH = {ph}",
        ph,
        region=region,
        detail=detail,
    )


def solve_titration_weak(intent: ChemistryIntent) -> ChemistryResult:
    if intent.params.get("kb") is not None and intent.params.get("ka") is None:
        return _weak_titration(intent, acid=False)
    return _weak_titration(intent, acid=True)


def _weak_titration(intent: ChemistryIntent, *, acid: bool) -> ChemistryResult:
    """A weak acid titrated by strong base, or (``acid=False``) a weak base by strong acid.

    The two are mirror images: swap H+ with OH-, Ka with Kb, and pH with pOH. The weak-acid
    case reads Ma/Va as the analyte; the weak-base case reads Mb/Vb as the base and Ma/Va as
    the strong acid that is added.
    """
    ma, va, mb, vb = _titration_moles(intent)
    if vb is None:
        raise SolveServiceError("weak titration needs the added volume")
    if acid:
        constant = require(intent, "ka", positive=True)
        symbol, weak, conj, titrant = "Ka", "HA", "A-", "OH-"
        analyte_moles, titrant_moles = ma * va, mb * vb
        analyte_name = f"n(HA) = MaVa = ({inp(ma)})({inp(va)})"
        titrant_name = f"n(OH-) = MbVb = ({inp(mb)})({inp(vb)})"
        analyte_conc = ma
    else:
        constant = require(intent, "kb", positive=True)
        symbol, weak, conj, titrant = "Kb", "B", "BH+", "H+"
        analyte_moles, titrant_moles = mb * vb, ma * va
        analyte_name = f"n(B) = MbVb = ({inp(mb)})({inp(vb)})"
        titrant_name = f"n(H+) = MaVa = ({inp(ma)})({inp(va)})"
        analyte_conc = mb
    total = va + vb
    p_constant = -math.log10(constant)
    p_name = "pKa" if acid else "pKb"
    scale = max(analyte_moles, titrant_moles)

    lines = [
        f"{analyte_name} = {num(analyte_moles)} mol",
        f"{titrant_name} = {num(titrant_moles)} mol",
        f"V = {inp(va)} + {inp(vb)} = {num(total)} L",
    ]
    ph_of_p = (lambda p: p) if acid else (lambda p: PKW - p)  # pH from pKa, or from pKb via pOH
    if abs(titrant_moles - analyte_moles / 2) <= _TOLERANCE * scale:
        buffer = (analyte_moles / 2) / total
        amount, approximate = half_equivalence_ion(constant, buffer)
        ion = "H+" if acid else "OH-"
        k_name = "Ka" if acid else "Kb"
        region = "half-equivalence"
        lines.append(f"{p_name} = −log10({inp(constant)}) = {p_value(p_constant)}")
        if approximate:
            ph = p_value(ph_of_p(p_constant))
            detail = f"half-equivalence: {'pH = pKa' if acid else 'pOH = pKb'}"
            formula = "pH = pKa" if acid else "pOH = pKb"
            pkb = p_value(p_constant)
            lines.append(
                f"n({titrant}) = n({weak}) / 2, so {conj} = {weak} and "
                + (f"pH = pKa = {ph}" if acid else f"pOH = pKb = {pkb}, pH = {PKW} − {pkb} = {ph}")
            )
        else:
            ph = p_value(ph_of_p(-math.log10(amount)))
            detail = f"half-equivalence: [{ion}] from charge balance"
            partner = "OH−" if acid else "H+"
            formula = (
                f"[{ion}] = {k_name} (C − [{ion}] + [{partner}]) / (C + [{ion}] − [{partner}])"
            )
            lines.append(f"n({titrant}) = n({weak}) / 2, so {conj} = {weak} = {num(buffer)} mol/L")
            lines.append(f"{formula} = {num(amount)} mol/L")
            if acid:
                lines.append(f"pH = −log10({num(amount)}) = {ph}")
            else:
                poh = p_value(-math.log10(amount))
                lines.append(f"pOH = −log10({num(amount)}) = {poh}")
                lines.append(f"pH = {PKW} − {poh} = {ph}")
    elif titrant_moles == 0:
        amount = weak_dissociation(constant, analyte_conc)
        governing = "H+" if acid else "OH-"
        lines.append(f"{symbol} = x^2 / (C − x), C = {inp(analyte_conc)} mol/L")
        lines.append(f"[{governing}] = x = {num(amount)} mol/L")
        ph = p_value(-math.log10(amount) if acid else PKW + math.log10(amount))
        region = "start"
        detail = f"before titrant is added: [{governing}] = {num(amount)}"
        formula = f"{symbol} = x^2 / (C − x)"
    elif titrant_moles < analyte_moles - _TOLERANCE * scale:
        remaining = analyte_moles - titrant_moles
        offset = math.log10(titrant_moles / remaining)
        ph_value = p_constant + offset
        ph = p_value(ph_value if acid else PKW - ph_value)
        region = "buffer region"
        detail = f"buffer: [{conj}]/[{weak}] = {num(titrant_moles)} / {num(remaining)}"
        formula = (
            f"pH = pKa + log10([{conj}]/[{weak}])"
            if acid
            else (f"pOH = pKb + log10([{conj}]/[{weak}])")
        )
        lines.append(f"{p_name} = −log10({inp(constant)}) = {p_value(p_constant)}")
        lines.append(f"n({conj}) = n({titrant}) = {num(titrant_moles)} mol")
        lines.append(
            f"n({weak}) = {num(analyte_moles)} − {num(titrant_moles)} = {num(remaining)} mol"
        )
        ratio = f"{num(titrant_moles)} / {num(remaining)}"
        if acid:
            lines.append(f"pH = {p_value(p_constant)} + log10({ratio}) = {ph}")
        else:
            lines.append(f"pOH = {p_value(p_constant)} + log10({ratio}) = {p_value(ph_value)}")
            lines.append(f"pH = {PKW} − {p_value(ph_value)} = {ph}")
    elif abs(titrant_moles - analyte_moles) <= _TOLERANCE * scale:
        salt = analyte_moles / total
        conj_constant = KW / constant
        amount = weak_dissociation(conj_constant, salt)
        produced = "OH-" if acid else "H+"
        lines.append(f"[{conj}] = {num(analyte_moles)} / {num(total)} = {num(salt)} mol/L")
        conj_symbol = "Kb" if acid else "Ka"
        k_conj = num(conj_constant)
        lines.append(f"{conj_symbol} = Kw / {symbol} = ({num(KW)}) / ({inp(constant)}) = {k_conj}")
        lines.append(f"x^2 + ({k_conj})x − ({k_conj})({num(salt)}) = 0")
        lines.append(f"[{produced}] = x = {num(amount)} mol/L")
        ph = p_value(PKW + math.log10(amount) if acid else -math.log10(amount))
        region = "equivalence"
        detail = f"equivalence: [{conj}] = {num(salt)}, {conj_symbol} = Kw/{symbol}"
        formula = f"{conj_symbol} = Kw / {symbol}"
    else:
        excess = (titrant_moles - analyte_moles) / total
        # Excess strong titrant is the net strong ion. The water quadratic
        # keeps a 1e-8 M excess near pH 7.
        net = -excess if acid else excess
        hydrogen = (net + math.sqrt(net * net + 4 * KW)) / 2
        ph = ph_text(hydrogen)
        region = "after equivalence"
        ion = "OH-" if acid else "H+"
        detail = f"after equivalence: [{ion}] = {num(excess)}"
        formula = _WITH_WATER
        lines.append(
            f"[{ion}] = ({num(titrant_moles)} − {num(analyte_moles)}) / {num(total)} = "
            f"{num(excess)} mol/L"
        )
        lines.append(_with_water_line(net, hydrogen))
        lines.append(f"pH = −log10({num(hydrogen)}) = {ph}")
    return _done(
        intent,
        "Verified weak titration" if acid else "Verified weak-base titration",
        (
            f"Ma = {inp(ma)} mol/L",
            f"Va = {inp(va)} L",
            f"Mb = {inp(mb)} mol/L",
            f"Vb = {inp(vb)} L",
            f"{symbol} = {inp(constant)}",
        ),
        "pH",
        "Weak acid–strong base titration" if acid else "Weak base–strong acid titration",
        formula,
        lines,
        f"pH = {ph}",
        ph,
        region=region,
        detail=detail,
    )


def _done(
    intent: ChemistryIntent,
    title: str,
    given: tuple[str, ...] | list[str],
    find: str,
    formula_name: str,
    formula: str,
    substitution: tuple[str, ...] | list[str],
    answer: str,
    value: str,
    *,
    region: str,
    detail: str,
) -> ChemistryResult:
    return with_titration_scene(
        intent,
        verified(title, given, find, formula_name, formula, substitution, answer, value),
        region=region,
        detail=detail,
    )
