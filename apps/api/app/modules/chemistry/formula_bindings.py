"""How a one-line chemistry law is named in a question.

The arithmetic lives in ``formula_laws``. ``laws.LAWS`` concatenates these bindings
with the laws written by hand.
"""

from __future__ import annotations

from app.modules.chemistry.law_record import (
    _ELECTROLYSIS_CUES,
    _MILLIGRAM_ASKS,
    _MOLAL,
    _MOLAR,
    _SOLUTE_WORDS,
    _SOLVENT_WORDS,
    ChemistryLaw,
    _law,
)
from app.services.law_binding.spec import VariableSpec, var
from app.services.units import CELSIUS_OFFSET_K


def _concentration() -> VariableSpec:
    return var("concentration", "C", _MOLAR)


# STP is 0 °C and 1 atm; a question that also states a pressure or temperature declines.
def _stp_pressure() -> VariableSpec:
    return var("pressure", "P", "atmosphere", implied=(("stp", 1.0),))


def _stp_temperature() -> VariableSpec:
    return var("temperature", "T", "kelvin", implied=(("stp", CELSIUS_OFFSET_K),))


def _molar_mass() -> VariableSpec:
    """The molar mass of the substance the question names, unless it states one."""
    return var("molar_mass", "M", "gram / mole", fallback="species_molar_mass")


_GRAMS_ASKS = ("how many grams", "grams", "mass")

# Laws that are one line of arithmetic (formula_laws), read from a question in its words.
FORMULA_LAW_BINDINGS: tuple[ChemistryLaw, ...] = (
    _law(
        "solution_mass",
        "solutions",
        _GRAMS_ASKS,
        "gram",
        (var("concentration", "c", _MOLAR), var("volume_l", "V", "liter"), _molar_mass()),
        cues=("solution",),
        species="compound",
    ),
    _law(
        "solution_mass",
        "solutions",
        _MILLIGRAM_ASKS,
        "gram",
        (var("concentration", "c", _MOLAR), var("volume_l", "V", "liter"), _molar_mass()),
        name="solution_mass_mg",
        cues=("solution",),
        species="compound",
        labels=(("answer", "mg"),),
    ),
    _law(
        "molality_from_mass",
        "solutions",
        ("molality",),
        _MOLAL,
        (
            var("solute_mass", "m", "gram", words=_SOLUTE_WORDS),
            _molar_mass(),
            var("solvent_kg", "m", "kilogram", words=_SOLVENT_WORDS),
        ),
        species="solute",
    ),
    _law(
        "mass_percent_solvent",
        "solutions",
        ("mass percent", "percent by mass", "mass percentage"),
        "percent",
        (
            var("solute_mass", "m", "gram", words=_SOLUTE_WORDS, needs_words=True),
            var("solvent_mass", "m", "gram", words=_SOLVENT_WORDS, needs_words=True),
        ),
    ),
    _law(
        "parts_per_million",
        "solutions",
        ("parts per million", "ppm"),
        "dimensionless",
        (
            var("solute_mass", "m", "gram", words=_SOLUTE_WORDS, needs_words=True),
            var("solution_mass", "m", "gram", words=("solution",), needs_words=True),
        ),
    ),
    _law(
        "parts_per_billion",
        "solutions",
        ("parts per billion", "ppb"),
        "dimensionless",
        (
            var("solute_mass", "m", "gram", words=_SOLUTE_WORDS, needs_words=True),
            var("solution_mass", "m", "gram", words=("solution",), needs_words=True),
        ),
    ),
    _law(
        "volume_percent",
        "solutions",
        ("volume percent", "percent by volume"),
        "percent",
        (
            var("solute_volume", "V", "milliliter", words=_SOLUTE_WORDS, needs_words=True),
            var("solution_volume", "V", "milliliter", words=("solution",), needs_words=True),
        ),
    ),
    _law(
        "mass_volume_percent",
        "solutions",
        ("mass/volume percent", "mass-volume percent", "percent m/v"),
        "percent",
        (
            var("solute_mass", "m", "gram", words=_SOLUTE_WORDS, needs_words=True),
            var("solution_volume", "V", "milliliter", words=("solution",), needs_words=True),
        ),
    ),
    _law(
        "particles_to_mass",
        "amounts",
        _GRAMS_ASKS,
        "gram",
        (
            # Molecules, not atoms: 3.01e23 atoms of O2 are half as many molecules.
            var(
                "particles",
                "N",
                dimensionless=True,
                words=("molecules", "particles", "formula units"),
                needs_words=True,
            ),
            _molar_mass(),
        ),
        species="compound",
    ),
    _law(
        "mole_fraction",
        "solutions",
        # The asked part is the solute: "the mole fraction of water" is not this reading.
        ("mole fraction of compound", "mole fraction of the compound"),
        "dimensionless",
        (
            var("moles_a", "nA", "mole", words=_SOLUTE_WORDS, needs_words=True),
            var("moles_b", "nB", "mole", words=_SOLVENT_WORDS, needs_words=True),
        ),
    ),
    _law(
        "binary_vapor_pressure",
        "solutions",
        ("total vapor pressure",),
        "atmosphere",
        (
            var(
                "mole_fraction_a",
                "XA",
                dimensionless=True,
                words=("mole fraction of a", "xa"),
                needs_words=True,
            ),
            var(
                "pressure_a",
                "PA",
                "atmosphere",
                words=("vapor pressure of a", "pa"),
                needs_words=True,
            ),
            var(
                "mole_fraction_b",
                "XB",
                dimensionless=True,
                words=("mole fraction of b", "xb"),
                needs_words=True,
            ),
            var(
                "pressure_b",
                "PB",
                "atmosphere",
                words=("vapor pressure of b", "pb"),
                needs_words=True,
            ),
        ),
    ),
    _law(
        "vant_hoff_constant",
        "equilibrium",
        ("k2", "equilibrium constant"),
        "dimensionless",
        (
            var("k1", "K1", dimensionless=True, words=("k1",), needs_words=True),
            var("t1", "T1", "kelvin", words=("t1",), needs_words=True),
            var("t2", "T2", "kelvin", words=("t2",), needs_words=True),
            var("enthalpy", "ΔH", "kilojoule / mole", words=("delta_h", "enthalpy")),
        ),
        cues=("van 't hoff", "van't hoff", "vant hoff"),
        excludes=("clausius",),
        nonnegative=False,
    ),
    _law(
        "vant_hoff_enthalpy",
        "equilibrium",
        ("delta_h", "enthalpy"),
        "kilojoule / mole",
        (
            var("k1", "K1", dimensionless=True, words=("k1",), needs_words=True),
            var("t1", "T1", "kelvin", words=("t1",), needs_words=True),
            var("k2", "K2", dimensionless=True, words=("k2",), needs_words=True),
            var("t2", "T2", "kelvin", words=("t2",), needs_words=True),
        ),
        cues=("van 't hoff", "van't hoff", "vant hoff"),
        excludes=("clausius",),
        nonnegative=False,
    ),
    _law(
        "gibbs_from_equilibrium",
        "equilibrium",
        ("delta_g", "gibbs", "free energy", "free-energy"),
        "kilojoule / mole",
        (
            var(
                "k",
                "K",
                dimensionless=True,
                words=("k =", "k=", "equilibrium constant"),
                needs_words=True,
            ),
            var("temperature", "T", "kelvin"),
        ),
        excludes=("delta_h", "delta_s"),
        nonnegative=False,
    ),
    _law(
        "equilibrium_from_gibbs",
        "equilibrium",
        ("equilibrium constant", "k"),
        "dimensionless",
        (
            var("gibbs", "ΔG", "kilojoule / mole", words=("delta_g",), needs_words=True),
            var("temperature", "T", "kelvin"),
        ),
        excludes=("delta_h", "delta_s"),
    ),
    _law(
        "gas_density",
        "gases",
        ("density",),
        "gram / liter",
        (_stp_pressure(), _molar_mass(), _stp_temperature()),
        cues=("gas", "stp"),
        species="compound",
    ),
    _law(
        "molar_mass_from_density",
        "gases",
        ("molar mass",),
        "gram / mole",
        (var("density", "d", "gram / liter"), _stp_temperature(), _stp_pressure()),
        cues=("gas",),
    ),
    _law(
        "percent_ionization",
        "acid_base",
        ("percent ionization", "percentage ionization", "% ionization", "percent dissociation"),
        "percent",
        (_concentration(), var("ka", "Ka", dimensionless=True, words=("k_a",), needs_words=True)),
        species="acid_weak",
    ),
    _law(
        "reaction_heat",
        "thermochemistry",
        ("how much heat", "heat", "energy"),
        "kilojoule",
        (var("moles", "n", "mole"), var("enthalpy", "ΔH", "kilojoule / mole")),
        nonnegative=False,
        no_equation=True,
    ),
    _law(
        "reaction_heat_mass",
        "thermochemistry",
        ("how much heat", "heat", "energy"),
        "kilojoule",
        (var("mass", "m", "gram"), _molar_mass(), var("enthalpy", "ΔH", "kilojoule / mole")),
        species="compound",
        nonnegative=False,
        no_equation=True,
    ),
    _law(
        "electrolysis_time",
        "electrochemistry",
        ("how long", "time"),
        "second",
        (
            var("mass", "m", "gram"),
            var(
                "electrons",
                "n",
                dimensionless=True,
                words=("n =", "electrons"),
                needs_words=True,
                fallback="ion_charge",
            ),
            var("current", "I", "ampere"),
            var("molar_mass", "M", "gram / mole", fallback="deposited_molar_mass"),
        ),
        cues=_ELECTROLYSIS_CUES,
    ),
    _law(
        "ionic_strength",
        "solutions",
        ("ionic strength",),
        _MOLAR,
        (
            var("concentration_1", "c1", _MOLAR, words=("cation concentration",), needs_words=True),
            var("charge_1", "z1", dimensionless=True, words=("cation charge",), needs_words=True),
            var("concentration_2", "c2", _MOLAR, words=("anion concentration",), needs_words=True),
            var("charge_2", "z2", dimensionless=True, words=("anion charge",), needs_words=True),
        ),
        excludes=("debye", "huckel", "hückel", "activity"),
        nonnegative=False,
    ),
    _law(
        "absorbance_transmittance",
        "spectroscopy",
        ("absorbance",),
        "dimensionless",
        (
            var(
                "transmittance",
                "T",
                dimensionless=True,
                words=("transmittance",),
                needs_words=True,
            ),
        ),
        excludes=("percent transmittance", "percent t", "beer", "epsilon", "absorptivity"),
    ),
    _law(
        "absorbance_percent_transmittance",
        "spectroscopy",
        ("absorbance",),
        "dimensionless",
        (
            var(
                "percent_transmittance",
                "%T",
                "percent",
                words=("percent transmittance", "percent t"),
                needs_words=True,
            ),
        ),
        excludes=("beer", "epsilon", "absorptivity"),
    ),
    _law(
        "kirchhoff",
        "thermochemistry",
        ("enthalpy", "delta_h"),
        "kilojoule / mole",
        (
            var(
                "enthalpy",
                "ΔH",
                "kilojoule / mole",
                words=("delta_h", "enthalpy"),
                needs_words=True,
            ),
            var("t1", "T1", "kelvin", words=("t1",), needs_words=True),
            var("t2", "T2", "kelvin", words=("t2",), needs_words=True),
            var(
                "heat_capacity",
                "ΔCp",
                "kilojoule / mole / kelvin",
                words=("delta_cp", "heat capacity", "cp"),
                needs_words=True,
            ),
        ),
        cues=("kirchhoff",),
        nonnegative=False,
    ),
    _law(
        "optical_purity",
        "organic",
        ("optical purity",),
        "percent",
        (
            var("observed", "a_obs", dimensionless=True, words=("observed",), needs_words=True),
            var("pure", "a_pure", dimensionless=True, words=("pure",), needs_words=True),
        ),
        nonnegative=False,
    ),
    _law(
        "partition_coefficient",
        "solutions",
        ("partition coefficient", "distribution coefficient"),
        "dimensionless",
        (
            var("organic", "org", _MOLAR, words=("organic",), needs_words=True),
            var("aqueous", "aq", _MOLAR, words=("aqueous",), needs_words=True),
        ),
        excludes=("successive", "stages", "repeated"),
    ),
    _law(
        "vant_hoff_factor",
        "solutions",
        ("van 't hoff factor", "vant hoff factor"),
        "dimensionless",
        (
            # The stated degrees are the change. 0.372 °C is not 273.5 K.
            var(
                "delta_t",
                "ΔT",
                "kelvin",
                words=(
                    "freezing point depression",
                    "boiling point elevation",
                    "temperature change",
                ),
                needs_words=True,
            ),
            var(
                "constant",
                "K",
                "kelvin * kilogram / mole",
                words=("k_f", "k_b", "colligative"),
                needs_words=True,
            ),
            var("molality", "m", _MOLAL),
        ),
        keep_units=("delta_t",),
    ),
    _law(
        "hydrogen_deficiency",
        "organic",
        ("index of hydrogen deficiency", "hydrogen deficiency", "degree of unsaturation"),
        "dimensionless",
        (
            var("carbon", "C", dimensionless=True, words=("carbon",), needs_words=True),
            var("hydrogen", "H", dimensionless=True, words=("hydrogen",), needs_words=True),
            var("nitrogen", "N", dimensionless=True, words=("nitrogen",), needs_words=True),
            var("halogen", "X", dimensionless=True, words=("halogen",), needs_words=True),
        ),
    ),
    _law(
        "specific_rotation",
        "organic",
        ("specific rotation",),
        "dimensionless",
        (
            var("observed", "alpha", dimensionless=True, words=("observed",), needs_words=True),
            var("path_length", "l", "decimeter", words=("path",), needs_words=True),
            var(
                "concentration",
                "c",
                "gram / milliliter",
                words=("concentration",),
                needs_words=True,
            ),
        ),
        cues=("specific rotation",),
        excludes=("optical purity", "enantiomeric"),
        nonnegative=False,
    ),
    _law(
        "enantiomeric_excess",
        "organic",
        ("enantiomeric excess",),
        "percent",
        (
            var("major", "major", "mole", words=("major",), needs_words=True),
            var("minor", "minor", "mole", words=("minor",), needs_words=True),
        ),
    ),
    _law(
        "gibbs_reaction",
        "thermochemistry",
        ("delta_g", "gibbs energy"),
        "kilojoule / mole",
        (
            var(
                "gibbs_standard",
                "dG0",
                "kilojoule / mole",
                words=("standard", "delta_g_standard"),
                needs_words=True,
            ),
            var("temperature", "T", "kelvin"),
            var(
                "quotient",
                "Q",
                dimensionless=True,
                words=("reaction quotient", "quotient"),
                needs_words=True,
            ),
        ),
        cues=("reaction quotient", "quotient"),
        nonnegative=False,
    ),
    _law(
        "van_der_waals_pressure",
        "gases",
        ("pressure",),
        "atmosphere",
        (
            var("n", "n", "mole"),
            var("temperature", "T", "kelvin"),
            var("volume", "V", "liter"),
            var("a", "a", dimensionless=True, words=("a =", "a="), needs_words=True),
            var("b", "b", dimensionless=True, words=("b =", "b="), needs_words=True),
        ),
        cues=("van der waals",),
    ),
    _law(
        "compressibility",
        "gases",
        ("compressibility",),
        "dimensionless",
        (
            var("pressure", "P", "atmosphere"),
            var("volume", "V", "liter"),
            var("n", "n", "mole"),
            var("temperature", "T", "kelvin"),
        ),
        cues=("compressibility",),
    ),
    _law(
        "phase_rule",
        "thermochemistry",
        ("degrees of freedom",),
        "dimensionless",
        (
            var("components", "C", dimensionless=True, words=("component",), needs_words=True),
            var("phases", "P", dimensionless=True, words=("phase",), needs_words=True),
        ),
        cues=("phase rule",),
    ),
    _law(
        "mixture_concentration",
        "solutions",
        ("concentration after mixing", "mixture concentration"),
        _MOLAR,
        (
            var(
                "concentration_1",
                "C1",
                _MOLAR,
                words=("first concentration",),
                needs_words=True,
            ),
            var("volume_1", "V1", "liter", words=("first volume",), needs_words=True),
            var(
                "concentration_2",
                "C2",
                _MOLAR,
                words=("second concentration",),
                needs_words=True,
            ),
            var("volume_2", "V2", "liter", words=("second volume",), needs_words=True),
        ),
        cues=("after mixing", "mixture"),
    ),
    _law(
        "entropy_volume",
        "thermochemistry",
        ("entropy",),
        "joule / kelvin",
        (
            var("n", "n", "mole"),
            var("volume_1", "V1", "liter", words=("initial volume",), needs_words=True),
            var("volume_2", "V2", "liter", words=("final volume",), needs_words=True),
        ),
        cues=("volume",),
        excludes=("heat capacity", "temperature"),
    ),
    _law(
        "entropy_temperature",
        "thermochemistry",
        ("entropy",),
        "joule / kelvin",
        (
            var("n", "n", "mole"),
            var(
                "heat_capacity",
                "Cp",
                "joule / mole / kelvin",
                words=("heat capacity", "cp"),
                needs_words=True,
            ),
            var("t1", "T1", "kelvin", words=("t1",), needs_words=True),
            var("t2", "T2", "kelvin", words=("t2",), needs_words=True),
        ),
        cues=("heat capacity",),
    ),
    _law(
        "clapeyron",
        "thermochemistry",
        ("enthalpy", "delta_h"),
        "kilojoule / mole",
        (
            var("temperature", "T", "kelvin", words=("temperature is", "t ="), needs_words=True),
            var(
                "delta_v",
                "dV",
                "meter ** 3 / mole",
                words=("volume change",),
                needs_words=True,
            ),
            var("delta_p", "dP", "pascal", words=("pressure change",), needs_words=True),
            var("delta_t", "dT", "kelvin", words=("temperature change",), needs_words=True),
        ),
        cues=("clapeyron",),
        excludes=("clausius",),
        keep_units=("delta_t",),
        nonnegative=False,
    ),
    _law(
        "langmuir",
        "analytical",
        ("coverage", "surface coverage"),
        "dimensionless",
        (
            var(
                "affinity",
                "K",
                "1 / atmosphere",
                words=("langmuir constant", "affinity"),
                needs_words=True,
            ),
            var("pressure", "P", "atmosphere"),
        ),
        cues=("langmuir",),
    ),
    _law(
        "eyring",
        "kinetics",
        ("rate constant",),
        "1 / second",
        (
            var("temperature", "T", "kelvin"),
            var(
                "delta_h",
                "dH",
                "joule / mole",
                words=("activation enthalpy", "delta_h"),
                needs_words=True,
            ),
            var(
                "delta_s",
                "dS",
                "joule / mole / kelvin",
                words=("activation entropy", "delta_s"),
                needs_words=True,
            ),
        ),
        cues=("eyring",),
        nonnegative=False,
    ),
    _law(
        "crystal_field_stabilization",
        "inorganic",
        ("crystal field stabilization", "stabilization energy"),
        "kilojoule / mole",
        (
            var("n_t2g", "nt2g", dimensionless=True, words=("t2g",), needs_words=True),
            var("n_eg", "neg", dimensionless=True, words=("eg",), needs_words=True),
            var(
                "delta_o",
                "do",
                "kilojoule / mole",
                words=("delta_o", "splitting"),
                needs_words=True,
            ),
        ),
        excludes=("pairing", "tetrahedral"),
    ),
    _law(
        "molar_conductivity",
        "analytical",
        ("molar conductivity",),
        "siemens * meter ** 2 / mole",
        (
            var(
                "conductivity",
                "kappa",
                "siemens / meter",
                words=("conductivity",),
                needs_words=True,
            ),
            var("concentration", "c", "mole / meter ** 3"),
        ),
        cues=("molar conductivity",),
    ),
)
