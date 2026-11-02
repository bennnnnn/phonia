"""The element table holds the values students look up, checked against reference data.

The row data sits next to the assertions on purpose: a typo in the table (a wrong mass, a
shifted configuration, a swapped group) changes a verified answer for every question that
touches that element, and nothing else in the suite compares a row with an outside source.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.elements import BY_NUMBER, BY_SYMBOL

# symbol, Z, atomic weight (IUPAC conventional or CRC), period, group, Pauling EN, configuration
GOLDEN = [
    ("H", 1, 1.008, 1, 1, 2.20, "1s1"),
    ("Li", 3, 6.94, 2, 1, 0.98, "[He] 2s1"),
    ("C", 6, 12.011, 2, 14, 2.55, "[He] 2s2 2p2"),
    ("N", 7, 14.007, 2, 15, 3.04, "[He] 2s2 2p3"),
    ("O", 8, 15.999, 2, 16, 3.44, "[He] 2s2 2p4"),
    ("F", 9, 18.998, 2, 17, 3.98, "[He] 2s2 2p5"),
    ("Na", 11, 22.990, 3, 1, 0.93, "[Ne] 3s1"),
    ("Mg", 12, 24.305, 3, 2, 1.31, "[Ne] 3s2"),
    ("Al", 13, 26.982, 3, 13, 1.61, "[Ne] 3s2 3p1"),
    ("Si", 14, 28.085, 3, 14, 1.90, "[Ne] 3s2 3p2"),
    ("P", 15, 30.974, 3, 15, 2.19, "[Ne] 3s2 3p3"),
    ("S", 16, 32.06, 3, 16, 2.58, "[Ne] 3s2 3p4"),
    ("Cl", 17, 35.45, 3, 17, 3.16, "[Ne] 3s2 3p5"),
    ("K", 19, 39.098, 4, 1, 0.82, "[Ar] 4s1"),
    ("Ca", 20, 40.078, 4, 2, 1.00, "[Ar] 4s2"),
    ("Cr", 24, 51.996, 4, 6, 1.66, "[Ar] 3d5 4s1"),
    ("Mn", 25, 54.938, 4, 7, 1.55, "[Ar] 3d5 4s2"),
    ("Fe", 26, 55.845, 4, 8, 1.83, "[Ar] 3d6 4s2"),
    ("Ni", 28, 58.693, 4, 10, 1.91, "[Ar] 3d8 4s2"),
    ("Cu", 29, 63.546, 4, 11, 1.90, "[Ar] 3d10 4s1"),
    ("Zn", 30, 65.38, 4, 12, 1.65, "[Ar] 3d10 4s2"),
    ("Br", 35, 79.904, 4, 17, 2.96, "[Ar] 3d10 4s2 4p5"),
    ("Ag", 47, 107.868, 5, 11, 1.93, "[Kr] 4d10 5s1"),
    ("Sn", 50, 118.71, 5, 14, 1.96, "[Kr] 4d10 5s2 5p2"),
    ("I", 53, 126.904, 5, 17, 2.66, "[Kr] 4d10 5s2 5p5"),
    ("Au", 79, 196.967, 6, 11, 2.54, "[Xe] 4f14 5d10 6s1"),
    ("Hg", 80, 200.59, 6, 12, 2.00, "[Xe] 4f14 5d10 6s2"),
    ("Pb", 82, 207.2, 6, 14, 2.33, "[Xe] 4f14 5d10 6s2 6p2"),
]


@pytest.mark.parametrize(("symbol", "number", "mass", "period", "group", "en", "config"), GOLDEN)
def test_golden_element_row(
    symbol: str, number: int, mass: float, period: int, group: int, en: float, config: str
) -> None:
    element = BY_SYMBOL[symbol]
    assert element.number == number
    assert BY_NUMBER[number] is element
    assert element.mass == pytest.approx(mass, abs=0.01)
    assert element.period == period
    assert element.group == group
    assert element.electronegativity == pytest.approx(en, abs=0.005)
    assert element.configuration == config
    assert not element.mass_is_isotope


@pytest.mark.parametrize("symbol", ["He", "Ne", "Ar", "Rn"])
def test_a_noble_gas_with_no_pauling_value_omits_it(symbol: str) -> None:
    assert BY_SYMBOL[symbol].electronegativity is None


@pytest.mark.parametrize(("symbol", "en"), [("Kr", 3.00), ("Xe", 2.60)])
def test_krypton_and_xenon_have_a_pauling_value(symbol: str, en: float) -> None:
    assert BY_SYMBOL[symbol].electronegativity == pytest.approx(en)


def test_only_elements_without_a_standard_weight_carry_an_isotope_mass() -> None:
    # Tc, Pm, and every element from Po on except the three with a standard weight (Th, Pa, U).
    expected = {43, 61, *range(84, 90), *range(93, 119)}
    assert {element.number for element in BY_SYMBOL.values() if element.mass_is_isotope} == expected


def test_a_period_matches_the_noble_gas_core_of_its_configuration() -> None:
    cores = {"He": 1, "Ne": 2, "Ar": 3, "Kr": 4, "Xe": 5, "Rn": 6}
    for element in BY_NUMBER.values():
        if element.configuration.startswith("["):
            core = element.configuration[1 : element.configuration.index("]")]
            assert element.period == cores[core] + 1, element.symbol
