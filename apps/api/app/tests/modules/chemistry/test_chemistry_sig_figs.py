# ruff: noqa: RUF003 -- answers and notes use a multiplication sign and a true minus sign.
"""Answers keep the precision their question was written in.

Each given's significant figures are read from the text: the answer takes the fewest, kept
between two and four. A typed value is echoed as typed, a pH has as many decimals as its data
have figures, a sum of givens keeps their decimal places, and a molar mass stays at full
precision until the answer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.sig_figs import as_written, decimals_of, figures_of
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.display import num, p_value
from app.modules.chemistry.solvers.types import ChemistryResult


def _solve(question: str) -> ChemistryResult:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return solve_chemistry(intent)


@pytest.mark.parametrize(
    ("literal", "figures", "decimals"),
    [
        ("0.0050", 2, 4),
        ("1.10", 3, 2),
        ("200", 3, 0),
        ("4.50", 3, 2),
        ("1.8e-5", 2, 1),
        ("-0.76", 2, 2),
        ("0", 1, 0),
    ],
)
def test_a_typed_number_has_its_figures_and_places(
    literal: str, figures: int, decimals: int
) -> None:
    assert figures_of(literal) == figures
    assert decimals_of(literal) == decimals


@pytest.mark.parametrize(
    ("literal", "shown"),
    [("1.80e-5", "1.80 × 10^-5"), ("2.5E4", "2.5 × 10^4"), ("0.02370", "0.02370")],
)
def test_a_typed_number_is_shown_as_typed(literal: str, shown: str) -> None:
    assert as_written(literal) == shown


def test_a_typed_value_keeps_its_trailing_zero() -> None:
    result = _solve("Find ΔG° for a cell with n = 2 and E° = 1.10 V.")
    assert result.given == ("n = 2 mol e-", "E°cell = 1.10 V")
    assert result.answer == "ΔG° = -212 kJ/mol"
    kp = _solve("Convert Kc to Kp: Kc=0.02370 at T=298 K for N2 + H2 -> NH3")
    assert kp.given[0] == "Kc = 0.02370"


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        # One significant figure is raised to the two-figure floor.
        ("How many moles of H2O from 4 mol H2 in H2 + O2 -> H2O?", "n(H2O) = 4.0 mol H2O"),
        # Six figures are cut to the four-figure ceiling.
        ("How many moles are in 36.0400 g of H2O?", "n(H2O) = 2.001 mol"),
        (
            "Find the freezing point depression when i=1, Kf=1.86, and molality=0.500",
            "ΔTf = 0.930 °C",
        ),
    ],
    ids=["floor", "ceiling", "count-does-not-limit"],
)
def test_the_answer_has_the_fewest_figures_of_the_measured_givens(
    question: str, answer: str
) -> None:
    assert _solve(question).answer == answer


def test_a_celsius_reading_has_the_figures_of_its_kelvin_value() -> None:
    # 25 °C is 298 K, three figures, so 760 − 23.8 mmHg shows as 736, not 740.
    result = _solve("Gas collected over water at 25 °C with total pressure=760 mmHg")
    assert result.answer == "Pdry = 736 mmHg"


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        # 50.00 kJ is stored as 50000 J and 25 °C as 298.15 K: the kelvin reading's three
        # figures still limit the answer, not just the 1.000e10 that matched as typed.
        ("Arrhenius: A = 1.000e10 s^-1, Ea = 50.00 kJ/mol, T = 25 °C. Find k.", "k = 17.4 s⁻¹"),
        ("Arrhenius: A = 1.000e10 s^-1, Ea = 50.00 kJ/mol, T = 298.0 K. Find k.", "k = 17.22 s⁻¹"),
        # 152 mmHg is stored in atm; its three figures carry over.
        ("Find Kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=152 mmHg", "Kp = 0.200"),
    ],
)
def test_a_converted_given_keeps_the_figures_it_was_typed_with(question: str, answer: str) -> None:
    assert _solve(question).answer == answer


def test_a_number_that_ends_a_sentence_keeps_its_figures() -> None:
    # "1.8e-10." is 1.8e-10 and a full stop, not 1.8 and a stray "e-10".
    result = _solve("Ksp = 1.8e-10. Find the molar solubility for AgCl(s) -> Ag+ + Cl-.")
    assert result.answer == "s = 1.3 × 10^-5 mol/L"


def test_one_value_typed_two_ways_is_limited_by_both() -> None:
    intent = extract_chemistry_intent("Cell potential: cathode = 0.80 V, anode = 0.8 V")
    assert intent is not None
    # The anode's one decimal place limits the difference; neither 0.8 is echoed as the other.
    assert intent.decimals == 1
    assert intent.written == {}
    assert solve_chemistry(intent).answer == "E°cell = 0.0 V"


def test_a_coefficient_never_limits_a_measured_value_equal_to_it() -> None:
    # The equation's 2s are counts; the 2.00 g of hydrogen has three figures.
    result = _solve("2 H2 + O2 -> 2 H2O. How many grams of water form from 2.00 g of H2?")
    assert result.answer == "m(H2O) = 17.9 g"


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Find pH when [H+] = 2.5 × 10^-4", "pH = 3.60"),
        ("Find the strong acid pH of 0.0010 M HCl", "pH = 3.00"),
        ("Find the strong base pH of 0.010 M NaOH", "pH = 12.00"),
        ("Find pH when pOH = 3.25", "pH = 10.75"),
        ("Find buffer pH with pKa=4.756, [A-]=0.20 and [HA]=0.10", "pH = 5.06"),
        ("Find the pKa if Ka = 1.8 × 10^-5", "pKa = 4.74"),
    ],
)
def test_a_logarithm_has_as_many_places_as_its_data_have_figures(
    question: str, answer: str
) -> None:
    assert _solve(question).answer == answer


def test_a_concentration_from_a_ph_has_as_many_figures_as_the_ph_has_places() -> None:
    assert _solve("Find [H+] when pH = 4.50").answer == "[H+] = 3.2 × 10^-5 mol/L"


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Find the cell potential when cathode=0.34 V and anode=-0.76 V", "E°cell = 1.10 V"),
        (
            "Find the formation enthalpy for H2 + Cl2 -> 2HCl when ΔHf(HCl)=-92.3 kJ/mol",
            "ΔH° = -184.6 kJ/mol",
        ),
        # The multipliers are whole numbers, so only the enthalpies' places count.
        (
            "Use Hess's law: ΔH1=-200.5 kJ, multiplier1=1, ΔH2=50.25 kJ, multiplier2=2",
            "ΔH = -100.0 kJ",
        ),
        ("Find the cell potential when cathode=0.80 V and anode=0.80 V", "E°cell = 0.00 V"),
    ],
)
def test_a_sum_of_givens_keeps_their_fewest_decimal_places(question: str, answer: str) -> None:
    assert _solve(question).answer == answer


def test_a_table_cell_potential_keeps_the_tables_hundredths() -> None:
    result = _solve("Find the galvanic cell for Al and Cu")
    assert result.answer.startswith("E°cell = 2.00 V\n")
    assert result.given == ("Al E° = -1.66 V", "Cu E° = 0.34 V")


def test_a_molar_mass_stays_full_precision_until_the_answer() -> None:
    # 4.000 / 2.016 × 18.015 is 35.74 g; rounding to 2.02 and 18.02 first gave 35.68 g.
    water = _solve("How many grams of water are produced from 4.000 g of H2 in 2H2 + O2 -> 2H2O?")
    assert water.answer == "m(H2O) = 35.74 g"
    assert water.substitution[-1] == "m(H2O) = 1.984 × 18.015 = 35.74 g"
    excess = _solve(
        "In 2H2 + O2 -> 2H2O, 10.00 g of H2 reacts with 64.00 g of O2. Find the limiting reagent."
    )
    assert "excess H2 = (4.960 − 4.000) × 2.016 = 1.935 g" in excess.substitution
    assert _solve("What is the molar mass of H2SO4?").answer == "M(H2SO4) = 98.07 g/mol"


def test_numbers_outside_a_solve_keep_the_default_format() -> None:
    assert num(2.0) == "2"
    assert p_value(4.7447) == "4.745"


@pytest.mark.parametrize(
    "written",
    [{"1.0": "<b>1</b>"}, {"1.0": "1 kg"}, {"1.0": "1" * 33}],
    ids=["markup", "unit", "too-long"],
)
def test_written_holds_only_a_number_as_typed(written: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ChemistryIntent(kind="amounts", chemistry_op="molar_mass", formula="H2O", written=written)


def test_a_long_literal_is_not_recorded() -> None:
    intent = extract_chemistry_intent(
        "How many moles are in 36.000000000000000000000000000001 g of H2O?"
    )
    assert intent is not None
    assert intent.written == {}
    ChemistryIntent.model_validate(intent.model_dump())
