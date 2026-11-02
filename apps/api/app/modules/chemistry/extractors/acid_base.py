"""pH, pOH and acid strength: a solution's acidity from its concentration or its constant."""

from __future__ import annotations

import math
import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    _search,
)
from app.modules.chemistry.request import CHEMICAL_FORMULA, FORMULA_END
from app.modules.chemistry.schemas import ChemistryIntent
from app.services.law_binding.ask import ask_clause


def _extract_ph(text: str) -> ChemistryIntent | None:
    # pH has to be what was asked. A stated pH beside [H+] is a given, so a
    # conjugate-fraction question is not answered as pH = 4.
    asked = ask_clause(text) or ""
    h = _search(rf"\[H\+?\]\s*=\s*({_N})", text, flags=0)
    if h is not None and re.search(r"\bpH\b", asked):
        return ChemistryIntent(kind="acid_base", chemistry_op="ph_from_h", params={"h": h})
    oh = _search(rf"\[OH-?\]\s*=\s*({_N})", text, flags=0)
    if oh is not None and re.search(r"\bpOH\b", asked):
        return ChemistryIntent(kind="acid_base", chemistry_op="poh_from_oh", params={"oh": oh})
    poh = _search(rf"\bpOH\s*=\s*({_N})", text)
    if poh is not None and re.search(r"\bpH\b", text):
        return ChemistryIntent(kind="acid_base", chemistry_op="ph_from_poh", params={"poh": poh})
    # "pH = 4.75", "a pH of 4.75", "pH 4.75"; never "the pH of 0.01 M HCl".
    ph = _search(rf"\bpH\s*(?:=|of|is|:)?\s*({_N})(?!\s*(?:M|mM|mol)\b)(?![\d.])", text)
    if ph is not None and re.search(r"\[H\+?\]|hydrogen ion", text, re.IGNORECASE):
        return ChemistryIntent(kind="acid_base", chemistry_op="h_from_ph", params={"ph": ph})
    if re.search(r"\b(?:buffer|Henderson)\b", text, re.IGNORECASE):
        pka = _search(rf"\bpK(?:a|ₐ)\s*=\s*({_N})", text)
        base = _search(rf"\[(?:A-|A⁻|base)\]\s*=\s*({_N})", text)
        acid = _search(rf"\[(?:HA|acid)\]\s*=\s*({_N})", text)
        if pka is not None and base is not None and acid is not None:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="buffer_ph",
                params={"pka": pka, "base": base, "acid": acid},
            )
    return None


_AMPHIPROTIC = re.compile(r"\bamphiprotic\b|\bintermediate form\b", re.IGNORECASE)
_SPECIATION = re.compile(
    r"\b(?:speciation|charge[- ]balance|every species|all species)\b", re.IGNORECASE
)
# Superscript 2 + superscript minus is the typeset charge. Mixed keyboard forms stay too.
_SUP2 = "\u00b2"
_SUP_MINUS = "\u207b"
_UNI_MINUS = "\u2212"
_A2_CHARGE = r"(?:\^2-|2-|" + _SUP2 + _SUP_MINUS + r"|" + _SUP2 + r"-|2" + _UNI_MINUS + r")"
_A2_SPECIES = r"\[A" + _A2_CHARGE + r"\]|(?<![A-Za-z])A" + _A2_CHARGE + r"(?![A-Za-z0-9])"
_A2_BODY = _A2_SPECIES + r"|fully deprotonated"
# The ask names this concentration. "concentration of H+ ... forms A2-" does not.
_A2_ASK = re.compile(
    r"(?:"
    r"(?:what|find|calculate|determine)\s+(?:is\s+)?(?:the\s+)?"
    r"(?:(?:concentration|molarity)\s+)?(?:of\s+)?(?:the\s+)?"
    r"|(?:concentration|molarity)\s+of\s+(?:the\s+)?"
    r")(?:" + _A2_BODY + r")",
    re.IGNORECASE,
)
_KA_STEP = {"1": "1", "2": "2", "₁": "1", "₂": "2"}


def _step_constants(text: str) -> dict[str, float]:
    """pKa1, Ka2, and the same labels with a subscript 1 or 2."""
    found: dict[str, float] = {}
    for match in re.finditer(
        rf"(?<![A-Za-z0-9])(p?Ka)\s*([12₁₂])\s*=\s*({_N})",
        text,
        re.IGNORECASE,
    ):
        kind = "pka" if match.group(1).lower().startswith("p") else "ka"
        found[f"{kind}{_KA_STEP[match.group(2)]}"] = float(match.group(3))
    return found


def _pka_pair(found: dict[str, float]) -> tuple[float, float] | None:
    def one(index: str) -> float | None:
        pka = found.get(f"pka{index}")
        if pka is not None:
            return pka
        ka = found.get(f"ka{index}")
        if ka is None or ka <= 0:
            return None
        return -math.log10(ka)

    first, second = one("1"), one("2")
    if first is None or second is None:
        return None
    return first, second


def _stated_molarity(text: str) -> float | None:
    match = re.search(rf"({_N})\s*M(?![A-Za-z])", text)
    return None if match is None else float(match.group(1))


def _with_concentration(text: str, params: dict[str, float]) -> dict[str, float]:
    molarity = _stated_molarity(text)
    if molarity is not None:
        params["concentration"] = molarity
    return params


def _asks_for_a2(text: str) -> bool:
    if _SPECIATION.search(text):
        return False
    asked = _A2_ASK.search(text)
    if asked is None:
        return False
    # "[A2-] = 1e-6" states the concentration. It does not ask for it.
    return re.match(r"\s*=", text[asked.end() :]) is None


def _extract_acid_solution(text: str) -> ChemistryIntent | None:
    if _AMPHIPROTIC.search(text):
        found = _step_constants(text)
        pka_values = _pka_pair(found)
        if pka_values is None or re.search(r"\bpH\b", text) is None:
            return None
        params = {"pka1": pka_values[0], "pka2": pka_values[1]}
        for key in ("ka1", "ka2"):
            if key in found and f"p{key}" not in found:
                params[key] = found[key]
        return ChemistryIntent(
            kind="acid_base",
            chemistry_op="amphiprotic_ph",
            params=_with_concentration(text, params),
        )
    if _asks_for_a2(text):
        ka2 = _step_constants(text).get("ka2")
        if ka2 is not None:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="diprotic_a2",
                params=_with_concentration(text, {"ka2": ka2}),
            )
    if re.search(r"\bweak acid\b", text, re.IGNORECASE):
        pair = _molar_formula(text)
        ka = _search(rf"\bKa\s*=\s*({_N})", text, flags=0)
        if pair and ka is not None:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="weak_acid_ph",
                formula=pair[1],
                params={"concentration": pair[0], "ka": ka},
            )
    if re.search(r"\bweak base\b", text, re.IGNORECASE):
        pair = _molar_formula(text)
        kb = _search(rf"\bKb\s*=\s*({_N})", text, flags=0)
        if pair and kb is not None:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="weak_base_ph",
                formula=pair[1],
                params={"concentration": pair[0], "kb": kb},
            )
    if re.search(r"\bpolyprotic\b", text, re.IGNORECASE):
        pair = _molar_formula(text)
        ka1 = _search(rf"\bKa1\s*=\s*({_N})", text, flags=0)
        if pair and ka1 is not None:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="polyprotic_ph",
                formula=pair[1],
                params={"concentration": pair[0], "ka1": ka1},
            )
    if re.search(r"\bstrong acid\b", text, re.IGNORECASE):
        pair = _molar_formula(text)
        if pair:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="strong_acid_ph",
                formula=pair[1],
                params={"concentration": pair[0]},
            )
    if re.search(r"\bstrong base\b", text, re.IGNORECASE):
        pair = _molar_formula(text)
        if pair:
            return ChemistryIntent(
                kind="acid_base",
                chemistry_op="strong_base_ph",
                formula=pair[1],
                params={"concentration": pair[0]},
            )
    ka = _constant(text, "Ka")
    kb = _constant(text, "Kb")
    if ka is not None and re.search(r"\bpKa\b", text):
        return ChemistryIntent(
            kind="acid_base", chemistry_op="ka_kb", target="pKa", params={"ka": ka}
        )
    if kb is not None and re.search(r"\bpKb\b", text):
        return ChemistryIntent(
            kind="acid_base", chemistry_op="ka_kb", target="pKb", params={"kb": kb}
        )
    if ka is not None and re.search(r"\bKb\b", text, flags=0):
        return ChemistryIntent(
            kind="acid_base", chemistry_op="ka_kb", target="Kb", params={"ka": ka}
        )
    if kb is not None and re.search(r"\bKa\b", text, flags=0):
        return ChemistryIntent(
            kind="acid_base", chemistry_op="ka_kb", target="Ka", params={"kb": kb}
        )
    return None


def _molar_formula(text: str) -> tuple[float, str] | None:
    match = re.search(rf"({_N})\s*M\s+({CHEMICAL_FORMULA}){FORMULA_END}", text)
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def _constant(text: str, symbol: str) -> float | None:
    """A stated Ka or Kb: "Ka = 1.8e-5", "the Kb of NH3 is 1.8e-5", "Ka for HF: 6.8e-4".

    Exactly one value: a second one leaves open which constant the question means.
    """
    values = [
        float(match.group(1))
        for match in re.finditer(
            rf"(?<![A-Za-z]){symbol}(?![A-Za-z0-9])(?:\s+(?:of|for)\s+(?:the\s+)?"
            rf"[A-Za-z0-9()]+(?:\s+(?:acid|ion|base))?)?\s*(?:=|is|was|:)\s*({_N})",
            text,
        )
    ]
    return values[0] if len(values) == 1 else None
