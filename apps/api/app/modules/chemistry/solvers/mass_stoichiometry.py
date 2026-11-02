# ruff: noqa: RUF001, RUF002
"""Stoichiometry from measured amounts: grams, or a solution's or a gas's volume, via moles."""

from __future__ import annotations

from dataclasses import replace

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.scene import StoichScene, StoichStep
from app.modules.chemistry.solvers.constants import AVOGADRO, GAS_R
from app.modules.chemistry.solvers.display import const, inp, molar_mass_working, num, verified
from app.modules.chemistry.solvers.stoichiometry import balanced_text
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.stoichiometry import (
    molar_mass,
)
from app.services.solving import SolveServiceError


def _pressure_temperature(params: dict[str, float], what: str) -> tuple[float, float]:
    pressure = params.get("pressure")
    temperature = params.get("temperature")
    if pressure is None or temperature is None or pressure <= 0 or temperature <= 0:
        raise SolveServiceError(f"{what} needs positive pressure and temperature")
    return pressure, temperature


def _symbol(unit: str, formula: str) -> str:
    return {
        "mol": f"n({formula})",
        "g": f"m({formula})",
        "particles": f"N({formula})",
        "L": f"V({formula})",
        "solution": f"V({formula})",
    }.get(unit, formula)


def _known_lines(formula: str, amount: float, unit: str, params: dict[str, float]) -> list[str]:
    """Given lines for one supplied amount, including the conditions its conversion needs."""
    if unit == "L":
        pressure, temperature = _pressure_temperature(params, "gas amount")
        return [
            f"V({formula}) = {inp(amount)} L",
            f"P = {inp(pressure)} atm",
            f"T = {inp(temperature)} K",
        ]
    if unit == "solution":
        return [
            f"V({formula}) = {inp(amount)} L",
            f"M({formula}) = {inp(params.get('molarity', 0.0))} mol/L",
        ]
    noun = "particles" if unit == "particles" else unit
    return [f"{_symbol(unit, formula)} = {inp(amount)} {noun}"]


def _to_moles(
    formula: str,
    amount: float,
    unit: str,
    params: dict[str, float],
) -> tuple[float, str | None]:
    """``(moles, working)``; the working is None when the amount was already in moles."""
    if amount < 0:
        raise SolveServiceError("amount cannot be negative")
    if unit == "mol":
        return amount, None
    if unit == "g":
        molar = molar_mass(formula)
        return amount / molar, f"{inp(amount)} / {molar_mass_working(molar)}"
    if unit == "particles":
        return amount / AVOGADRO, f"{inp(amount)} / {const(AVOGADRO)}"
    if unit == "L":
        pressure, temperature = _pressure_temperature(params, "gas amount")
        return (
            pressure * amount / (GAS_R * temperature),
            f"({inp(pressure)})({inp(amount)}) / (({const(GAS_R)})({inp(temperature)}))",
        )
    if unit == "solution":
        molarity = params.get("molarity")
        if molarity is None or molarity < 0:
            raise SolveServiceError("solution amount needs molarity")
        return molarity * amount, f"({inp(molarity)})({inp(amount)})"
    raise SolveServiceError(f"unsupported amount unit {unit}")


def _from_moles(
    formula: str, moles: float, unit: str, params: dict[str, float]
) -> tuple[float, str, str | None]:
    """``(value, unit, working)`` for an amount of product expressed in ``unit``."""
    if unit == "mol":
        return moles, "mol", None
    if unit == "g":
        molar = molar_mass(formula)
        return moles * molar, "g", f"{num(moles)} × {molar_mass_working(molar)}"
    if unit == "particles":
        return moles * AVOGADRO, "particles", f"{num(moles)} × {const(AVOGADRO)}"
    if unit == "L":
        pressure, temperature = _pressure_temperature(params, "gas volume")
        return (
            moles * GAS_R * temperature / pressure,
            "L",
            f"({num(moles)})({const(GAS_R)})({inp(temperature)}) / {inp(pressure)}",
        )
    raise SolveServiceError(f"unsupported result unit {unit}")


def _ratio(intent: ChemistryIntent) -> tuple[str, str, int, int, str]:
    equation = intent.equation
    target = intent.target
    if not equation or not target or len(intent.species) != 1:
        raise SolveServiceError("one reactant, an equation, and a product are required")
    known = next(iter(intent.species))
    balanced = balance_equation(equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "equation could not be balanced")
    # Any two species of the balanced equation: a product from a reactant, or the reactant
    # needed for a product, or one reactant for another.
    coefficients = {**balanced.reactants, **balanced.products}
    if known == target or known not in coefficients or target not in coefficients:
        raise SolveServiceError("both species must be in the balanced equation")
    return known, target, coefficients[known], coefficients[target], equation


def solve_mass_stoichiometry(intent: ChemistryIntent) -> ChemistryResult:
    known, target, reactant_coeff, product_coeff, equation = _ratio(intent)
    known_unit = intent.units.get("known", "g")
    find_unit = intent.units.get("find", "g")
    amount = next(iter(intent.species.values()))
    moles, known_working = _to_moles(known, amount, known_unit, intent.params)
    product_moles = moles * product_coeff / reactant_coeff
    value_num, unit, find_working = _from_moles(target, product_moles, find_unit, intent.params)
    value = f"{num(value_num)} {unit}"
    steps = [
        f"n({known}) = {known_working} = {num(moles)} mol"
        if known_working
        else f"n({known}) = {num(moles)} mol",
        f"n({target}) = {num(moles)} × ({product_coeff} / {reactant_coeff}) "
        f"= {num(product_moles)} mol",
    ]
    if find_working:
        steps.append(f"{_symbol(find_unit, target)} = {find_working} = {value}")
    result = verified(
        "Verified stoichiometry chain",
        (
            f"Balanced equation: {balanced_text(equation)}",
            *_known_lines(known, amount, known_unit, intent.params),
        ),
        f"Amount of {target}",
        stated(intent.chemistry_op)[0],
        f"n({target}) = n({known}) × ({product_coeff} / {reactant_coeff})",
        steps,
        f"{_symbol(find_unit, target)} = {value}",
        value,
    )
    return replace(
        result,
        scene=StoichScene(
            title="Stoichiometry chain",
            steps=[
                StoichStep(
                    label=f"n({known})",
                    value=f"{known_working} = {num(moles)} mol"
                    if known_working
                    else f"{num(moles)} mol",
                ),
                StoichStep(
                    label=f"n({target})",
                    value=f"{num(moles)} × ({product_coeff} / {reactant_coeff}) "
                    f"= {num(product_moles)} mol",
                ),
                StoichStep(label=_symbol(find_unit, target), value=value),
            ],
        ),
    )


def solve_limiting_amounts(intent: ChemistryIntent, *, unit: str) -> ChemistryResult:
    equation = intent.equation
    target = intent.target
    if not equation or not target or len(intent.species) < 2:
        raise SolveServiceError("two reactant amounts, an equation, and a product are required")
    balanced = balance_equation(equation)
    if not balanced.balanced or target not in balanced.products:
        raise SolveServiceError("equation could not be balanced for that product")
    moles: dict[str, float] = {}
    working: dict[str, str | None] = {}
    given: list[str] = []
    for formula, amount in intent.species.items():
        if formula not in balanced.reactants:
            raise SolveServiceError(f"{formula} is not a reactant")
        params = dict(intent.params)
        if unit == "solution":
            molarity = intent.params.get(formula)
            if molarity is None:
                raise SolveServiceError(f"missing molarity for {formula}")
            params["molarity"] = molarity
        moles[formula], working[formula] = _to_moles(formula, amount, unit, params)
        given.extend(_known_lines(formula, amount, unit, params))
    missing = [name for name in balanced.reactants if name not in moles]
    if missing:
        raise SolveServiceError(f"an amount is needed for every reactant, missing {missing[0]}")
    reaction_units = {name: moles[name] / balanced.reactants[name] for name in moles}
    fewest = min(reaction_units.values())
    limiting = [name for name, value in reaction_units.items() if value <= fewest * (1 + 1e-9)]
    product_coeff = balanced.products[target]
    product_moles = fewest * product_coeff
    product_molar = molar_mass(target)
    product_mass = product_moles * product_molar
    steps = []
    for formula in moles:
        steps.append(
            f"n({formula}) = {working[formula]} = {num(moles[formula])} mol"
            if working[formula]
            else f"n({formula}) = {num(moles[formula])} mol"
        )
        steps.append(
            f"{formula}: {num(moles[formula])} / {balanced.reactants[formula]} = "
            f"{num(reaction_units[formula])} reaction units"
        )
    steps.append(f"limiting reagent = {' and '.join(limiting)} (fewest reaction units)")
    steps.append(f"n({target}) = {num(fewest)} × {product_coeff} = {num(product_moles)} mol")
    steps.append(
        f"m({target}) = {num(product_moles)} × {molar_mass_working(product_molar)} "
        f"= {num(product_mass)} g"
    )
    for formula, amount in moles.items():
        if formula in limiting:
            continue
        used = fewest * balanced.reactants[formula]
        leftover = amount - used
        if unit == "g":
            molar = molar_mass(formula)
            steps.append(
                f"excess {formula} = ({num(amount)} − {num(used)}) × {molar_mass_working(molar)} "
                f"= {num(leftover * molar)} g"
            )
        else:
            steps.append(f"excess {formula} = {num(amount)} − {num(used)} = {num(leftover)} mol")
    value = f"{num(product_mass)} g {target}"
    return verified(
        "Verified limiting reagent",
        given,
        f"Limiting reagent, theoretical yield of {target}, and excess",
        *stated(intent.chemistry_op),
        steps,
        f"Limiting reagent = {' and '.join(limiting)}; {value}",
        value,
    )


def solve_limiting_mass(intent: ChemistryIntent) -> ChemistryResult:
    return solve_limiting_amounts(intent, unit="g")


def solve_limiting_solution(intent: ChemistryIntent) -> ChemistryResult:
    return solve_limiting_amounts(intent, unit="solution")


def solve_reaction_percent_yield(intent: ChemistryIntent) -> ChemistryResult:
    """% yield = actual / theoretical × 100, the theoretical mass from the reaction's ratio."""
    known, target, reactant_coeff, product_coeff, equation = _ratio(intent)
    amount = next(iter(intent.species.values()))
    actual = intent.params.get("actual")
    if actual is None or actual < 0 or amount <= 0:
        raise SolveServiceError("percent yield needs the reactant mass and the actual yield")
    moles, known_working = _to_moles(known, amount, "g", intent.params)
    product_moles = moles * product_coeff / reactant_coeff
    molar = molar_mass(target)
    theoretical = product_moles * molar
    if actual > theoretical * 1.0001:
        raise SolveServiceError("the actual yield is more than the reaction can make")
    percent = actual / theoretical * 100
    value = f"{num(percent)}%"
    return verified(
        "Verified percent yield",
        (
            f"Balanced equation: {balanced_text(equation)}",
            f"m({known}) = {inp(amount)} g",
            f"actual yield of {target} = {inp(actual)} g",
        ),
        "Percent yield",
        *stated("reaction_percent_yield"),
        (
            f"n({known}) = {known_working} = {num(moles)} mol",
            f"n({target}) = {num(moles)} × ({product_coeff} / {reactant_coeff})"
            f" = {num(product_moles)} mol",
            f"theoretical m({target}) = {num(product_moles)} × {molar_mass_working(molar)}"
            f" = {num(theoretical)} g",
            f"% yield = ({inp(actual)} g / {num(theoretical)} g) × 100",
        ),
        f"Percent yield = {value}",
        value,
    )
