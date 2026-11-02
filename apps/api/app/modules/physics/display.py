# ruff: noqa: RUF001, RUF002, RUF003 -- the point of this module is ×, ·, Ω and superscripts.
"""How physics shows a number and a unit: one formatter for every answer.

A verified answer has three significant figures, never calculator notation,
and upright units, unless it ends within six figures: 36250 J stays 36250 J.
Scientific notation is used outside [10⁻³, 10⁵). A given
is echoed with the figures the user typed (up to six), never rounded to the
answer's precision.

Two spellings of the same value: plain text with Unicode symbols for guards,
logs and the web reader (``3.31 × 10⁻¹⁹ J``), and LaTeX for the answer card
and the working (``3.31 \\times 10^{-19}\\,\\mathrm{J}``).
"""

from __future__ import annotations

import math
import re

from app.services.school_rounding import round_figures, trim_zeros

ANSWER_FIGURES = 3
GIVEN_FIGURES = 6
_SCIENTIFIC_BELOW = 1e-3
_SCIENTIFIC_FROM = 1e5
_PLAIN_WHOLE_BELOW = 1e7
# A value below 10⁷ that ends within one decimal has at most eight figures.
_EXACT_FIGURES = 8

_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _school_figures(value: float) -> tuple[int, bool]:
    """How many figures a textbook prints for ``value``, and whether that is all of it.

    A book never rounds away a digit before the point: 50 × 10 × 72.5 is 36250,
    and 7625 / 2 is 3812.5, so an answer that ends within one decimal place is
    printed whole; 36300 and 3810 read to a student as a wrong sum. Anything
    longer keeps three figures, but at least every whole digit: 9.81 × 3.75 is
    36.8 and 22620.47 is 22620.
    """
    if value == 0 or not math.isfinite(value):
        return ANSWER_FIGURES, False
    mantissa, exponent = round_figures(value, _EXACT_FIGURES)
    written = trim_zeros(format(mantissa.scaleb(exponent), "f"))
    if abs(value) >= _PLAIN_WHOLE_BELOW:
        return ANSWER_FIGURES, False
    if value.is_integer():
        return max(len(str(int(abs(value))).rstrip("0")), 1), True
    if math.isclose(float(written), value, rel_tol=1e-9):
        whole, _, decimals = written.lstrip("-").partition(".")
        if len(decimals) <= 1:
            return max(len((whole + decimals).strip("0")), 1), True
    return max(ANSWER_FIGURES, exponent + 1 if abs(value) < _SCIENTIFIC_FROM else 0), False


def _parts(value: float, figures: int) -> tuple[str, int | None]:
    """(mantissa, exponent) after rounding half up, exponent None for plain form.

    Rounding comes first, so 99999.97 is 1 × 10⁵ rather than 100000, and the
    plain form is fixed-point. An answer's figures are a textbook's
    (``_school_figures``); past 10⁵ one stays plain below 10⁷ when it has
    more than three figures.
    """
    exact = False
    if figures == ANSWER_FIGURES:
        figures, exact = _school_figures(value)
    mantissa, exponent = round_figures(value, figures)
    rounded = float(mantissa.scaleb(exponent))
    # Past 10⁵ a value stays plain only when its exponent form would round digits away:
    # 117187.5 and 612500, but 6.4 × 10⁶ and 2.4 × 10⁵ as books print them.
    plain_whole = exact and figures > ANSWER_FIGURES and abs(rounded) < _PLAIN_WHOLE_BELOW
    in_plain_range = _SCIENTIFIC_BELOW <= abs(rounded) < _SCIENTIFIC_FROM
    if rounded != 0 and not plain_whole and not in_plain_range:
        return trim_zeros(f"{mantissa:.{figures - 1}f}"), exponent
    decimals = max(figures - 1 - exponent, 0)
    return trim_zeros(f"{rounded:.{decimals}f}"), None


def plain_number(value: float, figures: int = ANSWER_FIGURES) -> str:
    """``39.6``, ``0.216``, ``3.31 × 10⁻¹⁹``."""
    if not math.isfinite(value):
        return str(value)
    mantissa, exponent = _parts(value, figures)
    if exponent is None:
        return mantissa
    return f"{mantissa} × 10{str(exponent).translate(_SUPERSCRIPT)}"


def latex_given(value: float) -> str:
    """A given or a working value with the figures the user wrote, up to six."""
    return latex_number(value, GIVEN_FIGURES)


def latex_number(value: float, figures: int = ANSWER_FIGURES) -> str:
    """``39.6``, ``3.31 \\times 10^{-19}``."""
    if not math.isfinite(value):
        return str(value)
    mantissa, exponent = _parts(value, figures)
    if exponent is None:
        return mantissa
    return rf"{mantissa} \times 10^{{{exponent}}}"


# Spelled-out units a question may carry, as the symbol a textbook prints.
_SPELLED = {
    "seconds": "s",
    "second": "s",
    "secs": "s",
    "sec": "s",
    "minutes": "min",
    "minute": "min",
    "mins": "min",
    "hours": "h",
    "hour": "h",
    "hrs": "h",
    "hr": "h",
    "meters": "m",
    "metres": "m",
    "meter": "m",
    "metre": "m",
    "kilometers": "km",
    "kilometres": "km",
    "centimeters": "cm",
    "centimetres": "cm",
    "kilograms": "kg",
    "kilogram": "kg",
    "grams": "g",
    "gram": "g",
    "newtons": "N",
    "newton": "N",
    "joules": "J",
    "joule": "J",
    "watts": "W",
    "watt": "W",
    "volts": "V",
    "volt": "V",
    "amps": "A",
    "amperes": "A",
    "ampere": "A",
    "ohms": "ohm",
    "degrees": "deg",
    "degree": "deg",
    "°": "deg",
    "uC": "µC",
    "uF": "µF",
    "um": "µm",
    "micrometers": "µm",
    "dioptre": "D",
    "dioptres": "D",
    "diopter": "D",
    "diopters": "D",
    "percent": "%",
}
# Solver unit spellings with a symbol of their own.
_PLAIN_SYMBOLS = {"deg": "°", "ohm": "Ω", "degC": "°C", "D": "D", "%": "%", "": ""}
_LATEX_SYMBOLS = {
    "deg": r"^\circ",
    "ohm": r"\,\Omega",
    "degC": r"\,^\circ\mathrm{C}",
    "%": r"\,\%",
    "": "",
}
_POWER = re.compile(r"\^\{?(-?\d+)\}?")
_BARE_POWER = re.compile(r"(?<=[A-Za-zµμΩ])(-?\d)(?![\d.])")

# A unit written in words, by the unit it means: "miles per hour" is mph, and
# "ohm m" is Ω·m. Spelling it back out would print "miles·per·hour".
_WORD_UNIT_SYMBOLS = {
    "pascal * second": "Pa·s",
    "degC": "°C",
    "joule / kilogram / kelvin": "J/(kg·K)",
    "kilogram * meter / second": "kg·m/s",
    "kilogram * meter ** 2": "kg·m²",
    "meter / second ** 2": "m/s²",
    "mile / hour": "mph",
    "newton * meter": "N·m",
    "newton * second": "N·s",
    "ohm * meter": "Ω·m",
    "1 / second": "s⁻¹",
    "1 / kelvin": "K⁻¹",
    "1 / millimeter": "lines/mm",
    "1 / centimeter": "lines/cm",
    "1 / meter": "lines/m",
    "1 / meter ** 3": "m⁻³",
}


def _symbol(unit: str) -> str:
    return _SPELLED.get(unit, _SPELLED.get(unit.lower(), unit)) if unit else unit


def _written_in_words(unit: str) -> str | None:
    """The symbol for a unit written as words ("miles per hour"), if it is one."""
    if " " not in unit.strip():
        return None
    from app.modules.physics.givens import unit_expression

    expression = unit_expression(unit.strip())
    return None if expression is None else _WORD_UNIT_SYMBOLS.get(expression)


def _explicit_powers(unit: str) -> str:
    """``m/s2`` as ``m/s^2``: a power typed bare, in a spelling the unit table reads.

    Only a table spelling: there a digit after a unit letter can only be a power.
    """
    from app.modules.physics.givens import unit_expression

    if unit_expression(unit) is None:
        return unit
    return _BARE_POWER.sub(r"^\1", unit)


def plain_unit(unit: str) -> str:
    """``m/s²``, ``kg·m²``, ``J/(kg·K)``, ``°``, ``Ω``."""
    unit = _symbol(unit)
    if unit in _PLAIN_SYMBOLS:
        return _PLAIN_SYMBOLS[unit]
    words = _written_in_words(unit)
    if words is not None:
        return words
    spelled = _grouped_denominator(_explicit_powers(unit)).replace("*", "·").replace(" ", "·")
    return _POWER.sub(lambda match: match.group(1).translate(_SUPERSCRIPT), spelled)


def latex_unit(unit: str) -> str:
    """The unit as it follows a number in LaTeX, leading space included.

    The unit is an upright text run holding the plain spelling (``m/s²``,
    ``µC``): MathText draws a ``\\mathrm`` group as written, so a nested
    command or brace inside it would show raw.
    """
    unit = _symbol(unit)
    if unit in _LATEX_SYMBOLS:
        return _LATEX_SYMBOLS[unit]
    return rf"\,\mathrm{{{plain_unit(unit)}}}"


def _grouped_denominator(unit: str) -> str:
    """``J/kg/K`` reads as ``J/(kg·K)``: a second slash would divide by K twice."""
    head, *rest = unit.split("/")
    if len(rest) < 2:
        return unit
    return f"{head}/({'*'.join(rest)})"


# Pint unit names in catalog dimensions, as their SI symbols.
_SI_SYMBOLS = {
    "meter": "m",
    "second": "s",
    "kilogram": "kg",
    "newton": "N",
    "joule": "J",
    "watt": "W",
    "pascal": "Pa",
    "kelvin": "K",
    "ampere": "A",
    "coulomb": "C",
    "volt": "V",
    "ohm": "ohm",
    "farad": "F",
    "henry": "H",
    "tesla": "T",
    "weber": "Wb",
    "hertz": "Hz",
    "mole": "mol",
    "radian": "rad",
}
# The one catalog dimension that is not SI: a value in rpm is solved in rad/s.
_NON_SI = {"revolution / minute": "radian / second"}


def si_symbol(dimension: str) -> str:
    """``joule / kilogram / kelvin`` as ``J/kg/K``: the SI unit a solver works in."""
    expression = _NON_SI.get(dimension, dimension)
    for name, symbol in _SI_SYMBOLS.items():
        expression = re.sub(rf"\b{name}\b", symbol, expression)
    return expression.replace(" ** ", "^").replace(" / ", "/").replace(" * ", "*")


def plain_quantity(value: float, unit: str, figures: int = ANSWER_FIGURES) -> str:
    shown_unit = plain_unit(unit)
    if not shown_unit:
        return plain_number(value, figures)
    gap = "" if shown_unit == "°" else " "
    return f"{plain_number(value, figures)}{gap}{shown_unit}"


def latex_quantity(value: float, unit: str, figures: int = ANSWER_FIGURES) -> str:
    return f"{latex_number(value, figures)}{latex_unit(unit)}"


_NUMBER_IN_TEXT = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")


def given_number(value: float) -> str:
    """A given as the working writes it: plain, to the givens' figures."""
    return plain_number(value, GIVEN_FIGURES)


def plain_numbers_in(text: str) -> str:
    """A note or a scene label with its numbers at answer precision."""
    return _NUMBER_IN_TEXT.sub(lambda match: plain_number(float(match.group())), text)


_E_NOTATION = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)[eE]([-+]?\d+)(?![\w.])")
_LONG_DECIMAL = re.compile(r"(?<![\w.])(-?\d+\.\d{7,})(?![\w.])")


def typeset_numbers(row: str) -> str:
    """A LaTeX row without calculator notation or float noise.

    ``6.6261e-34`` becomes ``6.6261 \\times 10^{-34}``; a decimal that floating
    point stretched past six figures (``0.30000000000000004``) is cut back.
    Integers and the user's own decimals are left as written. A number raised
    to a power keeps its brackets once it is a product: ``7e+06^3`` is
    ``(7 \\times 10^{6})^3``, not a double superscript.
    """

    def scientific(match: re.Match[str]) -> str:
        shown = latex_number(float(match.group(0)), GIVEN_FIGURES)
        raised = match.string.startswith("^", match.end())
        return f"({shown})" if raised and r"\times" in shown else shown

    row = _E_NOTATION.sub(scientific, row)
    return _LONG_DECIMAL.sub(lambda match: latex_number(float(match.group(1)), GIVEN_FIGURES), row)


# One value as ``latex_number`` and ``latex_unit`` print it: "2 \\times 10^{-10}\\,\\mathrm{m}".
_QUANTITY = r"-?\d[\d.]*(?: \\times 10\^\{-?\d+\})?(?:\\,\S+)?"
_CONVERSION_ROW = re.compile(rf"\A[^=]+ = {_QUANTITY} = {_QUANTITY}")


def is_conversion_row(row: str) -> bool:
    """A row ``conversion_row`` wrote: one value restated in another unit, no arithmetic."""
    return _CONVERSION_ROW.fullmatch(row) is not None


_VALUE_ROW = re.compile(rf"\A[^=]+ (?:=|\\approx) {_QUANTITY}")
_NUMBER = re.compile(r"(?P<number>-?\d[\d.]*)(?: \\times 10\^\{(?P<power>-?\d+)\})?")


def is_value_row(row: str) -> bool:
    """``E = 2.16 \\times 10^{7}\\,\\mathrm{J}``: a symbol and its value, no arithmetic left."""
    return _VALUE_ROW.fullmatch(row) is not None


def quantity_number(row: str | None) -> float | None:
    """The first value after the symbol: 0.0492 in ``V = 0.0492\\,\\mathrm{m^3} = 49.2 L``."""
    match = _NUMBER.match(row.split(" = ", 1)[1]) if row and " = " in row else None
    if match is None:
        return None
    try:
        value = float(match.group("number"))
    except ValueError:
        return None
    return value * 10.0 ** int(match.group("power")) if match.group("power") else value


def conversion_row(symbol: str, before: tuple[float, str], after: tuple[float, str]) -> str:
    """The step from the SI value the substitution gives to the unit the answer is shown in.

    "V = 0.0492 m³ = 49.2 L": the working reaches the answer the reply states.
    """
    return (
        f"{symbol} = {latex_number(before[0])}{latex_unit(before[1])} "
        f"= {latex_number(after[0])}{latex_unit(after[1])}"
    )


def latex_factor(numerator: float, denominator: float) -> str:
    """What turns a given into SI, as a student would write it: ``\\times 1000/3600`` for km/h.

    Whole numbers above and below the line stay a fraction, so the hour's 3600 s
    shows; anything else is one factor (``\\times 0.01``, ``\\times 10^{-9}``).
    """

    def whole(value: float) -> bool:
        return value >= 1 and math.isclose(value, round(value), rel_tol=1e-9)

    if denominator != 1 and whole(numerator) and whole(denominator):
        return rf"\times {round(numerator)}/{round(denominator)}"
    factor = latex_given(numerator / denominator)
    # "10^{-9}", not "1 \times 10^{-9}".
    return rf"\times {factor.removeprefix(r'1 \times ')}"
