# ruff: noqa: RUF001, RUF002
"""Balanced equations and the amounts they relate: mole ratios, yields, limiting reagents."""

from __future__ import annotations

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.equations import balance_equation, format_balanced
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import inp, num, qty, verified
from app.modules.chemistry.solvers.params import require
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import parse_species
from app.modules.chemistry.stoichiometry import (
    limiting_reagent,
    stoichiometry,
)
from app.services.solving import SolveServiceError


def balanced_text(equation: str) -> str:
    """The balanced equation as text, or a refusal when it does not balance."""
    balanced = balance_equation(equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "equation could not be balanced")
    return format_balanced(balanced)


def _tally_lines(equation: str, *, written: bool = False) -> tuple[str, ...]:
    """One line per element (and one for charge): coefficient × atoms summed on each side.

    ``written`` tallies the coefficients the user typed instead of the balanced ones.
    """
    balanced = balance_equation(equation)
    left_side = balanced.written_reactants if written else balanced.reactants
    right_side = balanced.written_products if written else balanced.products
    parsed = {
        label: parse_species(label, coefficient_already_removed=True)
        for label in (*balanced.reactants, *balanced.products)
    }
    if any(species is None for species in parsed.values()):
        return ()
    elements = list(
        dict.fromkeys(
            element
            for species in parsed.values()
            if species is not None
            for element in species.composition
        )
    )

    def side_text(side: dict[str, int], element: str | None) -> str:
        terms = []
        for label, coefficient in side.items():
            species = parsed[label]
            if species is None:
                continue
            count = species.charge if element is None else species.composition.get(element, 0)
            if count:
                terms.append((coefficient, count))
        total = sum(coefficient * count for coefficient, count in terms)
        shown = " + ".join(f"{coefficient}({count})" for coefficient, count in terms)
        return f"{shown} = {total}" if terms else "0"

    lines = [
        f"{element}: left {side_text(left_side, element)}; right {side_text(right_side, element)}"
        for element in elements
    ]
    if any(species is not None and species.charge for species in parsed.values()):
        lines.append(
            f"charge: left {side_text(left_side, None)}; right {side_text(right_side, None)}"
        )
    return tuple(lines)


def solve_equation(intent: ChemistryIntent) -> ChemistryResult:
    equation = intent.equation
    if not equation:
        raise SolveServiceError("an equation is required")
    balanced = balanced_text(equation)
    if intent.target == "check":
        already = balance_equation(equation).given_balanced
        verdict = (
            f"Yes, it is balanced: {balanced}"
            if already
            else f"No, it is not balanced. Balanced: {balanced}"
        )
        return verified(
            title="Verified balance check",
            given=(f"Equation: {equation}",),
            find="Whether the written coefficients balance",
            formula_name=stated("balance")[0],
            formula=stated("balance")[1],
            substitution=_tally_lines(equation, written=True)
            or (f"Count atoms and charge on each side of: {equation}",),
            answer=verdict,
            value=verdict,
        )
    return verified(
        title="Verified balanced equation",
        given=(f"Unbalanced equation: {equation}",),
        find="Smallest whole-number coefficients",
        formula_name=stated("balance")[0],
        formula=stated("balance")[1],
        substitution=_tally_lines(equation) or (f"Balance element counts: {equation}",),
        answer=balanced,
        value=balanced,
    )


def solve_percent_yield(intent: ChemistryIntent) -> ChemistryResult:
    actual = require(intent, "actual", non_negative=True)
    theoretical = require(intent, "theoretical", positive=True)
    percent = actual / theoretical * 100
    value = f"{num(percent)}%"
    return verified(
        "Verified percent yield",
        (
            f"actual yield = {inp(actual)} g",
            f"theoretical yield = {inp(theoretical)} g",
        ),
        "Percent yield",
        *stated("percent_yield"),
        (f"% yield = ({qty(actual, 'g')} / {qty(theoretical, 'g')}) × 100",),
        f"Percent yield = {value}",
        value,
    )


def solve_stoichiometry(intent: ChemistryIntent) -> ChemistryResult:
    equation = intent.equation
    target = intent.target
    if not equation or not target:
        raise SolveServiceError("equation and target product are required")
    if intent.chemistry_op == "limiting_reagent":
        if len(intent.species) < 2:
            raise SolveServiceError("at least two reactant amounts are required")
        limiting_result = limiting_reagent(equation, intent.species, target)
        if (
            limiting_result.error
            or limiting_result.limiting_reagent is None
            or limiting_result.product_amount is None
        ):
            raise SolveServiceError(limiting_result.error or "limiting reagent solve failed")
        balanced = balance_equation(equation)
        product_coeff = balanced.products[target]
        ratios = tuple(
            f"{name}: {inp(amount)} / {balanced.reactants[name]} = "
            f"{num(amount / balanced.reactants[name])} reaction units"
            for name, amount in intent.species.items()
        )
        value = f"{num(limiting_result.product_amount)} mol {target}"
        limiting_names = " and ".join((limiting_result.limiting_reagent, *limiting_result.tied))
        return verified(
            "Verified limiting reagent",
            tuple(f"n({name}) = {inp(amount)} mol" for name, amount in intent.species.items()),
            f"Limiting reagent and moles of {target}",
            *stated("limiting_reagent"),
            (*ratios, f"n({target}) = smallest reaction units × {product_coeff}"),
            f"Limiting reagent = {limiting_names}; {value}",
            value,
        )
    if len(intent.species) != 1:
        raise SolveServiceError("one known reactant amount is required")
    known, amount = next(iter(intent.species.items()))
    stoich_result = stoichiometry(equation, known, amount, target)
    if stoich_result.error or stoich_result.product_amount is None:
        raise SolveServiceError(stoich_result.error or "stoichiometry solve failed")
    balanced = balance_equation(equation)
    r_coeff = balanced.reactants[known]
    p_coeff = balanced.products[target]
    value = f"{num(stoich_result.product_amount)} mol {target}"
    return verified(
        "Verified stoichiometry",
        (
            f"Balanced equation: {balanced_text(equation)}",
            f"n({known}) = {inp(amount)} mol",
        ),
        f"Moles of {target}",
        stated("stoichiometry")[0],
        f"n({target}) = n({known}) × ({p_coeff} / {r_coeff})",
        (f"n({target}) = {inp(amount)} × ({p_coeff} / {r_coeff})",),
        f"n({target}) = {value}",
        value,
    )
