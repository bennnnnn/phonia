"""The shared law engine reads a subject it was not written for.

A toy gas-law subject (mol, L, atm, K) drives the engine directly, so nothing here depends
on physics' tables: its own units, its own setting for an unstated input, its own constant.
"""

from __future__ import annotations

import pytest

from app.services.law_binding.expression import ExpressionError, Notation, evaluate, to_latex
from app.services.law_binding.fit import Question, Subject, fit, read_givens
from app.services.law_binding.givens import scan_givens
from app.services.law_binding.spec import Binding, FormulaSpec, VariableSpec, var
from app.services.law_binding.units import UnitTable, dimension_of
from app.tests.services.law_binding_support import names

_UNITS = UnitTable(
    {"L": "liter", "K": "kelvin", "atm": "atmosphere", "mL": "milliliter"},
    {"mol": "mole", "moles": "mole"},
)
_ROOM_TEMPERATURE = 298.15


def _fallback(variable: VariableSpec, _text: str, lower: str) -> float | None:
    if variable.fallback == "room_temperature" and "room temperature" in lower:
        return _ROOM_TEMPERATURE
    return None


_GASES = Subject(units=_UNITS, fallback=_fallback, unit_of=lambda variable: "K")
_PRESSURE = FormulaSpec(
    id="ideal_gas_pressure",
    kind="gases",
    law_name="Ideal gas law",
    result_symbol="P",
    variables=(
        var("n", "n", "mole"),
        var("V", "V", "liter"),
        var("T", "T", "kelvin", fallback="room_temperature"),
    ),
    binding=Binding(
        asks=("pressure",),
        result=("atmosphere",),
        inputs=(frozenset({"n", "V", "T"}),),
        nonnegative=True,
    ),
    expression="n*R*T/V",
)


def _question(text: str) -> Question:
    lower = text.lower()
    return Question(
        text=text,
        lower=lower,
        givens=read_givens(text, _UNITS),
        asked=frozenset({dimension_of("atmosphere") or ""}),
        asked_in=None,
        asked_from=lower.rfind("pressure"),
    )


def test_a_subject_table_reads_its_own_units() -> None:
    givens = scan_givens("2 mol in 500 mL at 300 K and 1 atm", _UNITS)
    assert [(given.value, given.unit) for given in givens] == [
        (2.0, "mol"),
        (500.0, "mL"),
        (300.0, "K"),
        (1.0, "atm"),
    ]
    # The longer spelling wins: "mL" is a millilitre, not a metre-less "m" and an "L".
    assert givens[1].si == pytest.approx(5e-4)


def test_a_special_reader_and_an_exact_spelling_extend_the_table() -> None:
    def percent_sign(text: str, end: int) -> tuple[str, str] | None:
        return ("pc", "percent") if text.startswith("pc", end) else None

    table = UnitTable({"L": "liter"}, {}, special=percent_sign, exact={"pc": "percent"})
    assert table.at("40pc", 2) == ("pc", "percent")
    assert table.expression("pc") == "percent"
    assert table.at("40 L", 2) == ("L", "liter")


@pytest.mark.parametrize(
    ("listed", "typed"),
    [
        ("m/s^2", ("m/s^2", "m/s²", "m/s2")),
        ("cm³", ("cm^3", "cm³", "cm3")),
        ("m s^-2", ("m s^-2", "m s⁻²", "m s-2", "m·s⁻²", "m*s^-2", "m·s-2")),
    ],
)
def test_a_listed_power_reads_however_it_is_typed(listed: str, typed: tuple[str, ...]) -> None:
    table = UnitTable({listed: "unit"}, {})
    for spelling in typed:
        assert table.at(f"2 {spelling}", 1) == (spelling, "unit")


def test_a_bare_negative_power_alone_is_not_a_unit() -> None:
    # "between 2 m-3 m" is a range, so only "m^-3" and "m⁻³" read.
    table = UnitTable({"m": "meter", "m^-3": "1 / meter ** 3"}, {})
    assert table.at("2 m⁻³", 1) == ("m⁻³", "1 / meter ** 3")
    assert table.at("2 m-3 m", 1) == ("m", "meter")


def test_a_listed_spelling_keeps_its_own_meaning() -> None:
    table = UnitTable({"x^2": "first", "x2": "second"}, {})
    assert table.expression("x2") == "second"


@pytest.mark.parametrize(
    "table",
    [UnitTable({"L": "liter"}, {}), UnitTable({}, {"liter": "liter"}), UnitTable({}, {})],
)
def test_a_table_with_no_symbols_or_no_words_still_reads_a_bare_number(table: UnitTable) -> None:
    assert table.at("2", 1) is None
    assert [(given.value, given.unit) for given in scan_givens("2 and 3", table)] == [
        (2.0, ""),
        (3.0, ""),
    ]


def test_a_law_is_filled_from_a_question_in_its_own_units() -> None:
    filled = fit(
        _PRESSURE, 8, _question("What is the pressure of 2 mol of gas in 10 L at 300 K?"), _GASES
    )
    assert filled is not None
    assert filled.params == {"n": 2.0, "V": 10.0, "T": 300.0}
    assert filled.units == {"n": "mol", "V": "L", "T": "K"}


def test_an_unstated_input_takes_the_subjects_setting() -> None:
    question = _question("What is the pressure of 2 mol of gas in 10 L at room temperature?")
    filled = fit(_PRESSURE, 8, question, _GASES)
    assert filled is not None
    assert filled.params["T"] == _ROOM_TEMPERATURE
    assert filled.units["T"] == "K"


@pytest.mark.parametrize(
    "text",
    [
        # A second volume has no input to fill.
        "What is the pressure of 2 mol of gas in 10 L and 5 L at 300 K?",
        # No temperature and no setting for it.
        "What is the pressure of 2 mol of gas in 10 L?",
    ],
)
def test_a_law_that_does_not_fit_one_way_declines(text: str) -> None:
    assert fit(_PRESSURE, 8, _question(text), _GASES) is None


_GAS_NOTATION = Notation(constants={"R": (0.082057366, "R")}, number=lambda value: f"{value:g}")


def test_an_expression_uses_the_subjects_constants_and_numbers() -> None:
    values = {"n": 2.0, "V": 10.0, "T": 300.0}
    assert evaluate("n*R*T/V", values, _GAS_NOTATION) == pytest.approx(4.9234, rel=1e-4)
    assert names("n*R*T/V", _GAS_NOTATION) == frozenset({"n", "T", "V"})
    assert to_latex("n*R*T/V", {"n": "n", "T": "T", "V": "V"}, notation=_GAS_NOTATION) == (
        r"\frac{n R T}{V}"
    )
    assert to_latex("n*R*T/V", {}, values, notation=_GAS_NOTATION) == (
        r"\frac{2 \times 0.0820574 \times 300}{10}"
    )


def test_pi_is_every_subjects_constant() -> None:
    assert evaluate("2*pi", {}, _GAS_NOTATION) == pytest.approx(6.283185)
    assert names("pi*r**2", _GAS_NOTATION) == frozenset({"r"})


def test_an_expression_is_never_executed() -> None:
    with pytest.raises(ExpressionError):
        evaluate("__import__('os')", {}, _GAS_NOTATION)


def test_an_asked_phrase_reads_the_unit_after_it_as_written() -> None:
    """ "pH of 5 mM": a concentration, so the 5 is not the pH's label; "5 mm" would be a length."""
    from app.services.law_binding.words import ask_strength

    table = UnitTable({"mM": "millimole / liter", "mm": "millimeter"}, {})
    # A concentration after the ask is a value of another kind: the phrase is asked.
    assert ask_strength(" the pH of 5 mM HCl", ("ph",), ("dimensionless",), table) == 2
    # A label of the asked kind is not an ask; the phrase is matched without case.
    assert ask_strength(" the length of 5 mm", ("length",), ("meter",), table) == 0
    assert ask_strength(" the Length of the rod", ("length",), ("meter",), table) == 6


@pytest.mark.parametrize(
    ("clause", "ask"),
    [
        (" does the temperature of 2 kg of water increase after heating", "temperature increase"),
        (" does the pressure of the gas decrease as it cools", "pressure decrease"),
        (" what is the temperature increase of the water", "temperature increase"),
    ],
)
def test_a_quantity_can_be_asked_through_its_change_verb(clause: str, ask: str) -> None:
    from app.services.law_binding.words import ask_strength

    assert ask_strength(clause, (ask,), ("kelvin",), _UNITS) == len(ask)
