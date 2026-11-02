"""Maths glyphs as ASCII, one table for every reader: operators and script digits.

The solver, the arithmetic gate, the work reader, the tool check, the check of a
reply's own arithmetic and the number scanners each kept a table of their own (eleven
of them): an en dash was a minus to the solver and not to the reply check, and "⋅"
folded in three of them (code-health audit DUP-07). A reader's own rewrites (π, ∞,
roots, vulgar fractions, ≤) stay with it, on top of these.
"""

from __future__ import annotations

# Escapes, not literals: RUF001 flags lookalike punctuation.
OPERATOR_GLYPHS: dict[str, str] = {
    "\u00d7": "*",  # multiplication sign
    "\u22c5": "*",  # dot operator
    "\u00b7": "*",  # middle dot
    "\u2217": "*",  # asterisk operator
    "\u00f7": "/",  # division sign
    "\u2215": "/",  # division slash
    "\u2044": "/",  # fraction slash
    "\u2212": "-",  # minus sign
    "\u2013": "-",  # en dash (phones, OCR)
    "\u2014": "-",  # em dash
}
_OPERATORS = str.maketrans(OPERATOR_GLYPHS)

SUPERSCRIPT_DIGIT_GLYPHS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
SUBSCRIPT_DIGIT_GLYPHS = "₀₁₂₃₄₅₆₇₈₉"
# Superscript digits alone, and with the signs an exponent carries ("10⁻⁹").
SUPERSCRIPT_DIGITS = str.maketrans(SUPERSCRIPT_DIGIT_GLYPHS, "0123456789")
SUPERSCRIPT_SIGNED = str.maketrans(SUPERSCRIPT_DIGIT_GLYPHS + "⁻⁺", "0123456789-+")
SUBSCRIPT_DIGITS = str.maketrans(SUBSCRIPT_DIGIT_GLYPHS, "0123456789")


def fold_operator_glyphs(text: str) -> str:
    """Every operator glyph a reader meets, as ASCII: times, divide and minus signs."""
    return text.translate(_OPERATORS)
