"""The chemistry laws a question can be read into in its own words.

Each law is a ``FormulaSpec`` for the shared binder (``services.law_binding``) whose
variables are its solver's parameters, in the unit that solver reads them in: the binder
converts a stated 500 mL to the 0.5 L a molarity solver expects. The solver stays the one
in ``solvers/``; a law here only says how a question names its inputs and its ask.

Words are matched in the binder's prepared text (``binding.prepare``): case-sensitive
symbols are spelled out ("pH" is ``p_h``, "Ka" is ``k_a``, "E°" is ``e_standard``), and a
named substance is its role (``acid_strong``, ``base_weak``, ``salt_conjugate``).
"""

from __future__ import annotations

from app.modules.chemistry.formula_bindings import FORMULA_LAW_BINDINGS
from app.modules.chemistry.law_record import (
    _ELECTROLYSIS_CUES,
    _MOLAL,
    _MOLAR,
    _PER_SECOND,
    _PH_ASKS,
    _SOLUTE_WORDS,
    _SOLVENT_WORDS,
    ChemistryLaw,
    _law,
)
from app.modules.chemistry.stated_bindings import STATED_LAW_BINDINGS
from app.services.law_binding.spec import VariableSpec, var


def _concentration() -> VariableSpec:
    return var("concentration", "C", _MOLAR)


ACID_BASE: tuple[ChemistryLaw, ...] = (
    _law(
        "strong_acid_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (_concentration(),),
        species="acid_strong",
    ),
    _law(
        "strong_base_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (_concentration(),),
        species="base_strong",
    ),
    _law(
        "weak_acid_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (_concentration(), var("ka", "Ka", dimensionless=True, words=("k_a",), needs_words=True)),
        species="acid_weak",
        # A named conjugate salt is that salt's solution, not the parent acid's.
        excludes=("salt",),
    ),
    _law(
        "conjugate_salt_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (
            _concentration(),
            var("ka", "Ka", dimensionless=True, words=("k_a",), needs_words=True),
        ),
        species="salt_conjugate",
        excludes=("buffer",),
        nonnegative=False,
    ),
    _law(
        "weak_base_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (_concentration(), var("kb", "Kb", dimensionless=True, words=("k_b",), needs_words=True)),
        species="base_weak",
    ),
    _law(
        "ph_from_poh",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (var("poh", "pOH", dimensionless=True, words=("p_oh",), needs_words=True),),
        nonnegative=False,
    ),
    _law(
        "buffer_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (
            var("pka", "pKa", dimensionless=True, words=("p_ka",), needs_words=True),
            var("acid", "[HA]", _MOLAR, words=("acid",), needs_words=True),
            var("base", "[A-]", _MOLAR, words=("base", "salt"), needs_words=True),
        ),
        cues=("buffer",),
        nonnegative=False,
    ),
    _law(
        "base_buffer_ph",
        "acid_base",
        _PH_ASKS,
        "dimensionless",
        (
            var("kb", "Kb", dimensionless=True, words=("k_b",), needs_words=True),
            var(
                "conjugate",
                "[BH+]",
                _MOLAR,
                words=("salt", "conjugate", "ammonium"),
                needs_words=True,
            ),
            var("base", "[B]", _MOLAR, words=("base",), needs_words=True),
        ),
        cues=("buffer",),
        excludes=("p_ka",),
        nonnegative=False,
    ),
    _law(
        "strong_acid_poh",
        "acid_base",
        ("p_oh",),
        "dimensionless",
        (_concentration(),),
        species="acid_strong",
    ),
    _law(
        "strong_base_poh",
        "acid_base",
        ("p_oh",),
        "dimensionless",
        (_concentration(),),
        species="base_strong",
    ),
    _law(
        "weak_acid_ka",
        "acid_base",
        ("k_a",),
        "dimensionless",
        (
            var("concentration", "C", _MOLAR, words=("weak acid",), needs_words=True),
            var("ph", "pH", dimensionless=True, words=("p_h",), needs_words=True),
        ),
        cues=("weak acid",),
        nonnegative=False,
    ),
)


def _van_t_hoff() -> VariableSpec:
    return var(
        "i",
        "i",
        dimensionless=True,
        words=("i =", "van 't hoff", "van't hoff"),
        needs_words=True,
        fallback="van_t_hoff",
    )


# How a colligative question states the solute's amount: as a molality, as moles in a mass of
# solvent, or as grams of a named solute (its molar mass from the table) in a mass of solvent.
# The solvent mass is passed as typed; the solver shows it in kilograms.
_SOLVENT_MASS = var("solvent_mass", "m(solvent)", "gram", words=_SOLVENT_WORDS)
_COLLIGATIVE_AMOUNTS: tuple[tuple[str, tuple[VariableSpec, ...]], ...] = (
    ("", (var("molality", "m", _MOLAL),)),
    ("_moles", (var("moles", "n", "mole"), _SOLVENT_MASS)),
    (
        "_mass",
        (
            var("solute_mass", "m(solute)", "gram", words=_SOLUTE_WORDS, needs_words=True),
            var("molar_mass", "M", "gram / mole", fallback="species_molar_mass"),
            var("solvent_mass", "m(solvent)", "gram", words=_SOLVENT_WORDS, needs_words=True),
        ),
    ),
)


def _colligative(
    op: str,
    constant: str,
    point: str,
    change_asks: tuple[str, ...],
    change_words: tuple[str, ...],
) -> tuple[ChemistryLaw, ...]:
    """ΔT = iKm for each way the amount is stated, asked as the change or as the new point.

    "The boiling point elevation" is ΔTb. "The boiling point" of a solution is the solvent's
    normal boiling point plus ΔTb: water's is a setting, another solvent's must be stated. A
    question that asks how much the point changes is never read as the new point.
    """
    symbol = constant.capitalize()
    laws: list[ChemistryLaw] = []
    for suffix, amount in _COLLIGATIVE_AMOUNTS:
        given = (_van_t_hoff(), var(constant, symbol, "kelvin * kilogram / mole"), *amount)
        keep = ("solvent_mass",) if suffix else ()
        # A solute weighed in grams is one named solute: its molar mass and its formula.
        solute = "solute" if suffix == "_mass" else None
        laws.append(
            _law(
                op,
                "solutions",
                change_asks,
                "kelvin",
                given,
                name=f"{op}{suffix}",
                keep_units=keep,
                species=solute,
            )
        )
        verb = "boils" if point == "boiling" else "freezes"
        normal = var(
            "normal_point",
            f"normal {point} point",
            "kelvin",
            words=(f"normal {point} point", "pure", f"{verb} at"),
            needs_words=True,
            fallback=f"solvent_{point}_point",
        )
        laws.append(
            _law(
                f"solution_{point}_point",
                "solutions",
                (f"{point} point", f"new {point} point"),
                "kelvin",
                (*given, normal),
                name=f"{op}_point{suffix}",
                excludes=change_words,
                keep_units=keep,
                species=solute,
            )
        )
    return tuple(laws)


_COLLIGATIVE: tuple[ChemistryLaw, ...] = (
    *_colligative(
        "freezing_depression",
        "kf",
        "freezing",
        (
            "freezing point depression",
            "depression",
            "freezing point decrease",
            "freezing point drop",
            "freezing point fall",
            "freezing point change",
            "change in freezing point",
            "change in the freezing point",
        ),
        ("depress", "lower", "decreas", "drop", "fall", "change", "how much", "differ"),
    ),
    *_colligative(
        "boiling_elevation",
        "kb",
        "boiling",
        (
            "boiling point elevation",
            "elevation",
            "boiling point increase",
            "boiling point rise",
            "boiling point change",
            "change in boiling point",
            "change in the boiling point",
        ),
        ("elevat", "rais", "increas", "rise", "change", "how much", "differ", "higher"),
    ),
)


SOLUTIONS: tuple[ChemistryLaw, ...] = (
    _law(
        "dilution",
        "solutions",
        ("new concentration", "final concentration", "concentration", "molarity"),
        _MOLAR,
        (
            var("m1", "M1", _MOLAR),
            var("v1", "V1", "liter"),
            var("v2", "V2", "liter", words=("diluted to", "dilute it to", "final volume", "total")),
        ),
        cues=("dilut",),
        interchangeable=("v1", "v2"),
        keep_units=("v1", "v2"),
    ),
    # "What is the molarity of 0.25 mol of KCl in 750 mL of solution?"
    _law(
        "molarity",
        "solutions",
        ("molarity", "molar concentration", "concentration"),
        _MOLAR,
        (var("moles", "n", "mole"), var("volume_l", "V", "liter")),
        excludes=("dilut",),
    ),
    *_COLLIGATIVE,
    _law(
        "osmotic_pressure",
        "solutions",
        ("osmotic pressure",),
        "atmosphere",
        (
            var(
                "i",
                "i",
                dimensionless=True,
                words=("i =", "van 't hoff", "van't hoff"),
                needs_words=True,
                fallback="van_t_hoff",
            ),
            var("molarity", "M", _MOLAR),
            var("temperature", "T", "kelvin"),
        ),
    ),
)

AMOUNTS: tuple[ChemistryLaw, ...] = (
    _law(
        "mass_to_moles",
        "amounts",
        ("how many moles", "moles", "amount"),
        "mole",
        (var("mass", "m", "gram"),),
        species="compound",
        labels=(("mass", "g"),),
    ),
    _law(
        "moles_to_mass",
        "amounts",
        ("how many grams", "grams", "mass"),
        "gram",
        (var("moles", "n", "mole"),),
        species="compound",
        labels=(("moles", "mol"),),
    ),
    _law(
        "molecular_formula",
        "amounts",
        ("molecular formula",),
        "dimensionless",
        (var("molar_mass", "M", "gram / mole"),),
        species="compound",
    ),
    _law(
        "percent_yield",
        "amounts",
        ("percent yield", "percentage yield", "% yield"),
        "percent",
        (
            var("actual", "actual", "gram", words=("actual", "obtained", "isolated", "collected")),
            var("theoretical", "theoretical", "gram", words=("theoretical", "expected")),
        ),
    ),
)


def _integrated(op: str, order: str, rate_unit: str) -> ChemistryLaw:
    """[A] after a time, for one reaction order: k and t in seconds."""
    return _law(
        op,
        "kinetics",
        ("a_conc", "concentration", "how much"),
        _MOLAR,
        (
            var("initial", "[A]0", _MOLAR, words=("a_initial", "initial", "starting")),
            var("rate_constant", "k", rate_unit),
            var("time", "t", "second"),
        ),
        cues=(f"{order}-order", f"{order} order"),
        labels=(("time", "s"),),
    )


KINETICS: tuple[ChemistryLaw, ...] = (
    _integrated("first_order_concentration", "first", _PER_SECOND),
    _integrated("zero_order", "zero", "mole / liter / second"),
    _integrated("second_order", "second", "liter / mole / second"),
    _law(
        "arrhenius_two_point",
        "kinetics",
        ("activation energy", "e_a"),
        "kilojoule / mole",
        (
            var("k1", "k1", _PER_SECOND),
            var("t1", "T1", "kelvin"),
            var("k2", "k2", _PER_SECOND),
            var("t2", "T2", "kelvin"),
        ),
        interchangeable=("k1", "k2", "t1", "t2"),
    ),
)

ELECTROCHEMISTRY: tuple[ChemistryLaw, ...] = (
    _law(
        "nernst",
        "electrochemistry",
        ("e_cell", "cell potential", "potential"),
        "volt",
        (
            var("standard_potential", "E°", "volt", words=("e_standard", "standard")),
            var("electrons", "n", dimensionless=True, words=("n =", "electrons"), needs_words=True),
            var(
                "quotient",
                "Q",
                dimensionless=True,
                words=("q =", "reaction quotient", "quotient"),
                needs_words=True,
            ),
            var("temperature", "T", "kelvin", fallback="standard_temperature"),
        ),
        nonnegative=False,
    ),
    _law(
        "electrolysis_mass",
        "electrochemistry",
        ("how many grams", "grams", "mass"),
        "gram",
        (
            var("molar_mass", "M", "gram / mole", fallback="deposited_molar_mass"),
            var("current", "I", "ampere"),
            var("time", "t", "second"),
            var(
                "electrons",
                "n",
                dimensionless=True,
                words=("n =", "electrons"),
                needs_words=True,
                fallback="ion_charge",
            ),
        ),
        cues=_ELECTROLYSIS_CUES,
    ),
)

THERMOCHEMISTRY: tuple[ChemistryLaw, ...] = (
    _law(
        "gibbs",
        "thermochemistry",
        ("delta_g", "gibbs", "free energy", "free-energy"),
        "kilojoule / mole",
        (
            var("delta_h", "ΔH", "kilojoule / mole"),
            var("delta_s", "ΔS", "kilojoule / mole / kelvin"),
            var("temperature", "T", "kelvin"),
        ),
        nonnegative=False,
    ),
)


def _beer_lambert(unknown: str, asks: tuple[str, ...], result: str) -> ChemistryLaw:
    variables = (
        var("absorbance", "A", dimensionless=True, words=("absorbance",), needs_words=True),
        var("epsilon", "ε", "liter / mole / centimeter"),
        var("path", "b", "centimeter"),
        var("concentration", "c", _MOLAR),
    )
    return _law(
        "beer_lambert",
        "spectroscopy",
        asks,
        result,
        tuple(variable for variable in variables if variable.name != unknown),
        name=f"beer_lambert_{unknown}",
    )


ANALYSIS: tuple[ChemistryLaw, ...] = (
    _beer_lambert("concentration", ("concentration", "molarity"), _MOLAR),
    _beer_lambert("absorbance", ("absorbance",), "dimensionless"),
    _beer_lambert("path", ("path length",), "centimeter"),
    _beer_lambert(
        "epsilon", ("molar absorptivity", "absorptivity", "ε"), "liter / mole / centimeter"
    ),
    _law(
        "percent_error",
        "analytical",
        ("percent error", "percentage error", "% error"),
        "percent",
        (
            var(
                "experimental",
                "experimental",
                dimensionless=True,
                words=("measured", "experimental", "observed", "obtained"),
                needs_words=True,
            ),
            var(
                "accepted",
                "accepted",
                dimensionless=True,
                words=("accepted", "true", "actual", "known", "literature"),
                needs_words=True,
            ),
        ),
    ),
    _law(
        "chromatography_rf",
        "analytical",
        ("r_f", "retention factor"),
        "dimensionless",
        (
            var("spot", "spot", "centimeter", words=("spot", "compound", "sample", "dye")),
            var("front", "front", "centimeter", words=("front", "solvent")),
        ),
    ),
)


LAWS: tuple[ChemistryLaw, ...] = (
    *ACID_BASE,
    *SOLUTIONS,
    *AMOUNTS,
    *KINETICS,
    *ELECTROCHEMISTRY,
    *THERMOCHEMISTRY,
    *ANALYSIS,
    *FORMULA_LAW_BINDINGS,
    *STATED_LAW_BINDINGS,
)
