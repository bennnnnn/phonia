"""Chemical equation parsing and balancing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.modules.chemistry.species import ReactionTerm, parse_reaction, split_equation


@dataclass(frozen=True)
class BalancedEquation:
    """Result of balancing a chemical equation."""

    reactants: dict[str, int]  # species → coefficient
    products: dict[str, int]  # species → coefficient
    balanced: bool
    error: str | None = None
    given_balanced: bool = False  # the coefficients the user wrote are already correct
    # The coefficients as the user typed them (1 when omitted), for a balance check.
    written_reactants: dict[str, int] = field(default_factory=dict)
    written_products: dict[str, int] = field(default_factory=dict)


def _counted(
    terms: Sequence[ReactionTerm],
    coeffs: list[int],
) -> tuple[dict[str, int], int] | None:
    """Atom and charge totals. Electrons contribute charge and no atoms."""
    totals: dict[str, int] = {}
    charge = 0
    for term, coeff in zip(terms, coeffs, strict=True):
        if not isinstance(term, ReactionTerm) or coeff < 1:
            return None
        if not term.species.electron and not term.species.composition:
            return None
        for elem, count in term.species.composition.items():
            totals[elem] = totals.get(elem, 0) + coeff * count
        charge += coeff * term.species.charge
    return totals, charge


def written_is_balanced(equation: str) -> bool:
    """The coefficients as written conserve atoms and charge.

    A common multiple counts: ``4 H2 + 2 O2 -> 4 H2O`` is balanced, not only the
    smallest integers ``2 H2 + O2 -> 2 H2O``.
    """
    reaction = parse_reaction(equation)
    if reaction is None or not reaction.reactants or not reaction.products:
        return False
    # A species written on both sides is a spectator, not a balanced reaction to weigh.
    labels = [term.species.label for term in (*reaction.reactants, *reaction.products)]
    if len(labels) != len(set(labels)):
        return False
    left = _counted(reaction.reactants, [term.coefficient for term in reaction.reactants])
    right = _counted(reaction.products, [term.coefficient for term in reaction.products])
    return left is not None and left == right


def format_balanced(balanced: BalancedEquation) -> str:
    """``2 H2 + O2 -> 2 H2O``: coefficients of 1 are left out."""

    def side(terms: dict[str, int]) -> str:
        return " + ".join(
            f"{coefficient} {species}" if coefficient != 1 else species
            for species, coefficient in terms.items()
        )

    return f"{side(balanced.reactants)} -> {side(balanced.products)}"


def balance_equation(equation: str) -> BalancedEquation:
    """Balance a chemical equation using SymPy linear algebra.

    Atom rows are always required. A charge row is added only when some species
    is an ion or an electron, so uncharged equations keep the same nullspace.
    e.g. "H2 + O2 -> H2O" → reactants={"H2": 2, "O2": 1}, products={"H2O": 2}
    """
    from sympy import Matrix, lcm

    if split_equation(equation) is None:
        return BalancedEquation({}, {}, False, "no arrow in equation")
    reaction = parse_reaction(equation)
    if reaction is None:
        return BalancedEquation({}, {}, False, "cannot parse equation")

    reactant_terms = list(reaction.reactants)
    product_terms = list(reaction.products)
    labels = [term.species.label for term in reactant_terms + product_terms]
    if len(labels) != len(set(labels)):
        return BalancedEquation({}, {}, False, "duplicate species")

    all_elements: set[str] = set()
    for term in reactant_terms + product_terms:
        all_elements.update(term.species.composition)
    elements = sorted(all_elements)
    n_reactants = len(reactant_terms)
    n_products = len(product_terms)

    rows: list[list[int]] = []
    for elem in elements:
        row = [term.species.composition.get(elem, 0) for term in reactant_terms]
        row.extend(-term.species.composition.get(elem, 0) for term in product_terms)
        rows.append(row)
    charges = [term.species.charge for term in reactant_terms + product_terms]
    if any(charge != 0 for charge in charges):
        charge_row = charges[:n_reactants] + [-charge for charge in charges[n_reactants:]]
        rows.append(charge_row)
    if not rows:
        return BalancedEquation({}, {}, False, "no constraints")

    matrix = Matrix(rows)
    nullspace = matrix.nullspace()
    if not nullspace:
        return BalancedEquation({}, {}, False, "no solution")
    if len(nullspace) != 1:
        return BalancedEquation({}, {}, False, "underdetermined")

    vec = nullspace[0]
    denominators = [v.q for v in vec]
    common = lcm(denominators) if denominators else 1
    coeffs = [int(v * common) for v in vec]
    if any(c < 0 for c in coeffs):
        coeffs = [-c for c in coeffs]
    if any(c < 1 for c in coeffs):
        return BalancedEquation({}, {}, False, "non-positive coefficient")

    left = _counted(reactant_terms, coeffs[:n_reactants])
    right = _counted(product_terms, coeffs[n_reactants:])
    if left is None or right is None or left[0] != right[0]:
        return BalancedEquation({}, {}, False, "atoms do not balance")
    if left[1] != right[1]:
        return BalancedEquation({}, {}, False, "charge does not balance")

    reactant_coeffs = {labels[i]: coeffs[i] for i in range(n_reactants)}
    product_coeffs = {labels[n_reactants + i]: coeffs[n_reactants + i] for i in range(n_products)}
    written = [term.coefficient for term in reactant_terms + product_terms]
    return BalancedEquation(
        reactants=reactant_coeffs,
        products=product_coeffs,
        balanced=True,
        given_balanced=written == coeffs,
        written_reactants={labels[i]: reactant_terms[i].coefficient for i in range(n_reactants)},
        written_products={
            labels[n_reactants + i]: product_terms[i].coefficient for i in range(n_products)
        },
    )
