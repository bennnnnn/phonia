"""A question about a written equation: balance it, its K or Q, or the moles it relates."""

from __future__ import annotations

import re
from dataclasses import replace

from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.extractors.parsing import (
    _N,
    _target,
    asked_quantity,
)
from app.modules.chemistry.request import CHEMICAL_FORMULA, EQUATION_RE, FORMULA_END
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.half_reaction import is_single_redox_change
from app.modules.chemistry.species import counts_in_mass_action, parse_reaction

_ACIDIC = re.compile(r"\b(?:acidic|in acid|an?\s+acid)\b", re.IGNORECASE)
_BASIC = re.compile(r"\b(?:basic|alkaline|in base|an?\s+base)\b", re.IGNORECASE)
# A misspelt "balance" ("balence", "ballance") is still the request.
_BALANCE_WORD = r"bal+[ae]nce[ds]?"
_BALANCE_REQUEST = re.compile(
    rf"\b(?:{_BALANCE_WORD}|coefficients?|half[- ]reactions?)\b", re.IGNORECASE
)


def _amounts(text: str) -> dict[str, float]:
    return {
        match.group(2): float(match.group(1))
        for match in re.finditer(
            rf"({_N})\s*mol(?:e|es)?(?:\s+of)?\s+({CHEMICAL_FORMULA}){FORMULA_END}",
            text,
            re.IGNORECASE,
        )
    }


def extract_equations(text: str) -> ChemistryIntent | None:
    match = EQUATION_RE.search(text)
    if match is None or re.search(r"\bnuclear\b", text, re.IGNORECASE):
        return None
    equation = match.group(1).strip()
    if re.search(r"\b(?:is|are|check|verify)\b[^?]{0,80}\bbalanced\b", text, re.IGNORECASE):
        return ChemistryIntent(
            kind="equations", chemistry_op="balance", equation=equation, target="check"
        )
    half = _half_reaction(text, equation)
    if half is not None:
        return half
    if re.search(rf"\b(?:{_BALANCE_WORD}|coefficient)\b", text, re.IGNORECASE):
        return ChemistryIntent(kind="equations", chemistry_op="balance", equation=equation)
    if re.search(r"\b(?:Kc|equilibrium constant|reaction quotient|Qc)\b", text, re.IGNORECASE):
        concentrations = {
            species: float(value)
            for species, value in re.findall(
                rf"\[({CHEMICAL_FORMULA})\]\s*=\s*({_N})\s*(?:M|mol/L)?",
                text,
                re.IGNORECASE,
            )
        }
        balanced = balance_equation(equation)

        normalized: dict[str, float] = {}
        if balanced.balanced:
            for species in (*balanced.reactants, *balanced.products):
                if not counts_in_mass_action(species):
                    continue
                value = concentrations.get(species)
                if value is None and "(" in species:
                    value = concentrations.get(species[: species.rfind("(")])
                if value is None:
                    normalized = {}
                    break
                normalized[species] = value
        if normalized:
            op = (
                "reaction_quotient"
                if re.search(r"\b(?:reaction quotient|Qc)\b", text, re.IGNORECASE)
                else "equilibrium_constant"
            )
            return ChemistryIntent(
                kind="equilibrium", chemistry_op=op, equation=equation, species=normalized
            )
    if _asks_amount(text) and re.search(
        r"\b(?:how much|how many|moles? of|limiting reagent|stoichiometr)\b", text, re.IGNORECASE
    ):
        amounts = _amounts(text)
        target = _target(text, equation)
        balanced = balance_equation(equation)
        if target and target not in balanced.products:
            # A reactant asked from another species' moles: the ratio chain answers it.
            return _moles_of_reactant(text, equation, target, amounts)
        if target and "limiting" in text.lower() and len(amounts) >= 2:
            return ChemistryIntent(
                kind="stoichiometry",
                chemistry_op="limiting_reagent",
                equation=equation,
                target=target,
                species=amounts,
            )
        reactants = balanced.reactants
        known = {formula: amount for formula, amount in amounts.items() if formula in reactants}
        if (
            target
            and len(known) == 1
            and not re.search(
                r"\b(?:grams?|molecules|particles|atoms|liters?|litres?)\b",
                text,
                re.IGNORECASE,
            )
        ):
            return ChemistryIntent(
                kind="stoichiometry",
                chemistry_op="stoichiometry",
                equation=equation,
                target=target,
                species=known,
            )
    return None


def _moles_of_reactant(
    text: str, equation: str, target: str, amounts: dict[str, float]
) -> ChemistryIntent | None:
    """ "How many moles of O2 are needed to burn 3.0 mol of CH4?": one other species' moles."""
    known = {formula: amount for formula, amount in amounts.items() if formula != target}
    if (
        len(known) != 1
        or len(amounts) != 1
        or re.search(
            r"\b(?:grams?|molecules|particles|atoms|liters?|litres?)\b", text, re.IGNORECASE
        )
    ):
        return None
    return ChemistryIntent(
        kind="stoichiometry",
        chemistry_op="mass_stoichiometry",
        equation=equation,
        target=target,
        species=known,
        units={"known": "mol", "find": "mol"},
    )


# "How much heat is released when 3.0 mol of H2 burns?" names a mole amount but asks for an
# energy: the mole ratio answers a different question.
_OTHER_ASK = re.compile(
    r"\b(?:how\s+much|what|find|calculate|determine)\s+(?:is\s+)?(?:the\s+)?"
    r"(?:heat|energy|enthalpy|work|temperature|pressure|volume|concentration|molarity|time)\b"
    r"|\bhow\s+(?:long|hot|fast)\b",
    re.IGNORECASE,
)


def _asks_amount(text: str) -> bool:
    """The question asks for an amount a mole ratio gives, not a heat or a volume."""
    if _OTHER_ASK.search(text):
        return False
    asked = asked_quantity(text)
    return asked is None or asked.unit in {None, "mol"}


def _half_reaction(text: str, equation: str) -> ChemistryIntent | None:
    """One written pair plus an acidic or basic medium. Anything wider stays unread."""
    if _BALANCE_REQUEST.search(text) is None:
        return None
    acidic = _ACIDIC.search(text) is not None
    basic = _BASIC.search(text) is not None
    if acidic == basic:
        return None
    reaction = parse_reaction(equation)
    if reaction is None or len(reaction.reactants) != 1 or len(reaction.products) != 1:
        return None
    # Water, H+, and OH- may be the pair itself (O2 -> H2O, H+ -> H2). Electrons
    # already written belong to the ordinary balancer.
    if any(term.species.electron for term in (*reaction.reactants, *reaction.products)):
        return None
    left = replace(reaction.reactants[0].species, phase=None)
    right = replace(reaction.products[0].species, phase=None)
    # A pair whose oxidation numbers do not change is an ordinary balance.
    if is_single_redox_change(left, right) is False:
        return None
    return ChemistryIntent(
        kind="equations",
        chemistry_op="half_reaction",
        equation=equation,
        target="acidic" if acidic else "basic",
    )
