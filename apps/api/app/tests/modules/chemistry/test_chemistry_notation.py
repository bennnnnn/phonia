"""One notation policy: the solver writes ASCII, the reader sees typeset chemistry."""

from __future__ import annotations

import re

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.catalog import CATALOG, law_name
from app.modules.chemistry.direct import format_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.fence import validate_chemistry_fences
from app.modules.chemistry.notation import typeset, typeset_json
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.solver import CHEMISTRY_SOLVERS
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.answer_fence import mark_server_answer_fences
from app.tests.modules.chemistry.new_law_cases import NEW_LAW_CASES
from app.tests.modules.chemistry.test_chemistry_solver_expanded import (
    PIPELINE_CASES,
    PUBCHEM_OPS,
    REMAINING_CASES,
)

_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")

ALL_CASES = (*PIPELINE_CASES, *REMAINING_CASES, *NEW_LAW_CASES)


def flatten(text: str) -> str:
    """Every presentation-only character folded back to ASCII: what ``typeset`` may change."""
    text = re.sub(r"\^[({]([^)}]*)[)}]", r"\1", text)
    return (
        text.translate(_SUB)
        .translate(_SUP)
        .replace("^", "")
        .replace("−", "-")
        .replace("→", "->")
        .replace("⇌", "<=>")
        .replace("₁₀", "10")
    )


def _solve(question: str) -> ChemistryResult:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return solve_chemistry(intent)


@pytest.mark.parametrize(
    ("ascii_text", "typeset_text"),
    [
        ("H2 + O2 -> H2O", "H₂ + O₂ → H₂O"),
        ("2 H2SO4", "2 H₂SO₄"),
        ("Fe2+ + 2 e- -> Fe", "Fe²⁺ + 2 e⁻ → Fe"),
        ("SO4^2- and [H+]", "SO₄²⁻ and [H⁺]"),
        ("NH4+ and (NH4)2SO4", "NH₄⁺ and (NH₄)₂SO₄"),
        ("[Fe(CN)6]3-", "[Fe(CN)₆]³⁻"),
        ("OH- and Cl-", "OH⁻ and Cl⁻"),
        ("N2O4 <=> 2NO2", "N₂O₄ ⇌ 2NO₂"),
        ("1.8 × 10^-5", "1.8 × 10⁻⁵"),
        ("10^(-4)", "10⁻⁴"),
        ("[NO2]^2 / [N2O4]", "[NO₂]² / [N₂O₄]"),
        ("Ka1 = 4.3 × 10^-7", "Ka₁ = 4.3 × 10⁻⁷"),
        ("M1V1 = M2V2", "M₁V₁ = M₂V₂"),
        ("pH = -log10([H+])", "pH = -log₁₀([H⁺])"),
        ("dG = -40 kJ", "dG = −40 kJ"),
        ("C6H12O6 · 180.16 g/mol", "C₆H₁₂O₆ · 180.16 g/mol"),
    ],
)
def test_typeset_encodes_ascii_chemistry(ascii_text: str, typeset_text: str) -> None:
    assert typeset(ascii_text) == typeset_text


@pytest.mark.parametrize(
    "text",
    [
        "n+1 = 3 (triplet)",  # a sum, not a charge
        "half-life",  # a hyphen, not a minus
        "e^(-kt)",  # an expression, not an exponent
        "x^(1/2)",
        "sp3 hybridization and log10",  # lowercase letters are not element symbols
        "0.5 mol/L at 25 °C",
        "Ea = 55.33 kJ/mol",
    ],
)
def test_typeset_leaves_prose_and_expressions_alone(text: str) -> None:
    assert typeset(text) == text or text == "sp3 hybridization and log10"
    if text.startswith("sp3"):
        assert typeset(text) == "sp3 hybridization and log₁₀"


@pytest.mark.parametrize(("question", "operation", "_answer"), ALL_CASES)
def test_typeset_is_idempotent_and_only_re_encodes_characters(
    question: str, operation: str, _answer: str
) -> None:
    result = _solve(question)
    for text in (
        *result.given,
        result.find,
        result.formula,
        *result.substitution,
        result.answer,
    ):
        once = typeset(text)
        assert typeset(once) == once, text
        assert flatten(once) == flatten(text), text


def test_typeset_json_skips_the_kind_tag() -> None:
    scene = {"kind": "cell", "anode": "Zn", "species": ["Cu2+", {"kind": "x", "note": "H2O"}]}
    assert typeset_json(scene) == {
        "kind": "cell",
        "anode": "Zn",
        "species": ["Cu²⁺", {"kind": "x", "note": "H₂O"}],
    }


@pytest.mark.parametrize(("question", "operation", "_answer"), ALL_CASES)
def test_every_substitution_is_a_working_not_a_copy_of_the_answer(
    question: str, operation: str, _answer: str
) -> None:
    result = _solve(question)
    assert result.substitution, operation
    assert result.substitution != (result.answer,), operation


_NUMBER = re.compile(r"\d+(?:\.\d+)?(?: × 10\^-?\d+)?")
# Given lines that describe the structure, not a value the calculation multiplies in.
_STRUCTURAL_GIVEN = ("valence electrons", "at 25 °C")


@pytest.mark.parametrize(("question", "operation", "_answer"), ALL_CASES)
def test_every_numeric_given_is_used_in_the_working(
    question: str, operation: str, _answer: str
) -> None:
    result = _solve(question)
    working = " ".join((result.formula, *result.substitution))
    for line in result.given:
        if any(marker in line for marker in _STRUCTURAL_GIVEN):
            continue
        if "=" not in line:
            continue
        # A converted given ("V = 500 mL = 0.500 L") is used as its last value.
        value = line.rsplit("=", 1)[1]
        for number in _NUMBER.findall(value):
            assert number in working, f"{operation}: {line!r} is not used in {working!r}"


@pytest.mark.parametrize(("question", "operation", "_answer"), ALL_CASES)
def test_a_direct_reply_is_typeset_free_of_math_delimiters_and_stable_under_finalize(
    question: str, operation: str, _answer: str
) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    reply = format_direct_chemistry_reply(verified)
    assert "$" not in reply
    # Finalizing adds only the server's verified marker to its own card.
    assert validate_chemistry_fences(reply, verified=verified) == mark_server_answer_fences(reply)


def test_every_operation_has_a_case_in_the_invariant_matrix() -> None:
    covered = {operation for _question, operation, _answer in ALL_CASES}
    assert covered == set(CHEMISTRY_SOLVERS) - PUBCHEM_OPS


def test_a_direct_reply_reads_as_typeset_chemistry() -> None:
    intent = extract_chemistry_intent("Balance N2 + 3H2 <=> 2NH3")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    reply = format_direct_chemistry_reply(verified)
    assert "N₂ + 3 H₂ ⇌ 2 NH₃" in reply or "N₂ + 3H₂ ⇌ 2NH₃" in reply
    assert "->" not in reply
    assert "<=>" not in reply


def test_a_smiles_result_is_never_typeset() -> None:
    intent = extract_chemistry_intent("Identify functional groups in SMILES C1CCCCC1O")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    reply = format_direct_chemistry_reply(verified)
    assert "OC1CCCCC1" in reply
    assert "C₁" not in reply


# Ops whose printed formula is built from this problem (a mole ratio, Kc in the user's
# species, an ICE quotient, or [OH-] = C versus 2C). A weak titration also changes the law name.
_CASE_FORMULA = frozenset(
    {
        "equilibrium_constant",
        "reaction_quotient",
        "kp",
        "ice_equilibrium",
        "stoichiometry",
        "mass_stoichiometry",
        "solution_stoichiometry",
        "gas_stoichiometry",
        "strong_base_ph",
        "atom_economy",
    }
)
_CASE_LAW = frozenset({"titration_weak"})


@pytest.mark.parametrize(("question", "operation", "_answer"), ALL_CASES)
def test_the_catalog_names_each_law_as_the_answer_prints_it(
    question: str, operation: str, _answer: str
) -> None:
    result = _solve(question)
    spec = CATALOG[operation]
    assert law_name(operation) == spec.law_name
    if operation not in _CASE_LAW:
        assert result.formula_name == spec.law_name
    if operation not in _CASE_FORMULA:
        assert result.formula == spec.base_formula


def test_a_strong_base_prints_how_many_hydroxides_it_releases() -> None:
    sodium = _solve("Find the strong base pH of 0.010 M NaOH")
    assert sodium.formula == "[OH-] = C"
    assert sodium.answer == "pH = 12.00"
    calcium = _solve("Find the strong base pH of 0.010 M Ca(OH)2")
    assert calcium.formula == "[OH-] = 2C"
    assert calcium.answer.startswith("pH = ")


def test_an_ice_formula_is_products_over_reactants() -> None:
    result = _solve("Solve the ICE equilibrium for N2O4 -> NO2 when K=4 and [N2O4]=1")
    assert result.formula == "K = (2x)^2 / (1 − x)"


def test_stoichiometry_prints_this_reaction_ratio() -> None:
    result = _solve("How many moles of NH3 from 2 mol N2 in N2 + 3 H2 -> NH3?")
    assert result.formula == "n(NH3) = n(N2) × (2 / 1)"
    assert result.answer == "n(NH3) = 4.0 mol NH3"


def test_the_model_prompt_keeps_each_answer_line_and_working_row_whole() -> None:
    intent = extract_chemistry_intent("Find the galvanic cell for Zn and Cu")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    prompt = verified.prompt_text
    assert "- E°cell = 1.10 V\n- anode: Zn\n- cathode: Cu" in prompt
    assert "- Zn + Cu2+ -> Zn2+ + Cu" in prompt
    assert "->" in prompt and "→" not in prompt.split("Formula")[1]
    intent = extract_chemistry_intent("How many moles are in 36 g of H2O?")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    assert "- n = 36 g / 18.015 g/mol" in verified.prompt_text
