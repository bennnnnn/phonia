"""Chemistry's constants are CODATA values from the shared unit registry, pinned.

A Pint upgrade that moved one would move answers, so each magnitude is held here. A
substitution row prints the constant its arithmetic uses: it names it (``{R_J}``) and the
solver writes the value, so the figure shown is the figure computed.
"""

from __future__ import annotations

import ast
import re
import string

import pytest

from app.modules.chemistry.formula_laws import FORMULA_LAWS
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers import constants
from app.modules.chemistry.solvers.formula import CHEMISTRY_NOTATION, solve_formula_law
from app.modules.chemistry.solvers.types import format_constant, format_number
from app.services.law_binding.expression import parse
from app.services.units import constant


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GAS_R", 0.08205736608095969),
        ("GAS_R_J", 8.314462618153241),
        ("FARADAY", 96485.33212331001),
        ("AVOGADRO", 6.02214076e23),
        ("PROTON_U", 1.0072764665741099),
        ("NEUTRON_U", 1.0086649160560601),
        ("MEV_PER_U", 931.4941037185688),
        ("STANDARD_TEMPERATURE_K", 298.15),
    ],
)
def test_a_chemistry_constant_is_the_registrys_codata_value(name: str, value: float) -> None:
    assert getattr(constants, name) == pytest.approx(value, rel=1e-15)


def test_a_registry_constant_reads_in_the_unit_asked_or_in_si() -> None:
    assert constant("molar_gas_constant", "L * atm / (mol * K)") == pytest.approx(0.0820573661)
    assert constant("molar_gas_constant") == pytest.approx(8.314462618)


# Every way a row could type a constant by hand: each one to three through seven figures.
_TYPED_SPELLINGS = sorted(
    {
        format_number(value, significant=figures)
        for value, _symbol in CHEMISTRY_NOTATION.constants.values()
        for figures in range(3, 8)
    }
)


def _named_in(row: str) -> set[str]:
    """The placeholders a substitution row names: ``{R_J}``, ``{k.value}`` → R_J, k."""
    return {field.split(".")[0] for _, field, _, _ in string.Formatter().parse(row) if field}


def _read_by(expression: str) -> set[str]:
    return {node.id for node in ast.walk(parse(expression)) if isinstance(node, ast.Name)}


def test_a_substitution_names_the_constant_its_arithmetic_uses() -> None:
    typed: list[str] = []
    elsewhere: list[str] = []
    for op, law in sorted(FORMULA_LAWS.items()):
        for row in law.substitution:
            text = re.sub(r"\{[^}]*\}", "", row)
            typed.extend(f"{op}: {spelling!r}" for spelling in _TYPED_SPELLINGS if spelling in text)
            named = _named_in(row) & CHEMISTRY_NOTATION.constants.keys()
            elsewhere.extend(f"{op}: {name}" for name in named - _read_by(law.expression))
    assert not typed, f"rows type a constant instead of naming it: {typed}"
    assert not elsewhere, f"rows name a constant their arithmetic does not use: {elsewhere}"


@pytest.mark.parametrize(
    ("op", "params", "name"),
    [
        ("particles_to_mass", {"particles": 3.01e23, "molar_mass": 18.015}, "N_A"),
        ("element_atoms", {"moles": 0.5, "count": 2}, "N_A"),
        (
            "electrolysis_time",
            {"mass": 1.0, "electrons": 2, "current": 2.0, "molar_mass": 63.546},
            "F",
        ),
        ("gas_density", {"pressure": 1.0, "molar_mass": 44.01, "temperature": 298.0}, "R_atm"),
        (
            "molar_mass_from_density",
            {"density": 1.8, "temperature": 298.0, "pressure": 1.0},
            "R_atm",
        ),
        ("vant_hoff_constant", {"k1": 0.1, "t1": 300, "t2": 350, "enthalpy": 28}, "R_J"),
        ("vant_hoff_enthalpy", {"k1": 0.1, "t1": 300, "k2": 0.5, "t2": 350}, "R_J"),
        ("gibbs_from_equilibrium", {"k": 10, "temperature": 298.15}, "R_J"),
        ("equilibrium_from_gibbs", {"gibbs": -5.7, "temperature": 298.15}, "R_J"),
        (
            "gibbs_reaction",
            {"gibbs_standard": -5.7, "temperature": 298.15, "quotient": 2.0},
            "R_J",
        ),
    ],
)
def test_a_substitution_prints_the_constant_to_five_figures(
    op: str, params: dict[str, float], name: str
) -> None:
    law = {"kind": FORMULA_LAWS[op].kind, "chemistry_op": op, "params": params}
    intent = ChemistryIntent.model_validate(law)
    value, _symbol = CHEMISTRY_NOTATION.constants[name]
    assert f"({format_constant(value)} " in " ".join(solve_formula_law(intent).substitution)
