# ruff: noqa: RUF001, RUF002
"""pH, pOH and the acid and base constants: strong, weak, polyprotic and buffered solutions."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import KW, PKW
from app.modules.chemistry.solvers.display import inp, num, p_value, verified
from app.modules.chemistry.solvers.params import positive, require
from app.modules.chemistry.solvers.types import ChemistryResult, format_number
from app.modules.chemistry.species_facts import STRONG_ACIDS, STRONG_BASES
from app.services.solving import SolveServiceError


def solve_acid_base(intent: ChemistryIntent) -> ChemistryResult:
    op = intent.chemistry_op
    if op == "ph_from_h":
        concentration = require(intent, "h", positive=True)
        ph = -math.log10(concentration)
        value = p_value(ph)
        return verified(
            "Verified pH calculation",
            (f"[H+] = {inp(concentration)} mol/L",),
            "pH",
            *stated("ph_from_h"),
            (f"pH = −log10({inp(concentration)})",),
            f"pH = {value}",
            value,
        )
    if op == "ph_from_poh":
        poh = require(intent, "poh")
        ph = PKW - poh
        value = p_value(ph)
        return verified(
            "Verified pH calculation",
            (f"pOH = {inp(poh)}", f"pKw = {PKW} at 25 °C"),
            "pH",
            *stated("ph_from_poh"),
            (f"pH = {PKW} − {inp(poh)}",),
            f"pH = {value}",
            value,
        )
    if op == "h_from_ph":
        ph = require(intent, "ph")
        concentration = 10 ** (-ph)
        value = f"{num(concentration)} mol/L"
        return verified(
            "Verified pH calculation",
            (f"pH = {inp(ph)}",),
            "[H+]",
            *stated("h_from_ph"),
            (f"[H+] = 10^(-{inp(ph)})",),
            f"[H+] = {value}",
            value,
        )
    if op == "poh_from_oh":
        concentration = require(intent, "oh", positive=True)
        poh = -math.log10(concentration)
        value = p_value(poh)
        return verified(
            "Verified pOH calculation",
            (f"[OH-] = {inp(concentration)} mol/L",),
            "pOH",
            *stated("poh_from_oh"),
            (f"pOH = −log10({inp(concentration)})",),
            f"pOH = {value}",
            value,
        )
    if op == "buffer_ph":
        pka = require(intent, "pka")
        base = require(intent, "base", positive=True)
        acid = require(intent, "acid", positive=True)
        ph = pka + math.log10(base / acid)
        value = p_value(ph)
        return verified(
            "Verified buffer pH",
            (
                f"pKa = {inp(pka)}",
                f"[A-] = {inp(base)} mol/L",
                f"[HA] = {inp(acid)} mol/L",
            ),
            "Buffer pH",
            *stated("buffer_ph"),
            (f"pH = {inp(pka)} + log10({inp(base)}/{inp(acid)})",),
            f"pH = {value}",
            value,
        )
    if op == "base_buffer_ph":
        kb = require(intent, "kb", positive=True)
        conjugate = require(intent, "conjugate", positive=True)
        base = require(intent, "base", positive=True)
        pkb = -math.log10(kb)
        poh = pkb + math.log10(conjugate / base)
        ph = PKW - poh
        value = p_value(ph)
        return verified(
            "Verified base-buffer pH",
            (
                f"Kb = {inp(kb)}",
                f"[BH+] = {inp(conjugate)} mol/L",
                f"[B] = {inp(base)} mol/L",
            ),
            "Buffer pH",
            *stated("base_buffer_ph"),
            (
                f"pKb = −log10({inp(kb)}) = {p_value(pkb)}",
                f"pOH = {p_value(pkb)} + log10({inp(conjugate)}/{inp(base)}) = {p_value(poh)}",
                f"pH = {PKW} − {p_value(poh)}",
            ),
            f"pH = {value}",
            value,
        )
    raise SolveServiceError(f"unsupported acid-base operation: {op}")


# Below this, water's own ions are no longer a small correction.
_DILUTE = 1e-6


def ph_text(value: float) -> str:
    return p_value(-math.log10(value))


def solve_strong_acid(intent: ChemistryIntent) -> ChemistryResult:
    formula = intent.formula or ""
    if formula == "H2SO4":
        raise SolveServiceError("H2SO4 is not a simple strong monoprotic acid")
    if formula not in STRONG_ACIDS:
        raise SolveServiceError(
            f"{formula or 'that acid'} is not a supported strong monoprotic acid"
        )
    concentration = require(intent, "concentration", positive=True)
    if concentration < _DILUTE:
        return _dilute_strong(intent, formula, concentration, acid=True)
    ph = ph_text(concentration)
    if intent.chemistry_op == "strong_acid_poh":
        poh = p_value(PKW + math.log10(concentration))
        return verified(
            "Verified strong-acid pOH",
            (f"{formula} = {inp(concentration)} mol/L",),
            "pOH",
            *stated("strong_acid_poh"),
            (
                f"[H+] = {inp(concentration)} mol/L",
                f"pH = −log10({inp(concentration)}) = {ph}",
                f"pOH = {PKW} − {ph}",
            ),
            f"pOH = {poh}",
            poh,
        )
    return verified(
        "Verified strong-acid pH",
        (f"{formula} = {inp(concentration)} mol/L",),
        "pH",
        *stated("strong_acid_ph"),
        (f"[H+] = {inp(concentration)} mol/L", f"pH = −log10({inp(concentration)})"),
        f"pH = {ph}",
        ph,
    )


def solve_strong_base(intent: ChemistryIntent) -> ChemistryResult:
    formula = intent.formula or ""
    factor = STRONG_BASES.get(formula)
    if factor is None:
        raise SolveServiceError(f"{formula or 'that base'} is not a supported strong base")
    concentration = require(intent, "concentration", positive=True)
    hydroxide = factor * concentration
    if hydroxide < _DILUTE:
        return _dilute_strong(intent, formula, concentration, acid=False, factor=factor)
    poh = ph_text(hydroxide)
    ph = p_value(PKW + math.log10(hydroxide))
    hydroxide_law = "[OH-] = C" if factor == 1 else f"[OH-] = {factor}C"
    if intent.chemistry_op == "strong_base_poh":
        return verified(
            "Verified strong-base pOH",
            (f"{formula} = {inp(concentration)} mol/L",),
            "pOH",
            *stated("strong_base_poh"),
            (
                f"[OH-] = {factor} × {inp(concentration)} = {num(hydroxide)} mol/L",
                f"pOH = −log10({num(hydroxide)})",
            ),
            f"pOH = {poh}",
            poh,
        )
    return verified(
        "Verified strong-base pH",
        (f"{formula} = {inp(concentration)} mol/L",),
        "pH",
        stated("strong_base_ph")[0],
        hydroxide_law,
        (
            f"[OH-] = {factor} × {inp(concentration)} = {num(hydroxide)} mol/L",
            f"pOH = −log10({num(hydroxide)}) = {poh}",
            f"pH = {PKW} − {poh} = {ph}",
        ),
        f"pH = {ph}",
        ph,
    )


def _dilute_strong(
    intent: ChemistryIntent,
    formula: str,
    concentration: float,
    *,
    acid: bool,
    factor: int = 1,
) -> ChemistryResult:
    """A strong acid or base too dilute for [H+] = C: water's own ions count.

    Charge balance with Kw gives [H+] = C/2 + √(C²/4 + Kw) for a strong acid (and [OH-] the
    same way for a base), so 1.0 × 10^-8 M HCl is pH 6.98, never the 8.00 of −log10(C).
    """
    ion, other = ("H+", "OH-") if acid else ("OH-", "H+")
    total = factor * concentration
    shown_c = inp(concentration) if factor == 1 else f"{factor} × {inp(concentration)}"
    amount = total / 2 + math.sqrt(total**2 / 4 + KW)
    own = ph_text(amount)
    other_p = p_value(PKW + math.log10(amount))
    ph, poh = (own, other_p) if acid else (other_p, own)
    asked = "pOH" if intent.chemistry_op.endswith("_poh") else "pH"
    value = poh if asked == "pOH" else ph
    # Three figures, so the logarithm of the shown value is the shown pH.
    amount_text = format_number(amount, significant=3)
    working = [
        f"[{ion}] = C/2 + √(C²/4 + Kw), C = {shown_c} mol/L, Kw = {num(KW)}",
        f"[{ion}] = {amount_text} mol/L",
        f"p{ion[:-1]} = −log10({amount_text}) = {own}",
    ]
    if asked != f"p{ion[:-1]}":
        working.append(f"{asked} = {PKW} − {own}")
    return verified(
        f"Verified dilute strong-{'acid' if acid else 'base'} {asked}",
        (f"{formula} = {inp(concentration)} mol/L", f"Kw = {num(KW)} at 25 °C"),
        asked,
        stated(intent.chemistry_op)[0],
        f"[{ion}] = C/2 + √(C²/4 + Kw), with [{other}] = Kw / [{ion}]",
        tuple(working),
        f"{asked} = {value}",
        value,
    )


_CONSTANT_LABELS = {"ka": "Ka", "kb": "Kb", "pka": "pKa", "pkb": "pKb"}


def solve_ka_kb(intent: ChemistryIntent) -> ChemistryResult:
    target = (intent.target or "Kb").strip()
    ka = intent.params.get("ka")
    kb = intent.params.get("kb")
    law_name, base_formula = stated("ka_kb")
    if target == "Kb" and ka is not None:
        source = positive(ka, "Ka")
        value = KW / source
        formula = base_formula
        working = f"Kb = ({num(KW)}) / ({inp(source)})"
    elif target == "Ka" and kb is not None:
        source = positive(kb, "Kb")
        value = KW / source
        formula = "Ka = Kw / Kb"
        working = f"Ka = ({num(KW)}) / ({inp(source)})"
    elif target == "pKa" and ka is not None:
        source = positive(ka, "Ka")
        value = -math.log10(source)
        formula = "pKa = −log10 Ka"
        working = f"pKa = −log10({inp(source)})"
    elif target == "pKb" and kb is not None:
        source = positive(kb, "Kb")
        value = -math.log10(source)
        formula = "pKb = −log10 Kb"
        working = f"pKb = −log10({inp(source)})"
    else:
        raise SolveServiceError("Ka/Kb conversion needs the matching constant and target")
    shown = f"{target} = {p_value(value) if target.startswith('p') else num(value)}"
    uses_kw = target in {"Ka", "Kb"}
    return verified(
        "Verified Ka/Kb conversion",
        tuple(
            f"{_CONSTANT_LABELS.get(key, key)} = {inp(item)}" for key, item in intent.params.items()
        ),
        target,
        law_name,
        formula,
        (f"Kw = {num(KW)} at 25 °C", working) if uses_kw else (working,),
        shown,
        num(value),
    )
