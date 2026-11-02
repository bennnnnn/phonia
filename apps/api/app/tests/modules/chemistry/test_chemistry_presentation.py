# ruff: noqa: RUF003 -- working rows use the multiplication sign.
"""A verified chemistry answer reads like a textbook's worked solution.

A law shows its equation under **Formula**; a procedure (balancing, a table lookup) shows its
rule under **Method** and checks it under **Working**. Substitutions carry units, a given an
extractor converted is shown as typed and then as used, and each unit change is a row.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.catalog import CATALOG, METHODS
from app.modules.chemistry.direct import format_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.solvers import solve_chemistry
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.workout import as_formula_heading


def _solve(question: str) -> ChemistryResult:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    return solve_chemistry(intent)


def _reply(question: str) -> str:
    intent = extract_chemistry_intent(question)
    assert intent is not None, question
    verified = build_verified_chemistry(intent)
    assert verified is not None, question
    return format_direct_chemistry_reply(verified)


def test_every_method_is_a_catalog_operation_with_a_rule_not_an_equation() -> None:
    assert set(METHODS) <= set(CATALOG)
    for operation in METHODS:
        assert CATALOG[operation].method
        assert " = " not in CATALOG[operation].base_formula, operation


@pytest.mark.parametrize(
    ("question", "method"),
    [
        ("Balance N2 + H2 -> NH3", True),
        ("IR peak at 1715 cm-1", True),
        ("What is the electron configuration of Fe?", True),
        ("How many moles are in 36 g of water?", False),
    ],
)
def test_a_procedure_shows_its_rule_and_then_its_steps(question: str, method: bool) -> None:
    """One layout: a procedure's rule under Formula, a law under its own name's heading
    ("Molar mass formula"); a procedure's tally under Steps."""
    reply = _reply(question)
    assert ("**Formula**" in reply) is method
    assert "**Formula**" in as_formula_heading(reply)
    assert ("**Steps**" in reply) is method
    assert ("**Substitution**" in reply) is not method


def test_the_model_prompt_names_the_same_sections() -> None:
    intent = extract_chemistry_intent("Balance N2 + H2 -> NH3")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    assert "Given, Required, Solution, Formula, Steps, Answer" in verified.prompt_text
    assert "\nSteps:\n" in verified.prompt_text


@pytest.mark.parametrize(
    ("question", "substitution"),
    [
        ("How many moles are in 36 g of water?", ("n = 36 g / 18.015 g/mol",)),
        ("What is the molarity of 0.5 mol NaCl in 2.0 L of solution?", ("c = 0.5 mol / 2.0 L",)),
        (
            "50 mL of 2 M HCl is diluted to 200 mL. What is the new concentration?",
            ("M2 = (2 mol/L)(50 mL) / 200 mL",),
        ),
        (
            "Find electrochemical Gibbs ΔG for a cell with n=2 and E°=1.1 V",
            (
                "ΔG° = −(2)(96485 C/mol)(1.1 V) = -2.1 × 10^5 J/mol",
                "ΔG° = -2.1 × 10^5 J/mol = -2.1 × 10^2 kJ/mol",
            ),
        ),
        (
            "How many grams of Cu are deposited by a current of 2 A for 1 hour from Cu2+?",
            ("m = (63.546 g/mol)(2 A)(3600 s) / [(2)(96485 C/mol)]",),
        ),
    ],
)
def test_a_substitution_carries_its_units_and_its_conversions(
    question: str, substitution: tuple[str, ...]
) -> None:
    assert _solve(question).substitution == substitution


@pytest.mark.parametrize(
    ("question", "row"),
    [
        # Typed in J, used in kJ: the typed value first, with its figures kept.
        (
            "Calculate ΔG at 298 K if ΔH = -100 kJ/mol and ΔS = -200 J/mol·K.",
            "ΔS = -200 J/(mol·K) = -0.200 kJ/(mol·K)",
        ),
        # The Celsius offset is exact, so the kelvin keeps it.
        ("Use Nernst equation with E°=1.1 V, n=2, Q=10, T=37 °C", "T = 37 °C = 310.15 K"),
        # An exact unit change keeps its own digits: 1 h is 3600 s, not 4 × 10^3 s.
        (
            "How many grams of Cu are deposited by a current of 2 A for 1 hour from Cu2+?",
            "t = 1 h = 3600 s",
        ),
        (
            "How many grams of NaCl are needed to make 500 mL of a 0.200 M NaCl solution?",
            "V = 500 mL = 0.500 L",
        ),
        (
            "25.0 mL of NaOH is neutralized by 20.0 mL of 0.100 M HCl. "
            "Find the concentration of the NaOH.",
            "V₂ = 25.0 mL = 0.0250 L",
        ),
    ],
)
def test_a_converted_given_is_shown_as_typed_then_as_used(question: str, row: str) -> None:
    assert row in _solve(question).given


@pytest.mark.parametrize(
    ("question", "row"),
    [
        # The unit is the one typed, not the one the template usually converts from (J).
        (
            "Calculate ΔG at 298 K if ΔH = -10 kcal/mol and ΔS = -200 J/mol·K.",
            "ΔH = -10 kcal/mol = -41.84 kJ/mol",
        ),
        (
            "How many grams of Cu are deposited by a current of 2 A for 1 year from Cu2+?",
            "t = 1 yr = 3.15576 × 10^7 s",
        ),
        # A conversion that does not terminate keeps the typed figures: 700 mmHg has three.
        ("Find the density of CO2 gas at 700 mmHg and 298 K.", "P = 700 mmHg = 0.921 atm"),
    ],
)
def test_a_converted_given_names_the_unit_it_was_typed_in(question: str, row: str) -> None:
    assert row in _solve(question).given


def test_a_repeating_conversion_is_substituted_to_the_typed_figures() -> None:
    result = _solve("Find the density of CO2 gas at 700 mmHg and 298 K.")
    assert result.substitution[0].startswith("d = (0.921 atm)(44.009 g/mol)")


def test_a_value_two_typed_numbers_explain_is_not_echoed_as_either() -> None:
    # 1800 s is 30 min, and also 0.50 × 3600: neither literal is claimed as the time.
    result = _solve("How many grams of Cu are deposited by 0.50 A for 30 min from Cu2+?")
    assert "t = 1800 s" in result.given


def test_a_respelled_unit_is_not_a_conversion() -> None:
    # 0.200 M is 0.200 mol/L: nothing to convert, so no "0.200 M = 0.200 mol/L" row.
    result = _solve("How many grams of NaCl are needed to make 500 mL of a 0.200 M NaCl solution?")
    assert "c = 0.200 mol/L" in result.given
