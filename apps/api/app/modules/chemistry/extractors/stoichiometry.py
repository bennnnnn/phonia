"""Multi-step stoichiometry: grams, solution volumes or gas volumes through a balanced equation."""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import (
    _N,
    AskedQuantity,
    _equation,
    _target,
    asked_quantity,
)
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.quantity import to_atm, to_kelvin, to_liters
from app.modules.chemistry.request import CHEMICAL_FORMULA, FORMULA_END
from app.modules.chemistry.schemas import ChemistryIntent

_HOW_MUCH = re.compile(r"\bhow\s+(?:many|much)\b", re.IGNORECASE)
# Units a chain answers in; None is the unit the amount is given in.
_ANSWERED_UNITS = frozenset({None, "g", "mol", "L", "particles"})


def extract_mass_chain(text: str) -> ChemistryIntent | None:
    equation = _equation(text)
    limiting = re.search(r"\blimiting\b", text, re.IGNORECASE) is not None
    asked = _amount_ask(text)
    if equation is None or (asked is None and not limiting):
        return None
    target = _target(text, equation)
    if target is None:
        return None
    if limiting:
        return _limiting_chain(text, equation, target)
    # The answer is in the unit the question head asks for. A head that names only the
    # substance ("how much H2O from 4 g of H2") asks in the unit the amount is given in.
    find_unit = None if asked is None else asked.unit
    grams = _gram_amounts(text)
    two_reactants = _limiting_from_masses(equation, target, grams)
    if two_reactants is not None:
        return two_reactants
    if target in grams:
        # The amount asked is the amount stated: no ratio to apply.
        return None
    if len(grams) == 1:
        return ChemistryIntent(
            kind="stoichiometry",
            chemistry_op="mass_stoichiometry",
            equation=equation,
            target=target,
            species=grams,
            units={"known": "g", "find": find_unit or "g"},
        )
    solution = re.search(
        rf"({_N})\s*L\s+of\s+({_N})\s*M\s+({CHEMICAL_FORMULA}){FORMULA_END}",
        text,
        re.IGNORECASE,
    )
    if solution:
        return ChemistryIntent(
            kind="stoichiometry",
            chemistry_op="solution_stoichiometry",
            equation=equation,
            target=target,
            species={solution.group(3): float(solution.group(1))},
            params={"molarity": float(solution.group(2))},
            units={"known": "solution", "find": find_unit or "mol"},
        )
    gas = re.search(
        rf"({_N})\s*(mL|L)\s+of\s+({CHEMICAL_FORMULA}){FORMULA_END}\s+at\s+"
        rf"({_N})\s*(kPa|Pa|mmHg|torr|atm|bar)\s+and\s+({_N})\s*(°C|C|K)\b",
        text,
    )
    if gas:
        return ChemistryIntent(
            kind="stoichiometry",
            chemistry_op="gas_stoichiometry",
            equation=equation,
            target=target,
            species={gas.group(3): to_liters(float(gas.group(1)), gas.group(2))},
            params={
                "pressure": to_atm(float(gas.group(4)), gas.group(5)),
                "temperature": to_kelvin(
                    float(gas.group(6)), "celsius" if gas.group(7).upper() == "C" else gas.group(7)
                ),
            },
            units={"known": "L", "find": find_unit or "L"},
        )
    counted = _one_amount(
        text,
        rf"({_N})\s*mol(?:e|es)?(?:\s+of)?\s+({CHEMICAL_FORMULA}){FORMULA_END}",
    )
    if counted is not None:
        amount, formula = counted
        return _chain(equation, target, formula, amount, "mol", find_unit or "mol")
    counted = _one_amount(
        text,
        rf"({_N})\s*(?:molecules|particles|atoms)(?:\s+of)?\s+"
        rf"({CHEMICAL_FORMULA}){FORMULA_END}",
    )
    if counted is not None:
        amount, formula = counted
        return _chain(equation, target, formula, amount, "particles", find_unit or "mol")
    return None


def _amount_ask(text: str) -> AskedQuantity | None:
    """The head that asks an amount: "how much H2O", "what mass of H2O", "find the moles of
    O2". No head, no verified answer: "what is H2O" asks nothing a ratio gives.

    The unit is one a chain answers in. Atoms are an element's alone ("atoms of O2" are
    twice its molecules), and "how many H2O" counts moles. Any other unit (mL, kg, two units
    at once) declines rather than take a default.
    """
    asked = asked_quantity(text)
    if asked is None or (asked.unit is None and not _HOW_MUCH.search(text)):
        return None
    if asked.unit == "atoms":
        single = asked.species is not None and parse_formula(asked.species) == {asked.species: 1}
        return AskedQuantity("particles", asked.species) if single else None
    if asked.unit is None and asked.species is not None:
        if re.search(rf"\bhow\s+many\s+{re.escape(asked.species)}\b", text, re.IGNORECASE):
            return AskedQuantity("mol", asked.species)
    return asked if asked.unit in _ANSWERED_UNITS else None


def _limiting_chain(text: str, equation: str, target: str) -> ChemistryIntent | None:
    """A limiting-reagent question: its answer is always a yield in grams."""
    amounts = _gram_amounts(text)
    if len(amounts) >= 2:
        return ChemistryIntent(
            kind="stoichiometry",
            chemistry_op="limiting_mass",
            equation=equation,
            target=target,
            species=amounts,
            units={"known": "g"},
        )
    volumes = re.findall(
        rf"({CHEMICAL_FORMULA})\s*=\s*({_N})\s*L\s*\(\s*({_N})\s*M\s*\)",
        text,
        re.IGNORECASE,
    )
    if len(volumes) >= 2:
        return ChemistryIntent(
            kind="stoichiometry",
            chemistry_op="limiting_solution",
            equation=equation,
            target=target,
            species={formula: float(volume) for formula, volume, _molarity in volumes},
            params={formula: float(molarity) for formula, _volume, molarity in volumes},
        )
    return None


def _one_amount(text: str, pattern: str) -> tuple[float, str] | None:
    matches = re.findall(pattern, text, re.IGNORECASE)
    if len(matches) != 1:
        return None
    amount, formula = matches[0]
    return float(amount), formula


def _chain(
    equation: str,
    target: str,
    formula: str,
    amount: float,
    known: str,
    find: str,
) -> ChemistryIntent:
    return ChemistryIntent(
        kind="stoichiometry",
        chemistry_op="mass_stoichiometry",
        equation=equation,
        target=target,
        species={formula: amount},
        units={"known": known, "find": find},
    )


def _gram_amounts(text: str) -> dict[str, float]:
    return {
        match.group(2): float(match.group(1))
        for match in re.finditer(
            rf"({_N})\s*g(?:rams?)?(?:\s+of)?\s+({CHEMICAL_FORMULA}){FORMULA_END}",
            text,
            re.IGNORECASE,
        )
    }


def _limiting_from_masses(
    equation: str, target: str, grams: dict[str, float]
) -> ChemistryIntent | None:
    """Two or more reactant masses and a product asked: the limiting reagent decides it.

    "How many grams of H2O form from 4.0 g of H2 and 40.0 g of O2?" Every reactant's mass is
    stated, so the product comes from whichever runs out first.
    """
    from app.modules.chemistry.equations import balance_equation

    if len(grams) < 2:
        return None
    balanced = balance_equation(equation)
    if (
        not balanced.balanced
        or target not in balanced.products
        or set(grams) != set(balanced.reactants)
    ):
        return None
    return ChemistryIntent(
        kind="stoichiometry",
        chemistry_op="limiting_mass",
        equation=equation,
        target=target,
        species=grams,
        units={"known": "g"},
    )


YIELD_ASK = re.compile(r"\b(?:percent(?:age)?|%)\s+yield\b", re.IGNORECASE)
_EXCESS = re.compile(r"\b(?:excess|plenty\s+of|enough)\b", re.IGNORECASE)


def extract_reaction_yield(text: str) -> ChemistryIntent | None:
    """Percent yield when the theoretical yield comes from a written reaction.

    "In CaCO3 → CaO + CO2, heating 50.0 g of CaCO3 gave 25.0 g of CaO. Percent yield?" One
    reactant's mass gives the theoretical mass of the one product weighed. A reaction with a
    second reactant reads only when the question says that one is in excess.
    """
    from app.modules.chemistry.equations import balance_equation

    equation = _equation(text)
    if equation is None or not YIELD_ASK.search(text):
        return None
    if re.search(r"\btheoretical\s+yield\s+(?:is|was|=|of)\s*\d", text, re.IGNORECASE):
        return None
    balanced = balance_equation(equation)
    grams = _gram_amounts(text)
    if not balanced.balanced or len(grams) != 2:
        return None
    reactants = [formula for formula in grams if formula in balanced.reactants]
    products = [formula for formula in grams if formula in balanced.products]
    if len(reactants) != 1 or len(products) != 1:
        return None
    if len(balanced.reactants) > 1 and not _EXCESS.search(text):
        return None
    known, product = reactants[0], products[0]
    return ChemistryIntent(
        kind="stoichiometry",
        chemistry_op="reaction_percent_yield",
        equation=equation,
        target=product,
        species={known: grams[known]},
        params={"actual": grams[product]},
    )
