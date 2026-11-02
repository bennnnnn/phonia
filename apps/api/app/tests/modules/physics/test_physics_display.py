"""One way to show a physics number and unit, in plain text and in LaTeX."""

from __future__ import annotations

import pytest

from app.modules.physics.display import (
    GIVEN_FIGURES,
    latex_number,
    latex_unit,
    plain_number,
    plain_quantity,
    plain_unit,
    typeset_numbers,
)
from app.modules.physics.solvers.chip import render_chip, render_chip_latex
from app.modules.physics.solvers.results import QuantityResult


@pytest.mark.parametrize(
    ("value", "plain", "latex"),
    [
        (39.618, "39.6", "39.6"),
        (0.2157, "0.216", "0.216"),
        (36.7875, "36.8", "36.8"),
        (20.0, "20", "20"),
        # An answer that ends within one decimal is printed whole, as a book does.
        (22620, "22620", "22620"),
        (36250, "36250", "36250"),
        (3812.5, "3812.5", "3812.5"),
        (240000, "2.4 × 10⁵", r"2.4 \times 10^{5}"),
        (612500, "612500", "612500"),
        # Longer ones keep three figures but every whole digit.
        (22620.47, "22620", "22620"),
        (1 / 3, "0.333", "0.333"),
        (12345678.0, "1.23 × 10⁷", r"1.23 \times 10^{7}"),
        (117187.5, "117187.5", "117187.5"),
        (6.4e6, "6.4 × 10⁶", r"6.4 \times 10^{6}"),
        (1234567, "1234567", "1234567"),
        (3.3131e-19, "3.31 × 10⁻¹⁹", r"3.31 \times 10^{-19}"),
        # Rounding comes before the choice of form.
        (99999.97, "1 × 10⁵", r"1 \times 10^{5}"),
        (0.00099996, "0.001", "0.001"),
        (-29.714, "-29.7", "-29.7"),
        (0.0, "0", "0"),
    ],
)
def test_answer_numbers_have_school_figures_and_no_calculator_notation(
    value: float, plain: str, latex: str
) -> None:
    assert plain_number(value) == plain
    assert latex_number(value) == latex


def test_a_given_keeps_the_figures_typed() -> None:
    assert plain_number(4186, GIVEN_FIGURES) == "4186"
    assert plain_number(0.385, GIVEN_FIGURES) == "0.385"
    assert latex_number(6.62607015e-34, GIVEN_FIGURES) == r"6.62607 \times 10^{-34}"


@pytest.mark.parametrize(
    ("unit", "plain", "latex"),
    [
        ("m/s^2", "m/s²", r"\,\mathrm{m/s²}"),
        ("kg*m^2", "kg·m²", r"\,\mathrm{kg·m²}"),
        ("N*s", "N·s", r"\,\mathrm{N·s}"),
        ("J/kg/K", "J/(kg·K)", r"\,\mathrm{J/(kg·K)}"),
        ("uC", "µC", r"\,\mathrm{µC}"),
        ("deg", "°", r"^\circ"),
        ("ohm", "Ω", r"\,\Omega"),
        ("", "", ""),
    ],
)
def test_units_are_upright_symbols(unit: str, plain: str, latex: str) -> None:
    assert plain_unit(unit) == plain
    assert latex_unit(unit) == latex


def test_an_angle_sits_against_its_number() -> None:
    assert plain_quantity(23.685, "deg") == "23.7°"
    assert plain_quantity(6, "ohm") == "6 Ω"


def test_rows_lose_calculator_notation_and_float_noise() -> None:
    row = r"E = \frac{6.6261e-34 \cdot 3e+08}{5e-07} + 0.30000000000000004 - 4186"
    assert typeset_numbers(row) == (
        r"E = \frac{6.6261 \times 10^{-34} \cdot 3 \times 10^{8}}{5 \times 10^{-7}} + 0.3 - 4186"
    )


def test_a_chip_reads_the_same_in_both_spellings() -> None:
    items = (
        QuantityResult("", 3.3131e-19, "J", detail="2.068 eV"),
        QuantityResult("", 2.4525, "m/s^2"),
    )
    assert render_chip(items) == "3.31 × 10⁻¹⁹ J (2.07 eV) and 2.45 m/s²"
    assert render_chip_latex(items) == (
        r"3.31 \times 10^{-19}\,\mathrm{J}\ (\text{2.07 eV})"
        r"\ \text{and}\ 2.45\,\mathrm{m/s²}"
    )


def test_a_note_escapes_latex_specials() -> None:
    item = QuantityResult("", 0.39988, "", detail="39.988%")
    assert render_chip((item,)) == "0.4 (40%)"
    assert render_chip_latex((item,)) == r"0.4\ (\text{40\%})"


@pytest.mark.parametrize(
    ("unit", "shown"),
    [
        ("miles per hour", "mph"),
        ("ohm m", "Ω·m"),
        ("per K", "K⁻¹"),
        ("per second", "s⁻¹"),
        ("per kelvin", "K⁻¹"),
        ("per cubic meter", "m⁻³"),
        ("degrees celsius", "°C"),
        ("J/(kg K)", "J/(kg·K)"),
        ("N m", "N·m"),
    ],
)
def test_a_unit_written_in_words_shows_its_symbol(unit: str, shown: str) -> None:
    assert plain_unit(unit) == shown
    assert latex_unit(unit) == rf"\,\mathrm{{{shown}}}"


def test_every_unit_the_scanner_reads_in_words_has_a_symbol() -> None:
    from app.modules.physics.given_units import _SYMBOLS, _WORDS

    for spelling in (*_WORDS, *_SYMBOLS):
        if " " in spelling:
            shown = plain_unit(spelling)
            assert " " not in shown and "per" not in shown, (spelling, shown)


@pytest.mark.parametrize(
    ("row", "typeset"),
    [
        (r"T = 2\pi\sqrt{\frac{7e+06^3}{GM}}", r"T = 2\pi\sqrt{\frac{(7 \times 10^{6})^3}{GM}}"),
        (r"F = \frac{k q}{5e-07^{2}}", r"F = \frac{k q}{(5 \times 10^{-7})^{2}}"),
        # Not raised, or not a product: no brackets.
        (r"E = 6.6261e-34 \cdot f", r"E = 6.6261 \times 10^{-34} \cdot f"),
    ],
)
def test_a_typeset_number_raised_to_a_power_keeps_its_brackets(row: str, typeset: str) -> None:
    assert typeset_numbers(row) == typeset


@pytest.mark.parametrize(
    ("name", "symbol", "value"),
    [
        ("mu_0", r"\mu_0", r"1.25664 \times 10^{-6}"),
        ("epsilon_0", r"\varepsilon_0", r"8.85419 \times 10^{-12}"),
        ("k_e", "k_e", r"8.98755 \times 10^{9}"),
        ("G_grav", "G", r"6.6743 \times 10^{-11}"),
        ("h_planck", "h", r"6.62607 \times 10^{-34}"),
        ("c_light", "c", r"2.99792 \times 10^{8}"),
        ("e_charge", "e", r"1.60218 \times 10^{-19}"),
        ("m_e", "m_e", r"9.10938 \times 10^{-31}"),
        ("R_gas", "R", "8.31446"),
        ("k_B", "k_B", r"1.38065 \times 10^{-23}"),
        ("hbar", r"\hbar", r"1.05457 \times 10^{-34}"),
        ("R_inf", r"R_\infty", r"1.09737 \times 10^{7}"),
        ("a_0", "a_0", r"5.29177 \times 10^{-11}"),
        ("sigma", r"\sigma", r"5.67037 \times 10^{-8}"),
    ],
)
def test_a_constant_shows_its_symbol_in_a_formula_and_six_figures_in_a_substitution(
    name: str, symbol: str, value: str
) -> None:
    from app.modules.physics.expression import PHYSICS_NOTATION, to_latex

    assert len(PHYSICS_NOTATION.constants) == 14
    assert to_latex(name, {}) == symbol
    assert to_latex(name, {}, {}) == value
