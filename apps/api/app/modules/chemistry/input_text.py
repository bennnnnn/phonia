# ruff: noqa: RUF001 -- the point of this module is Unicode scripts and dots.
"""What a student typed, as the ASCII text every chemistry reader reads.

The app's own replies are typeset (``H₂SO₄``, ``Fe³⁺``, ``CuSO₄·5H₂O``, ``10⁻³``), so a
student who copies one back types Unicode. The gate, the templates, the binder and the turn
context all read ASCII formulas, and a subscript digit used to end a formula: "the molar mass
of H₂SO₄" was answered as the molar mass of H. ``read_chemistry_text`` spells the text once,
at the input:

- a subscript digit is a digit: ``H₂SO₄`` is ``H2SO4``;
- a superscript is a charge or an exponent: ``Fe³⁺`` is ``Fe^3+``, ``SO₄²⁻`` is ``SO4^2-``,
  ``OH⁻`` is ``OH-`` and ``10⁻³`` is ``10^-3``;
- a hydrate's dot is one character: ``CuSO4.5H2O``, ``CuSO4 • 5H2O`` and ``CuSO4*5H2O`` are
  ``CuSO4·5H2O``, one formula with its water. A full stop that ends a sentence, a decimal
  point and a product of two numbers are not hydrate dots;
- a lowercase ``ph`` beside its value is pH: "whats the ph of 0.10 M HCl", "ph = 3.2";
- an ``=`` between two sides of formulas is the arrow of an equation to balance:
  "Al + HCl = AlCl3 + H2, balance it".

It changes how a formula or a symbol is written, never a number or a word, and reading text
it already read changes nothing.
"""

from __future__ import annotations

import re

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.formula import parse_formula
from app.services.glyphs import SUBSCRIPT_DIGITS, SUPERSCRIPT_SIGNED

_SUBSCRIPTS = SUBSCRIPT_DIGITS
_SUPERSCRIPTS = SUPERSCRIPT_SIGNED
# A run of superscripts, and a keyboard sign straight after its digits ("Fe²+"). A sign
# followed by a digit is the next term's ("x²-1"), not a charge.
_SCRIPT_RUN = re.compile(r"([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)([+\-−](?![\d.]))?")
_TRUE_MINUS = "−"

# The canonical hydrate dot. ``formula.parse_formula`` reads it, and a number reader never
# takes "4.5" out of "CuSO4·5H2O".
HYDRATE_DOT = "·"
# A salt, a dot, and the water (or second salt) it carries. A full stop is a hydrate dot only
# with no space and a coefficient after it ("CuSO4.5H2O", never "of NaCl. 5 g").
_HYDRATE = re.compile(
    r"(?<![A-Za-z0-9])(?P<salt>[A-Z][A-Za-z0-9()]*)"
    r"(?:(?P<period>\.)|\s?(?P<dot>[·•⋅∙*])\s?)"
    r"(?P<water>\d{0,2}[A-Z][A-Za-z0-9()]*)(?![A-Za-z0-9(])"
)
_COEFFICIENT = re.compile(r"(\d*)\s*(.*)", re.DOTALL)

# "ph" in lowercase is a word as often as a symbol ("my ph is 0412 555 123"). It is pH beside
# a pH value, or before a molar concentration. "PH" and "Ph" count only before a
# concentration: "PH = 7 cm" is a segment in geometry.
_CONCENTRATION = (
    r"(?:an?\s+|the\s+)?(?:solution\s+(?:of|with)\s+)?(?:\d+(?:\.\d+)?|\.\d+)"
    r"(?:\s*(?:[x×*·]\s*10\s*\^?\s*[-+−]?\d{1,3}|[eE][-+]?\d{1,3}))?"
    r"\s*(?:M|mM|mol/L|molar)(?![A-Za-z])"
)
_PH_WORD = re.compile(
    r"(?<![A-Za-z0-9])(?:ph(?=\s*(?:=|is)\s*(?:1[0-4]|\d)(?:\.\d+)?(?![\d.]))"
    rf"|(?:ph|PH|Ph)(?=\s+of\s+{_CONCENTRATION}))(?![A-Za-z0-9])"
)

# "Al + HCl = AlCl3 + H2": an "=" is the arrow only when the question asks to balance and
# every term on both sides is a formula.
_BALANCE = re.compile(r"\b(?:balance|balanced|balancing|coefficients?)\b", re.IGNORECASE)
_TERM = r"(?:\d{1,2}\s*)?[A-Z][A-Za-z0-9()]*"
_SIDE = rf"{_TERM}(?:\s*\+\s*{_TERM})*"
_EQUALS_SIGN = re.compile(r"(?<![<=>!])=(?![=>])")
_LEFT_SIDE = re.compile(rf"(?<![A-Za-z0-9])({_SIDE})\s*$")
_RIGHT_SIDE = re.compile(rf"\s*({_SIDE})(?![A-Za-z0-9(])")
# Each side is read in a window around its "=", and only the first few "=" are read, so a
# long paste of "A + A + …" costs a bounded amount, never a scan per position.
_SIDE_WINDOW = 160
_MAX_EQUALS = 8


def spell_scripts(text: str) -> str:
    """Subscript digits as digits; a superscript as a charge (Fe^3+) or an exponent (10^-3)."""

    def spell(match: re.Match[str]) -> str:
        run = match.group(1).translate(_SUPERSCRIPTS)
        sign = (match.group(2) or "").replace(_TRUE_MINUS, "-")
        digits = run.strip("+-")
        if not digits:
            # Signs alone are a charge: OH⁻, H⁺, e⁻.
            return run + sign
        return f"^{run}{sign}"

    return _SCRIPT_RUN.sub(spell, text.translate(_SUBSCRIPTS)).replace(_TRUE_MINUS, "-")


def _split_coefficient(term: str) -> tuple[str, str]:
    """``5H2O`` → ("5", "H2O"); ``H2O`` → ("", "H2O")."""
    match = _COEFFICIENT.fullmatch(term.strip())
    return ("", term) if match is None else (match.group(1), match.group(2))


def _atoms(token: str) -> dict[str, int] | None:
    atoms = parse_formula(token)
    if not atoms or any(symbol not in BY_SYMBOL for symbol in atoms):
        return None
    return atoms


def _compound(token: str) -> bool:
    """A formula of two atoms or more: ``NaCl``, ``H2O``, ``O2`` (never a bare ``P``)."""
    atoms = _atoms(token)
    return atoms is not None and sum(atoms.values()) >= 2


def _hydrate_dots(text: str) -> str:
    def join(match: re.Match[str]) -> str:
        salt, water = match.group("salt"), match.group("water")
        coefficient, body = _split_coefficient(water)
        if match.group("period") is not None and not coefficient:
            return match.group(0)
        if not _compound(salt) or not _compound(body):
            return match.group(0)
        return f"{salt}{HYDRATE_DOT}{water}"

    # A double salt has two dots (K2SO4·Al2(SO4)3·24H2O); each pass joins one pair.
    for _ in range(3):
        joined = _HYDRATE.sub(join, text)
        if joined == text:
            break
        text = joined
    return text


def _formula_side(side: str) -> bool:
    """Every term a formula of real elements, and one of them a compound or a molecule."""
    terms = [_split_coefficient(term)[1] for term in side.split("+")]
    return all(_atoms(term) is not None for term in terms) and any(map(_compound, terms))


def _equals_arrow(text: str) -> str:
    if "=" not in text or _BALANCE.search(text) is None:
        return text
    pieces: list[str] = []
    done = 0
    for count, sign in enumerate(_EQUALS_SIGN.finditer(text)):
        if count == _MAX_EQUALS:
            break
        if sign.start() < done:
            continue
        window_start = max(done, sign.start() - _SIDE_WINDOW)
        left = _LEFT_SIDE.search(text, window_start, sign.start())
        right = _RIGHT_SIDE.match(text, sign.end(), min(len(text), sign.end() + _SIDE_WINDOW))
        if left is None or right is None:
            continue
        if not (_formula_side(left.group(1)) and _formula_side(right.group(1))):
            continue
        pieces.append(text[done : left.start(1)])
        pieces.append(f"{left.group(1).strip()} -> {right.group(1).strip()}")
        done = right.end(1)
    pieces.append(text[done:])
    return "".join(pieces)


def read_chemistry_text(text: str) -> str:
    """The student's text with formulas, charges, hydrate dots and pH written in ASCII."""
    if not text:
        return text
    text = spell_scripts(text)
    text = _hydrate_dots(text)
    text = _PH_WORD.sub("pH", text)
    return _equals_arrow(text)
