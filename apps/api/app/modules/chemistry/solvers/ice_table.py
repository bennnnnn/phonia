# ruff: noqa: RUF001, RUF002
"""ICE tables: an equilibrium's concentrations from the initial ones and K."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.scene import EquilibriumRow, EquilibriumScene
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import counts_in_mass_action
from app.services.solving import SolveServiceError


def solve_ice(intent: ChemistryIntent) -> ChemistryResult:
    if not intent.equation:
        raise SolveServiceError("an equilibrium equation is required")
    constant = intent.params.get("k")
    if constant is None or constant <= 0:
        raise SolveServiceError("K must be positive")
    balanced = balance_equation(intent.equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "equation could not be balanced")
    from sympy import N, Symbol, expand

    extent = Symbol("x")
    concentrations: dict[str, Any] = {}
    for species, coefficient in balanced.reactants.items():
        if counts_in_mass_action(species):
            if species not in intent.species:
                raise SolveServiceError(f"the starting concentration of {species} is missing")
            concentrations[species] = intent.species[species] - coefficient * extent
    for species, coefficient in balanced.products.items():
        if counts_in_mass_action(species):
            concentrations[species] = intent.species.get(species, 0.0) + coefficient * extent
    if not concentrations:
        raise SolveServiceError("the equilibrium has no concentration terms")
    numerator = 1
    denominator = 1
    for species, coefficient in balanced.products.items():
        if species in concentrations:
            numerator *= concentrations[species] ** coefficient
    for species, coefficient in balanced.reactants.items():
        if species in concentrations:
            denominator *= concentrations[species] ** coefficient
    polynomial = expand(numerator - constant * denominator)
    poly = polynomial.as_poly(extent)
    if poly is None or poly.degree() > 2:
        raise SolveServiceError("equilibrium extent is higher than quadratic")
    roots = poly.nroots() if poly.degree() > 0 else []
    # Tolerances follow the size of the concentrations, so a 1e-9 M problem is not
    # judged by a 1e-6 M yardstick.
    scale = max((abs(value) for value in intent.species.values()), default=0.0) or 1.0
    valid: list[float] = []
    for root in roots:
        numeric = complex(N(root))
        if abs(numeric.imag) > 1e-7 * scale:
            continue
        candidate = float(numeric.real)
        negative = -1e-8 * scale
        if any(
            float(N(expr.subs(extent, candidate))) < negative for expr in concentrations.values()
        ):
            continue
        if not any(abs(candidate - kept) <= 1e-6 * scale for kept in valid):
            valid.append(candidate)
    if len(valid) != 1:
        raise SolveServiceError("equilibrium extent is not unique")
    chosen = valid[0]
    equilibrium: dict[str, str] = {}
    results: list[str] = []
    for species, expression in concentrations.items():
        amount = float(N(expression.subs(extent, chosen)))
        shown = f"{num(amount)} mol/L"
        results.append(f"[{species}] = {shown}")
        equilibrium[species] = shown
    rows = _ice_rows(intent, balanced.reactants, balanced.products, equilibrium)
    lines = [
        *_ice_setup(intent, balanced.reactants, balanced.products, concentrations),
        f"K = {_ice_expression(balanced.reactants, balanced.products, concentrations)} = "
        f"{inp(constant)}",
        f"K = {_ice_substituted(intent, balanced.reactants, balanced.products, concentrations)}",
        f"{_polynomial_text(poly.all_coeffs())} = 0",
        f"x = {num(chosen)} (the root that keeps every concentration non-negative)",
    ]
    answer = "\n".join([f"x = {num(chosen)}", *results])
    quotient = _ice_substituted(intent, balanced.reactants, balanced.products, concentrations)
    result = verified(
        "Verified ICE equilibrium",
        (intent.equation, f"K = {inp(constant)}"),
        "Equilibrium extent and concentrations",
        stated("ice_equilibrium")[0],
        f"K = {quotient}",
        lines,
        answer,
        num(chosen),
    )
    return replace(result, scene=EquilibriumScene(title="ICE table", rows=rows))


def _extent_text(initial: float, coefficient: int, *, product: bool) -> str:
    """One species at equilibrium in terms of the extent x: ``2x``, ``1 − x``, ``0.1 + x``."""
    change = "x" if coefficient == 1 else f"{coefficient}x"
    if initial == 0 and product:
        return change
    return f"{inp(initial)} {'+' if product else '−'} {change}"


def _ice_setup(
    intent: ChemistryIntent,
    reactants: dict[str, int],
    products: dict[str, int],
    concentrations: dict[str, Any],
) -> list[str]:
    """``[N2O4] = 1 − x`` for each species: initial concentration plus its change."""
    lines = []
    for side, product in ((reactants, False), (products, True)):
        for species, coefficient in side.items():
            if species in concentrations:
                initial = intent.species.get(species, 0.0)
                lines.append(f"[{species}] = {_extent_text(initial, coefficient, product=product)}")
    return lines


def _ice_expression(
    reactants: dict[str, int], products: dict[str, int], concentrations: dict[str, Any]
) -> str:
    """The mass-action expression as written in the concentrations: ``[NO2]^2 / [N2O4]``."""

    def side(terms: dict[str, int]) -> str:
        parts = [
            f"[{species}]" + ("" if coefficient == 1 else f"^{coefficient}")
            for species, coefficient in terms.items()
            if species in concentrations
        ]
        text = " × ".join(parts) or "1"
        return f"({text})" if len(parts) > 1 else text

    return f"{side(products)} / {side(reactants)}"


def _ice_substituted(
    intent: ChemistryIntent,
    reactants: dict[str, int],
    products: dict[str, int],
    concentrations: dict[str, Any],
) -> str:
    """``(2x)^2 / (1 − x)``: each concentration replaced by its expression in x."""

    def side(terms: dict[str, int], *, product: bool) -> str:
        parts = []
        for species, coefficient in terms.items():
            if species not in concentrations:
                continue
            expression = _extent_text(
                intent.species.get(species, 0.0), coefficient, product=product
            )
            parts.append(f"({expression})" + ("" if coefficient == 1 else f"^{coefficient}"))
        text = " × ".join(parts) or "1"
        return f"({text})" if len(parts) > 1 else text

    return f"{side(products, product=True)} / {side(reactants, product=False)}"


def _polynomial_text(coefficients: list[Any]) -> str:
    """``4x^2 + 4x − 4`` from sympy's highest-degree-first coefficients."""
    degree = len(coefficients) - 1
    text = ""
    for offset, coefficient in enumerate(coefficients):
        value = float(coefficient)
        if abs(value) < 1e-15:
            continue
        power = degree - offset
        magnitude = num(abs(value))
        term = magnitude if power == 0 else ("x" if power == 1 else f"x^{power}")
        if power and abs(abs(value) - 1) < 1e-12:
            body = term
        elif power:
            body = f"{magnitude}{term}"
        else:
            body = term
        sign = "−" if value < 0 else "+"
        text += f"−{body}" if not text and value < 0 else body if not text else f" {sign} {body}"
    return text or "0"


def _ice_change(coefficient: int, *, product: bool) -> str:
    magnitude = "x" if coefficient == 1 else f"{coefficient}x"
    return f"+{magnitude}" if product else f"−{magnitude}"


def _ice_rows(
    intent: ChemistryIntent,
    reactants: dict[str, int],
    products: dict[str, int],
    equilibrium: dict[str, str],
) -> list[EquilibriumRow]:
    rows: list[EquilibriumRow] = []
    for species, coefficient in reactants.items():
        if not counts_in_mass_action(species):
            continue
        rows.append(
            EquilibriumRow(
                species=species,
                initial=num(intent.species.get(species, 0.0)),
                change=_ice_change(coefficient, product=False),
                equilibrium=equilibrium.get(species, ""),
            )
        )
    for species, coefficient in products.items():
        if not counts_in_mass_action(species):
            continue
        rows.append(
            EquilibriumRow(
                species=species,
                initial=num(intent.species.get(species, 0.0)),
                change=_ice_change(coefficient, product=True),
                equilibrium=equilibrium.get(species, ""),
            )
        )
    return rows
