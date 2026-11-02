# ruff: noqa: RUF001
"""Solubility equilibria: Ksp, precipitation, and the common-ion effect."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import counts_in_mass_action
from app.services.solving import SolveServiceError


def _ions(equation: str) -> list[tuple[str, int]]:
    balanced = balance_equation(equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "solubility equation could not be balanced")
    ions = [
        (species, coefficient)
        for species, coefficient in balanced.products.items()
        if counts_in_mass_action(species)
    ]
    if not ions:
        raise SolveServiceError("solubility products need at least one aqueous ion")
    return ions


def _solubility_power(ions: list[tuple[str, int]]) -> tuple[float, int]:
    factor = 1.0
    power = 0
    for _species, coefficient in ions:
        factor *= coefficient**coefficient
        power += coefficient
    return factor, power


def _ion_product_text(ions: list[tuple[str, int]]) -> str:
    """``Ksp = [Ca2+][OH-]^2 = (s)(2s)^2 = 4s^3`` for the ions of a salt with solubility s."""
    factor, power = _solubility_power(ions)
    bracketed = "".join(
        f"[{species}]" + ("" if coefficient == 1 else f"^{coefficient}")
        for species, coefficient in ions
    )
    in_s = "".join(
        f"({'' if coefficient == 1 else coefficient}s)"
        + ("" if coefficient == 1 else f"^{coefficient}")
        for _species, coefficient in ions
    )
    collected = f"{num(factor)}s" if factor != 1 else "s"
    collected += "" if power == 1 else f"^{power}"
    return f"Ksp = {bracketed} = {in_s} = {collected}"


def solve_ksp(intent: ChemistryIntent) -> ChemistryResult:
    if not intent.equation:
        raise SolveServiceError("a solubility equation is required")
    ions = _ions(intent.equation)
    factor, power = _solubility_power(ions)
    ksp = intent.params.get("ksp")
    solubility = intent.params.get("solubility")
    lines = [_ion_product_text(ions)]
    if ksp is not None and solubility is None:
        if ksp <= 0:
            raise SolveServiceError("Ksp must be positive")
        value = (ksp / factor) ** (1 / power)
        shown = f"s = {num(value)} mol/L"
        detail = f"Ksp = {inp(ksp)}"
        divisor = "" if factor == 1 else f" / {num(factor)}"
        lines.append(f"s = (Ksp{divisor})^(1/{power}) = (({inp(ksp)}){divisor})^(1/{power})")
    elif solubility is not None and ksp is None:
        if solubility <= 0:
            raise SolveServiceError("solubility must be positive")
        value = factor * solubility**power
        shown = f"Ksp = {num(value)}"
        detail = f"s = {inp(solubility)} mol/L"
        lines.append(f"Ksp = ({num(factor)})({inp(solubility)})^{power}")
    else:
        raise SolveServiceError("give Ksp or the molar solubility, not both")
    return verified(
        "Verified solubility product",
        (intent.equation, detail),
        "Molar solubility" if ksp is not None else "Ksp",
        *stated("ksp"),
        lines,
        shown,
        num(value),
    )


def solve_precipitation(intent: ChemistryIntent) -> ChemistryResult:
    qsp = intent.params.get("qsp")
    ksp = intent.params.get("ksp")
    if qsp is None or ksp is None or qsp < 0 or ksp <= 0:
        raise SolveServiceError("precipitation needs a non-negative Qsp and a positive Ksp")
    if math.isclose(qsp, ksp, rel_tol=1e-9, abs_tol=0.0):
        relation = "saturated (Qsp = Ksp)"
    elif qsp > ksp:
        relation = "precipitate forms (Qsp > Ksp)"
    else:
        relation = "no precipitate (Qsp < Ksp)"
    return verified(
        "Verified precipitation check",
        (f"Qsp = {inp(qsp)}", f"Ksp = {inp(ksp)}"),
        "Whether a precipitate forms",
        *stated("precipitation"),
        (
            f"Qsp = {inp(qsp)} {'=' if 'saturated' in relation else '>' if qsp > ksp else '<'} "
            f"Ksp = {inp(ksp)}",
        ),
        relation,
        relation,
    )


def solve_common_ion(intent: ChemistryIntent) -> ChemistryResult:
    if not intent.equation:
        raise SolveServiceError("a solubility equation is required")
    ksp = intent.params.get("ksp")
    if ksp is None or ksp <= 0:
        raise SolveServiceError("Ksp must be positive")
    ions = _ions(intent.equation)
    unknown = [species for species, _coefficient in ions if species not in intent.species]
    if len(unknown) != 1:
        raise SolveServiceError("exactly one ion concentration must be unknown")
    target = unknown[0]
    power = dict(ions)[target]
    known = 1.0
    for species, coefficient in ions:
        if species == target:
            continue
        concentration = intent.species[species]
        if concentration <= 0:
            raise SolveServiceError(f"{species} concentration must be positive")
        known *= concentration**coefficient
    value = (ksp / known) ** (1 / power)
    shown = f"[{target}] = {num(value)} mol/L"
    given = [f"Ksp = {inp(ksp)}"]
    given.extend(f"[{name}] = {inp(amount)} mol/L" for name, amount in intent.species.items())
    parts = [
        f"({inp(intent.species[species])})" + ("" if coefficient == 1 else f"^{coefficient}")
        for species, coefficient in ions
        if species != target
    ]
    others = parts[0] if len(parts) == 1 else f"({' × '.join(parts)})"
    root = "" if power == 1 else f"^(1/{power})"
    working = f"[{target}] = (({inp(ksp)}) / {others}){root}"
    return verified(
        "Verified common-ion concentration",
        given,
        f"[{target}]",
        *stated("common_ion"),
        (
            _ion_product_text_from_species(ions),
            working,
            f"molar solubility s = [{target}] / {power} = {num(value / power)} mol/L",
        ),
        shown,
        num(value),
    )


def _ion_product_text_from_species(ions: list[tuple[str, int]]) -> str:
    return "Ksp = " + "".join(
        f"[{species}]" + ("" if coefficient == 1 else f"^{coefficient}")
        for species, coefficient in ions
    )
