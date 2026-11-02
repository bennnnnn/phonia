"""Properties of the chemistry solvers (Hypothesis; code-health audit TEST-08).

The STEM corpus checks chosen questions. These check what makes a whole family
right: a balanced equation keeps every element and its smallest whole coefficients,
a nuclear one keeps its nucleons and protons, and a unit conversion comes back to
the value it started from.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest
from hypothesis import event, example, given, settings
from hypothesis import strategies as st

from app.modules.chemistry.elements import ELEMENTS
from app.modules.chemistry.equations import balance_equation
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.nuclear import balance_nuclear
from app.modules.chemistry.quantity import convert

# Ions by charge, for a synthesis that balances by construction.
_METALS = {"Li": 1, "Na": 1, "K": 1, "Mg": 2, "Ca": 2, "Ba": 2, "Zn": 2, "Al": 3, "Fe": 3}
_NONMETALS = {"F2": -1, "Cl2": -1, "Br2": -1, "I2": -1, "O2": -2, "N2": -3}
# Species real reactions use; any pick of them is a fair equation to try.
_SPECIES = (
    "H2", "O2", "H2O", "CH4", "CO2", "CO", "C3H8", "C2H6", "C6H12O6", "N2", "NH3", "NO",
    "NO2", "Na", "Cl2", "NaCl", "Fe", "Fe2O3", "Al", "Al2O3", "Mg", "MgO", "HCl", "NaOH",
    "H2SO4", "Na2SO4", "CaCO3", "CaO", "KClO3", "KCl",
)  # fmt: skip
_BY_NUMBER = {element.number: element for element in ELEMENTS}
# How each decay moves the daughter: (mass number, protons).
_DECAYS = {"alpha": (-4, -2), "beta minus": (0, 1), "beta plus": (0, -1)}
_UNITS = (
    ("atm", "kPa", "Pa", "bar", "mmHg", "torr"),
    ("L", "mL"),
    ("K", "°C"),
)


def _atoms(side: dict[str, int]) -> Counter[str]:
    total: Counter[str] = Counter()
    for species, coefficient in side.items():
        for element, count in parse_formula(species).items():
            total[element] += coefficient * count
    return total


def _formula(*parts: tuple[str, int]) -> str:
    return "".join(f"{element}{count if count > 1 else ''}" for element, count in parts if count)


@st.composite
def _balanceable(draw: st.DrawFn) -> str:
    """A combustion or an ionic synthesis: some whole coefficients always balance it."""
    if draw(st.booleans()):
        carbon = draw(st.integers(min_value=1, max_value=12))
        hydrogen = draw(st.integers(min_value=1, max_value=2 * carbon + 2))
        # O2 is burned only while the fuel holds less oxygen than CO2 and H2O take.
        most_oxygen = math.ceil(2 * carbon + hydrogen / 2) - 1
        oxygen = draw(st.integers(min_value=0, max_value=min(3, most_oxygen)))
        fuel = _formula(("C", carbon), ("H", hydrogen), ("O", oxygen))
        return f"{fuel} + O2 -> CO2 + H2O"
    metal, positive = draw(st.sampled_from(sorted(_METALS.items())))
    nonmetal, negative = draw(st.sampled_from(sorted(_NONMETALS.items())))
    shared = math.gcd(positive, -negative)
    salt = _formula((metal, -negative // shared), (nonmetal[:-1], positive // shared))
    return f"{metal} + {nonmetal} -> {salt}"


@given(equation=_balanceable())
@example(equation="C3H8 + O2 -> CO2 + H2O")
@example(equation="Fe + O2 -> Fe2O3")
@settings(max_examples=150, deadline=None)
def test_a_balanced_equation_keeps_every_element(equation: str) -> None:
    result = balance_equation(equation)
    assert result.balanced, (equation, result.error)
    coefficients = [*result.reactants.values(), *result.products.values()]
    assert all(coefficient > 0 for coefficient in coefficients)
    assert math.gcd(*coefficients) == 1
    assert _atoms(result.reactants) == _atoms(result.products)


@given(
    reactants=st.lists(st.sampled_from(_SPECIES), min_size=1, max_size=3, unique=True),
    products=st.lists(st.sampled_from(_SPECIES), min_size=1, max_size=3, unique=True),
)
@settings(max_examples=150, deadline=None)
def test_any_equation_either_balances_or_says_why(reactants, products) -> None:
    """Most picks have no balance; none may raise, and a balance must still hold."""
    result = balance_equation(" + ".join(reactants) + " -> " + " + ".join(products))
    if result.balanced:
        assert _atoms(result.reactants) == _atoms(result.products)
    else:
        assert result.error


@given(
    parent=st.sampled_from([e for e in ELEMENTS if 3 <= e.number <= 100]),
    neutron_excess=st.integers(min_value=0, max_value=60),
    decay=st.sampled_from(sorted(_DECAYS)),
)
@example(parent=_BY_NUMBER[92], neutron_excess=54, decay="alpha")
@settings(max_examples=150, deadline=None)
def test_a_completed_nuclear_equation_keeps_nucleons_and_protons(
    parent, neutron_excess, decay
) -> None:
    mass_number = 2 * parent.number + neutron_excess
    mass_shift, proton_shift = _DECAYS[decay]
    daughter = _BY_NUMBER[parent.number + proton_shift]
    equation = f"{mass_number}{parent.symbol} -> {mass_number + mass_shift}{daughter.symbol} + ?"
    result = balance_nuclear(equation)
    event("completed" if result.balanced else "no nuclide completes it")
    if not result.balanced:
        return
    for count in ("mass_number", "protons"):
        before = sum(getattr(n, count) * n.coefficient for n in result.reactants)
        after = sum(getattr(n, count) * n.coefficient for n in result.products)
        assert before == after, count


@given(
    data=st.data(),
    value=st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=150, deadline=None)
def test_a_conversion_comes_back_to_where_it_began(data, value) -> None:
    units = data.draw(st.sampled_from(_UNITS))
    unit, target = data.draw(st.sampled_from(units)), data.draw(st.sampled_from(units))
    there = convert(value, unit, target)
    assert convert(there, target, unit) == pytest.approx(value, rel=1e-9)
