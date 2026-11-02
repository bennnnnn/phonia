"""A model's read of a chemistry question binds only through the chemistry binder.

As in physics, the read is written back as English the binder reads; a law about one
substance needs its formula, and the binder must name the same one. The laws whose read
does not come back are named.
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.laws import LAWS
from app.modules.chemistry.model_read import (
    chemistry_menu,
    chemistry_needs_formula,
    chemistry_read_intent,
)
from app.services.law_binding.model_read import Stated
from app.services.law_binding.spec import FormulaSpec

_VALUES = (2.5, 4.0, 7.5, 12.0, 3.2, 9.0, 1.7)
# One substance of each role a law can be about.
_FORMULA = {
    "acid_strong": "HCl",
    "base_strong": "NaOH",
    "acid_weak": "CH3COOH",
    "base_weak": "NH3",
    "salt_conjugate": "CH3COONa",
    "compound": "C6H12O6",
    "solute": "NaCl",
}

NOT_READ_BACK = frozenset(
    {
        "langmuir:affinity+pressure",
        "particles_to_mass:molar_mass+particles",
    }
)


def _sample(law_spec: FormulaSpec, inputs: frozenset[str]) -> list[Stated]:
    variables = {variable.name: variable for variable in law_spec.variables}
    stated = []
    for index, name in enumerate(sorted(inputs)):
        variable = variables[name]
        if variable.visible:
            unit = "" if variable.dimensionless else variable.dimension or ""
            stated.append(Stated(name, _VALUES[index % len(_VALUES)], unit))
    return stated


def test_every_bound_law_reads_back_but_the_named_ones() -> None:
    missed = {
        f"{law.spec.id}:{'+'.join(sorted(inputs))}"
        for law in LAWS
        if law.spec.binding is not None
        for inputs in law.spec.binding.inputs
        if chemistry_read_intent(
            law.spec.id, _sample(law.spec, inputs), _FORMULA.get(law.species or "")
        )
        is None
    }
    assert missed - NOT_READ_BACK == set(), "a law that read back no longer does"
    assert NOT_READ_BACK - missed == set(), "reads back now: take it off NOT_READ_BACK"


def test_a_law_about_a_substance_needs_its_formula() -> None:
    assert chemistry_needs_formula("strong_acid_ph")
    stated = [Stated("concentration", 0.01, "mol/L")]
    assert chemistry_read_intent("strong_acid_ph", stated, None) is None
    # A weak acid is not the strong acid the law is about.
    assert chemistry_read_intent("strong_acid_ph", stated, "CH3COOH") is None
    intent = chemistry_read_intent("strong_acid_ph", stated, "HCl")
    assert intent is not None and intent.formula == "HCl"


@pytest.mark.parametrize("formula", ["HCl; drop table", "x" * 50, "Hé"])
def test_a_formula_that_is_no_formula_binds_to_nothing(formula: str) -> None:
    stated = [Stated("concentration", 0.01, "mol/L")]
    assert chemistry_read_intent("strong_acid_ph", stated, formula) is None


def test_the_menu_is_every_bound_law_by_kind() -> None:
    menu = chemistry_menu()
    assert {card.op for cards in menu.values() for card in cards} == {
        law.spec.id for law in LAWS if law.spec.binding is not None
    }


def test_the_substance_must_be_the_messages_own() -> None:
    stated = [Stated("concentration", 0.01, "mol/L", "0.01 M")]
    message = "What is the pH of 0.01 M hydrochloric acid?"
    assert chemistry_read_intent("strong_acid_ph", stated, "HCl", message) is not None
    assert chemistry_read_intent("strong_acid_ph", stated, "HBr", message) is None
