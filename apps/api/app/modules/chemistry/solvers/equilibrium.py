# ruff: noqa: RUF001, RUF002
"""Equilibrium constants: Kc and Q from concentrations, Kp, and Kc ↔ Kp."""

from __future__ import annotations

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import GAS_R
from app.modules.chemistry.solvers.display import const, given_row, inp, num, used, verified
from app.modules.chemistry.solvers.types import ChemistryResult
from app.modules.chemistry.species import counts_in_mass_action, parse_species
from app.services.solving import SolveServiceError


def _stored_concentration(intent: ChemistryIntent, species: str) -> float | None:
    """Read a concentration stored under the species label or its unphased formula."""
    if species in intent.species:
        return intent.species[species]
    if "(" in species:
        bare = species[: species.rfind("(")]
        if bare in intent.species:
            return intent.species[bare]
    return None


def equilibrium_expression(
    intent: ChemistryIntent, *, pressure: bool = False
) -> tuple[float, str, str]:
    equation = intent.equation
    if not equation:
        raise SolveServiceError("a simple reaction equation is required")

    balanced = balance_equation(equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "reaction could not be balanced")

    numerator = 1.0
    denominator = 1.0
    numerator_terms: list[str] = []
    denominator_terms: list[str] = []
    substitutions_top: list[str] = []
    substitutions_bottom: list[str] = []

    def _accumulate(species: str, coefficient: int, *, product: bool) -> None:
        nonlocal numerator, denominator
        if not counts_in_mass_action(species):
            return
        concentration = _stored_concentration(intent, species)
        if concentration is None or concentration <= 0:
            raise SolveServiceError(f"positive concentration required for {species}")
        label = f"P({species})" if pressure else f"[{species}]"
        power = "" if coefficient == 1 else f"^{coefficient}"
        if product:
            numerator *= concentration**coefficient
            numerator_terms.append(f"{label}{power}")
            substitutions_top.append(f"({inp(concentration)}){power}")
        else:
            denominator *= concentration**coefficient
            denominator_terms.append(f"{label}{power}")
            substitutions_bottom.append(f"({inp(concentration)}){power}")

    for species, coefficient in balanced.products.items():
        _accumulate(species, coefficient, product=True)
    for species, coefficient in balanced.reactants.items():
        _accumulate(species, coefficient, product=False)
    if not numerator_terms and not denominator_terms:
        raise SolveServiceError("the equilibrium expression has no concentration terms")
    return (
        numerator / denominator,
        _fraction(numerator_terms, denominator_terms),
        _fraction(substitutions_top, substitutions_bottom),
    )


def _fraction(top: list[str], bottom: list[str]) -> str:
    """``[HI]^2 / ([H2] × [I2])``: parentheses only around a product; a pure solid drops out."""

    def side(parts: list[str]) -> str:
        text = " × ".join(parts) or "1"
        return f"({text})" if len(parts) > 1 else text

    if not bottom:
        return side(top)
    return f"{side(top)} / {side(bottom)}"


def solve_equilibrium(intent: ChemistryIntent) -> ChemistryResult:
    value_num, expression, substitution = equilibrium_expression(intent)
    symbol = "Kc" if intent.chemistry_op == "equilibrium_constant" else "Qc"
    title = "Verified equilibrium constant" if symbol == "Kc" else "Verified reaction quotient"
    value = num(value_num)
    return verified(
        title,
        tuple(
            f"[{species}] = {inp(concentration)} mol/L"
            for species, concentration in intent.species.items()
        ),
        symbol,
        stated(intent.chemistry_op)[0],
        f"{symbol} = {expression}",
        (f"{symbol} = {substitution}",),
        f"{symbol} = {value}",
        value,
    )


def solve_kp(intent: ChemistryIntent) -> ChemistryResult:
    value_num, expression, substitution = equilibrium_expression(intent, pressure=True)
    value = num(value_num)
    return verified(
        "Verified Kp",
        tuple(
            f"P({species}) = {inp(pressure)} atm" for species, pressure in intent.species.items()
        ),
        "Kp",
        stated("kp")[0],
        f"Kp = {expression}",
        (f"Kp = {substitution}",),
        f"Kp = {value}",
        value,
    )


def _gas_delta_n(equation: str) -> int:
    balanced = balance_equation(equation)
    if not balanced.balanced:
        raise SolveServiceError(balanced.error or "equation could not be balanced")

    def _count(side: dict[str, int]) -> int:
        total = 0
        for label, coefficient in side.items():
            species = parse_species(label, coefficient_already_removed=True)
            if species is not None and species.phase in {"s", "l", "aq"}:
                continue
            total += coefficient
        return total

    return _count(balanced.products) - _count(balanced.reactants)


def solve_kc_kp(intent: ChemistryIntent) -> ChemistryResult:
    temperature = intent.params.get("temperature")
    if temperature is None or temperature <= 0:
        raise SolveServiceError("temperature must be positive Kelvin")
    if "delta_n" in intent.params:
        delta_n = int(intent.params["delta_n"])
    elif intent.equation:
        delta_n = _gas_delta_n(intent.equation)
    else:
        raise SolveServiceError("Kc/Kp conversion needs Δn or an equation")
    factor = (GAS_R * temperature) ** delta_n
    kc = intent.params.get("kc")
    kp = intent.params.get("kp")
    if kc is not None and kp is None:
        value = kc * factor
        shown = f"Kp = {num(value)}"
        given = f"Kc = {inp(kc)}"
        working = f"Kp = ({inp(kc)})({num(GAS_R * temperature)})^{delta_n}"
    elif kp is not None and kc is None:
        if factor == 0:
            raise SolveServiceError("cannot convert that Kp")
        value = kp / factor
        shown = f"Kc = {num(value)}"
        given = f"Kp = {inp(kp)}"
        working = f"Kc = ({inp(kp)}) / ({num(GAS_R * temperature)})^{delta_n}"
    else:
        raise SolveServiceError("give Kc or Kp, not both")
    return verified(
        "Verified Kc/Kp conversion",
        (given, given_row("T", temperature, "K", "°C"), f"Δn = {delta_n}"),
        shown.split(" = ", 1)[0],
        *stated("kc_kp"),
        (
            f"RT = ({const(GAS_R)})({used(temperature)}) = {num(GAS_R * temperature)} L·atm/mol",
            working,
        ),
        shown,
        num(value),
    )
