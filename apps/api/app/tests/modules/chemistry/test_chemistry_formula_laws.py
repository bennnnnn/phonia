"""Graham, two-point Clausius-Clapeyron, and Henry stay unverified when a value is missing."""

from __future__ import annotations

import pytest

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.solvers import solve_chemistry


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    if intent is None:
        return None
    return solve_chemistry(intent).answer


def test_graham_solves_a_rate_or_a_molar_mass() -> None:
    assert _answer("Use Graham's law when r1=2, M1=4, and M2=16. Find r2.") == "rate2 = 1.0"
    assert _answer("Use Graham's law when r1=2, r2=1, and M2=16. Find M1.") == "M1 = 4.0"


def test_clausius_solves_the_enthalpy_or_the_missing_pressure() -> None:
    enthalpy = "Clausius-Clapeyron: P1=1, T1=300, P2=2, T2=350. Find the enthalpy."
    pressure = "Clausius-Clapeyron: P1=1, T1=300, T2=350, dH=12100. Find P2."
    other = "Clausius-Clapeyron: P2=2, T1=300, T2=350, dH=12100. Find P1."
    assert _answer(enthalpy) == "ΔHvap = 12 kJ/mol"
    assert _answer(pressure) == "P2 = 2.0"
    assert _answer(other) == "P1 = 1.0"


def test_henry_solves_concentration_pressure_or_the_constant() -> None:
    assert _answer("Use Henry's law when kH=0.034 and P=2. Find the concentration.") == "C = 0.068"
    assert _answer("Use Henry's law when C=0.068 and kH=0.034. Find the pressure.") == "P = 2.0"
    assert _answer("Use Henry's law when C=0.068 and P=2. Find kH.") == "kH = 0.034"


@pytest.mark.parametrize(
    "question",
    [
        "Use Graham's law when r1=2 and M1=4. Find r2.",
        "Clausius-Clapeyron: P1=1, T1=300, T2=350. Find the enthalpy.",
        "Use Henry's law when kH=0.034. Find the concentration.",
    ],
)
def test_a_formula_law_declines_when_a_required_value_is_missing(question: str) -> None:
    assert _answer(question) is None
