"""A chemistry question in its own words reads into one law, or declines.

The answers themselves are checked against hand-worked values in the corpus
(``corpus.py``); these tests pin what each phrasing binds to and what must decline.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.binding import bind_chemistry_intent, prepare
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.laws import LAWS
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers import solve_chemistry


def _bound(question: str) -> ChemistryIntent:
    intent = bind_chemistry_intent(question)
    assert intent is not None, question
    return intent


@pytest.mark.parametrize(
    ("question", "op", "params", "formula"),
    [
        ("What is the pH of 0.01 M HCl?", "strong_acid_ph", {"concentration": 0.01}, "HCl"),
        (
            "What is the pH of 0.01 M Ca(OH)2?",
            "strong_base_ph",
            {"concentration": 0.01},
            "Ca(OH)2",
        ),
        (
            "What is the pH of 0.1 M acetic acid? Ka = 1.8e-5",
            "weak_acid_ph",
            {"concentration": 0.1, "ka": 1.8e-5},
            "CH3COOH",
        ),
        ("How many moles are in 36 g of water?", "mass_to_moles", {"mass": 36.0}, "H2O"),
        ("Convert 2.5 mol of CO2 to grams.", "moles_to_mass", {"moles": 2.5}, "CO2"),
        (
            "Find the osmotic pressure of 0.1 M glucose at 25 °C.",
            "osmotic_pressure",
            # Glucose does not dissociate, and 25 °C is read as 298.15 K.
            {"i": 1.0, "molarity": 0.1, "temperature": 298.15},
            None,
        ),
        (
            "How many grams of Cu are deposited by a current of 2 A for 1 hour from Cu2+?",
            "electrolysis_mass",
            # Copper's molar mass and its 2+ charge come from the question's words.
            {"molar_mass": 63.546, "current": 2.0, "time": 3600.0, "electrons": 2.0},
            None,
        ),
        (
            # A metal named without its ion takes the galvanic table's school ion, Cu2+.
            "How many grams of copper are deposited by a current of 2 A for 1 hour?",
            "electrolysis_mass",
            {"molar_mass": 63.546, "current": 2.0, "time": 3600.0, "electrons": 2.0},
            None,
        ),
        (
            "Calculate ΔG at 298 K if ΔH = -100 kJ/mol and ΔS = -200 J/mol·K.",
            "gibbs",
            {"delta_h": -100.0, "delta_s": -0.2, "temperature": 298.0},
            None,
        ),
        (
            "A rate constant is 0.01 s^-1 at 300 K and 0.04 s^-1 at 320 K. "
            "Find the activation energy.",
            "arrhenius_two_point",
            {"k1": 0.01, "t1": 300.0, "k2": 0.04, "t2": 320.0},
            None,
        ),
        (
            "A spot travels 3 cm and the solvent front travels 6 cm. Find the Rf value.",
            "chromatography_rf",
            {"spot": 3.0, "front": 6.0},
            None,
        ),
    ],
)
def test_a_question_in_its_own_words_binds_one_law(
    question: str, op: str, params: dict[str, float], formula: str | None
) -> None:
    intent = _bound(question)
    assert intent.chemistry_op == op
    assert intent.params == pytest.approx(params)
    assert intent.formula == formula


def test_a_volume_keeps_the_unit_the_dilution_was_written_in() -> None:
    intent = _bound("50 mL of 2 M HCl is diluted to 200 mL. What is the new concentration?")
    assert intent.params == {"m1": 2.0, "v1": 50.0, "v2": 200.0}
    assert intent.units == {"v1": "mL", "v2": "mL"}


@pytest.mark.parametrize(
    "question",
    [
        # Two strong acids: whose pH?
        "What is the pH of 0.01 M HCl and 0.02 M HNO3?",
        # A pH with no substance named is not a strong-acid pH.
        "What is the pH of a 0.01 M solution?",
        # Two substances, two masses: which moles?
        "10 g of NaCl is dissolved in 500 g of water. How many moles are there?",
        # The question asks for more than the law answers.
        "What is the pH of 0.01 M HCl and explain why it is acidic?",
        # A weak acid's pH needs its Ka.
        "What is the pH of 0.1 M acetic acid?",
        # A value no input takes: two times for one electrolysis.
        "How many grams of Cu are deposited by 2 A for 1 hour and 30 min from Cu2+?",
    ],
)
def test_a_question_that_does_not_fit_one_law_one_way_declines(question: str) -> None:
    assert bind_chemistry_intent(question) is None


def test_a_formulas_digits_are_never_read_as_numbers() -> None:
    prepared = prepare("What is the pH of 0.01 M Ca(OH)2 made from Cu2+?")
    assert "2" not in prepared.text.replace("0.01", "")
    assert prepared.species == ("Ca(OH)2",)


@pytest.mark.parametrize(
    "question",
    [
        "25 mL of 0.1 M HCl is titrated with 0.1 M NaOH. Find the pH after adding 10 mL of NaOH.",
        # The same titration, written titrant first.
        "10 mL of 0.1 M NaOH is added to 25 mL of 0.1 M HCl in a titration. Find the pH.",
        # The added solution's own phrase states its volume once, not twice.
        "25 mL of 0.1 M HCl is titrated by adding 10 mL of 0.1 M NaOH. Find the pH.",
        # The same volume said again is the same statement.
        "25 mL of 0.1 M HCl is titrated with 10 mL of 0.1 M NaOH. "
        "Find the pH after adding 10 mL of NaOH.",
    ],
)
def test_each_titration_volume_belongs_to_the_solution_it_is_of(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None
    assert intent.chemistry_op == "titration_strong"
    assert intent.params == pytest.approx({"ma": 0.1, "va_l": 0.025, "mb": 0.1, "vb_l": 0.01})


@pytest.mark.parametrize(
    "question",
    [
        # No phrase ties the only volume to the titrant.
        "25 mL of 0.1 M HCl is titrated with 0.1 M NaOH. Find the pH.",
        # Two different volumes for one titrant.
        "25 mL of 0.1 M HCl is titrated with 10 mL of 0.1 M NaOH. "
        "Find the pH after adding 20 mL of NaOH.",
        # 0.1 M Ca(OH)2 is 0.2 M OH-; the titration solvers count one OH- per formula unit.
        "25 mL of 0.1 M HCl is titrated with 0.1 M Ca(OH)2. "
        "Find the pH after adding 10 mL of Ca(OH)2.",
    ],
)
def test_a_titration_the_reader_cannot_pair_one_way_declines(question: str) -> None:
    assert extract_chemistry_intent(question) is None


def test_a_law_fit_is_a_chemistry_cue() -> None:
    assert is_chemistry_question("How many moles are in 36 g of water?")
    assert not is_chemistry_question("How many moles are in my garden?")


# One solvable set of inputs per law: every law the binder can read is one its solver answers.
_SAMPLES: dict[str, tuple[dict[str, float], str | None, dict[str, str]]] = {
    "strong_acid_ph": ({"concentration": 0.01}, "HCl", {}),
    "strong_base_ph": ({"concentration": 0.01}, "NaOH", {}),
    "weak_acid_ph": ({"concentration": 0.1, "ka": 1.8e-5}, "CH3COOH", {}),
    "conjugate_salt_ph": ({"concentration": 0.05, "ka": 1.8e-5}, "CH3COONa", {}),
    "weak_base_ph": ({"concentration": 0.1, "kb": 1.8e-5}, "NH3", {}),
    "ph_from_poh": ({"poh": 4.5}, None, {}),
    "buffer_ph": ({"pka": 4.74, "acid": 0.1, "base": 0.2}, None, {}),
    "base_buffer_ph": ({"kb": 1.8e-5, "conjugate": 0.3, "base": 0.2}, None, {}),
    "strong_acid_poh": ({"concentration": 0.01}, "HCl", {}),
    "strong_base_poh": ({"concentration": 0.01}, "NaOH", {}),
    "weak_acid_ka": ({"concentration": 0.1, "ph": 3.5}, None, {}),
    "dilution": ({"m1": 2.0, "v1": 50.0, "v2": 200.0}, None, {"v1": "mL", "v2": "mL"}),
    "freezing_depression": ({"i": 1.0, "kf": 1.86, "molality": 0.5}, None, {}),
    "boiling_elevation": ({"i": 2.0, "kb": 0.512, "molality": 1.0}, None, {}),
    **{
        f"{op}{point}{suffix}": (
            {"i": 1.0, constant: value, **amounts, **({"normal_point": normal} if point else {})},
            formula,
            units,
        )
        for op, constant, value, normal in (
            ("freezing_depression", "kf", 1.86, 273.15),
            ("boiling_elevation", "kb", 0.512, 373.15),
        )
        for point in ("", "_point")
        for suffix, amounts, formula, units in (
            ("", {"molality": 0.5}, None, {}),
            ("_moles", {"moles": 2.0, "solvent_mass": 1.0}, None, {"solvent_mass": "kg"}),
            (
                "_mass",
                {"solute_mass": 10.0, "molar_mass": 58.44, "solvent_mass": 250.0},
                "NaCl",
                {"solvent_mass": "g"},
            ),
        )
        if point or suffix
    },
    "reaction_heat_mass": ({"mass": 32.0, "molar_mass": 16.043, "enthalpy": -890.0}, "CH4", {}),
    "molarity": ({"moles": 0.25, "volume_l": 0.75}, None, {}),
    "solution_mass_mg": (
        {"concentration": 0.2, "volume_l": 0.015, "molar_mass": 74.55},
        "KCl",
        {"answer": "mg"},
    ),
    "osmotic_pressure": ({"i": 1.0, "molarity": 0.1, "temperature": 298.15}, None, {}),
    "mass_to_moles": ({"mass": 36.0}, "H2O", {"mass": "g"}),
    "moles_to_mass": ({"moles": 2.5}, "CO2", {"moles": "mol"}),
    "molecular_formula": ({"molar_mass": 180.0}, "CH2O", {}),
    "percent_yield": ({"actual": 45.0, "theoretical": 50.0}, None, {}),
    "first_order_concentration": (
        {"initial": 1.0, "rate_constant": 0.1, "time": 10.0},
        None,
        {"time": "s"},
    ),
    "zero_order": ({"initial": 1.0, "rate_constant": 0.01, "time": 50.0}, None, {"time": "s"}),
    "second_order": ({"initial": 1.0, "rate_constant": 0.5, "time": 2.0}, None, {"time": "s"}),
    "arrhenius_two_point": ({"k1": 0.01, "t1": 300.0, "k2": 0.04, "t2": 320.0}, None, {}),
    "nernst": (
        {"standard_potential": 1.1, "electrons": 2.0, "quotient": 0.01, "temperature": 298.0},
        None,
        {},
    ),
    "electrolysis_mass": (
        {"molar_mass": 63.546, "current": 2.0, "time": 3600.0, "electrons": 2.0},
        None,
        {},
    ),
    "gibbs": ({"delta_h": -100.0, "delta_s": -0.2, "temperature": 298.0}, None, {}),
    "beer_lambert_concentration": ({"absorbance": 0.5, "epsilon": 100.0, "path": 1.0}, None, {}),
    "beer_lambert_absorbance": ({"epsilon": 100.0, "path": 1.0, "concentration": 0.005}, None, {}),
    "beer_lambert_path": ({"absorbance": 0.5, "epsilon": 100.0, "concentration": 0.005}, None, {}),
    "beer_lambert_epsilon": ({"absorbance": 0.5, "path": 1.0, "concentration": 0.005}, None, {}),
    "percent_error": ({"experimental": 9.8, "accepted": 10.0}, None, {}),
    "chromatography_rf": ({"spot": 3.0, "front": 6.0}, None, {}),
    "solution_mass": ({"concentration": 0.2, "volume_l": 0.5, "molar_mass": 58.44}, "NaCl", {}),
    "molarity_from_mass": (
        {"solute_mass": 5.0, "molar_mass": 58.44, "volume_l": 0.25},
        "NaCl",
        {},
    ),
    "molality_from_mass": (
        {"solute_mass": 18.0, "molar_mass": 180.16, "solvent_kg": 0.5},
        "C6H12O6",
        {},
    ),
    "mass_percent_solvent": ({"solute_mass": 5.0, "solvent_mass": 95.0}, None, {}),
    "parts_per_million": ({"solute_mass": 0.0025, "solution_mass": 1000.0}, None, {}),
    "parts_per_billion": ({"solute_mass": 0.0025, "solution_mass": 1000.0}, None, {}),
    "volume_percent": ({"solute_volume": 25.0, "solution_volume": 500.0}, None, {}),
    "mass_volume_percent": ({"solute_mass": 5.0, "solution_volume": 250.0}, None, {}),
    "particles_to_mass": ({"particles": 3.01e23, "molar_mass": 18.015}, "H2O", {}),
    "mole_fraction": ({"moles_a": 1.0, "moles_b": 9.0}, None, {}),
    "binary_vapor_pressure": (
        {"mole_fraction_a": 0.4, "pressure_a": 0.8, "mole_fraction_b": 0.6, "pressure_b": 0.4},
        None,
        {},
    ),
    "vant_hoff_constant": ({"k1": 1.0, "t1": 300.0, "t2": 350.0, "enthalpy": 50.0}, None, {}),
    "vant_hoff_enthalpy": ({"k1": 0.1, "t1": 300.0, "k2": 0.5, "t2": 350.0}, None, {}),
    "gibbs_from_equilibrium": ({"k": 10.0, "temperature": 298.15}, None, {}),
    "equilibrium_from_gibbs": ({"gibbs": -5.708, "temperature": 298.15}, None, {}),
    "gas_density": ({"pressure": 1.0, "molar_mass": 44.01, "temperature": 273.0}, "CO2", {}),
    "molar_mass_from_density": ({"density": 1.25, "temperature": 273.0, "pressure": 1.0}, None, {}),
    "percent_ionization": ({"concentration": 0.1, "ka": 1.8e-5}, "CH3COOH", {}),
    "reaction_heat": ({"moles": 2.0, "enthalpy": -890.0}, None, {}),
    "electrolysis_time": (
        {"mass": 10.0, "electrons": 2.0, "current": 2.0, "molar_mass": 63.546},
        None,
        {},
    ),
    "ionic_strength": (
        {"concentration_1": 0.1, "charge_1": 2.0, "concentration_2": 0.2, "charge_2": 1.0},
        None,
        {},
    ),
    "absorbance_transmittance": ({"transmittance": 0.1}, None, {}),
    "absorbance_percent_transmittance": ({"percent_transmittance": 10.0}, None, {}),
    "kirchhoff": (
        {"enthalpy": -50.0, "t1": 298.0, "t2": 398.0, "heat_capacity": 0.04},
        None,
        {},
    ),
    "optical_purity": ({"observed": 8.5, "pure": 17.0}, None, {}),
    "partition_coefficient": ({"organic": 0.4, "aqueous": 0.1}, None, {}),
    "vant_hoff_factor": ({"delta_t": 0.372, "constant": 1.86, "molality": 0.2}, None, {}),
    "hydrogen_deficiency": (
        {"carbon": 5.0, "hydrogen": 8.0, "nitrogen": 1.0, "halogen": 1.0},
        None,
        {},
    ),
    "specific_rotation": ({"observed": 10.0, "path_length": 2.0, "concentration": 0.5}, None, {}),
    "enantiomeric_excess": ({"major": 0.7, "minor": 0.3}, None, {}),
    "gibbs_reaction": ({"gibbs_standard": -10.0, "temperature": 298.0, "quotient": 0.1}, None, {}),
    "van_der_waals_pressure": (
        {"n": 1.0, "temperature": 300.0, "volume": 2.0, "a": 1.0, "b": 0.05},
        None,
        {},
    ),
    "compressibility": (
        {"pressure": 2.0, "volume": 1.0, "n": 1.0, "temperature": 300.0},
        None,
        {},
    ),
    "phase_rule": ({"components": 2.0, "phases": 2.0}, None, {}),
    "mixture_concentration": (
        {"concentration_1": 1.0, "volume_1": 0.1, "concentration_2": 0.2, "volume_2": 0.3},
        None,
        {},
    ),
    "entropy_volume": ({"n": 1.0, "volume_1": 1.0, "volume_2": 2.0}, None, {}),
    "entropy_temperature": (
        {"n": 2.0, "heat_capacity": 30.0, "t1": 300.0, "t2": 600.0},
        None,
        {},
    ),
    "clapeyron": (
        {"temperature": 373.0, "delta_v": 0.03, "delta_p": 1000.0, "delta_t": 1.0},
        None,
        {},
    ),
    "langmuir": ({"affinity": 2.0, "pressure": 1.0}, None, {}),
    "eyring": ({"temperature": 300.0, "delta_h": 50000.0, "delta_s": 0.0}, None, {}),
    "crystal_field_stabilization": ({"n_t2g": 6.0, "n_eg": 0.0, "delta_o": 100.0}, None, {}),
    "molar_conductivity": ({"conductivity": 1.0, "concentration": 100.0}, None, {}),
    "neutron_count": ({"mass_number": 23.0, "atomic_number": 11.0}, None, {}),
    "ion_charge": ({"atomic_number": 11.0, "electron_count": 10.0}, None, {}),
    "shell_capacity": ({"shell_n": 3.0}, None, {}),
    "bond_order": ({"bonding": 8.0, "antibonding": 4.0}, None, {}),
    "wavenumber": ({"wavelength": 500.0}, None, {}),
    "quantum_yield": ({"events": 50.0, "photons": 200.0}, None, {}),
    "tetrahedral_splitting": ({"delta_o": 90.0}, None, {}),
    "base_buffer_poh": ({"pkb": 4.74, "conjugate": 0.1, "base": 0.2}, None, {}),
    "molar_heat": ({"moles": 2.0, "heat_capacity": 75.0, "delta_t": 10.0}, None, {}),
    "electron_moles": ({"current": 1.0, "time": 10.0}, None, {}),
    "hill_saturation": ({"ligand": 2.0, "hill_n": 1.0, "dissociation": 2.0}, None, {}),
    "freundlich": ({"coefficient": 2.0, "concentration": 4.0, "exponent": 2.0}, None, {}),
    "degree_of_polymerization": ({"polymer_mass": 10000.0, "repeat_mass": 100.0}, None, {}),
    "polydispersity": ({"weight_average": 20000.0, "number_average": 10000.0}, None, {}),
    "carothers": ({"extent": 0.5}, None, {}),
    "polymerization_rate": ({"rate_constant": 2.0, "monomer": 3.0, "radical": 4.0}, None, {}),
    "butler_volmer": (
        {
            "exchange": 1e-6,
            "alpha": 0.5,
            "electrons": 1.0,
            "overpotential": 0.01,
            "temperature": 298.0,
        },
        None,
        {},
    ),
    "tafel": ({"intercept": 0.1, "slope": 0.12, "current": 0.01}, None, {}),
    "electrochemical_potential": (
        {"chemical_potential": 1000.0, "charge_number": 1.0, "electric_potential": 0.1},
        None,
        {},
    ),
    "chemical_potential": (
        {"standard_potential": -10000.0, "temperature": 298.0, "activity": 0.5},
        None,
        {},
    ),
    "activity": ({"gamma": 0.8, "concentration": 0.1, "standard_concentration": 1.0}, None, {}),
    "larmor": ({"gyromagnetic": 2.675e8, "field": 1.0}, None, {}),
    "chemical_shift": (
        {"sample_freq": 4.00004e8, "reference_freq": 4.0e8, "spectrometer_freq": 4.0e8},
        None,
        {},
    ),
    "magnetic_sector": ({"field": 0.5, "radius": 0.1, "voltage": 1000.0}, None, {}),
    "cubic_spacing": (
        {"lattice": 0.4, "miller_h": 1.0, "miller_k": 1.0, "miller_l": 1.0},
        None,
        {},
    ),
    "lever_alpha": (
        {"alpha_composition": 0.2, "beta_composition": 0.8, "overall": 0.5},
        None,
        {},
    ),
    "lever_beta": (
        {"alpha_composition": 0.2, "beta_composition": 0.8, "overall": 0.5},
        None,
        {},
    ),
    "mean_square_displacement": ({"diffusion": 1e-5, "time": 10.0}, None, {}),
    "stokes_einstein": ({"temperature": 298.0, "viscosity": 0.001, "radius": 1.0}, None, {}),
    "relative_standard_deviation": ({"deviation": 0.2, "mean": 10.0}, None, {}),
    "conjugate_fraction": ({"ka": 1e-5, "hydrogen": 1e-4}, None, {}),
    "acid_fraction": ({"ka": 1e-5, "hydrogen": 1e-4}, None, {}),
    "conjugate_fraction_ph": ({"ka": 1e-5, "ph": 4.0}, None, {}),
    "acid_fraction_ph": ({"ka": 1e-5, "ph": 4.0}, None, {}),
}


def test_every_law_has_a_sample() -> None:
    assert set(_SAMPLES) == {law.spec.id for law in LAWS}


@pytest.mark.parametrize("law", LAWS, ids=[law.spec.id for law in LAWS])
def test_every_law_promises_inputs_its_solver_answers(law: object) -> None:
    from app.modules.chemistry.laws import ChemistryLaw

    assert isinstance(law, ChemistryLaw) and law.spec.binding is not None
    params, formula, units = _SAMPLES[law.spec.id]
    assert frozenset(params) in law.spec.binding.inputs
    intent = ChemistryIntent(
        kind=law.kind,  # type: ignore[arg-type]
        chemistry_op=law.op,
        params=params,
        units=units,
        formula=formula,
    )
    assert solve_chemistry(intent).answer
