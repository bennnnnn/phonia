# ruff: noqa: RUF001, RUF003 -- the point of this module is the Unicode minus, arrows and scripts.
"""One notation policy for chemistry text.

Solvers, prompt text and canonical answers are **ASCII**: ``H2SO4``, ``Fe2+``, ``SO4^2-``,
``[H+]``, ``10^-4``, ``->``. That form round-trips through ``species.parse_species`` and
is what a model is shown. ``typeset`` re-encodes it for the reader (``H₂SO₄``, ``Fe²⁺``,
``SO₄²⁻``, ``[H⁺]``, ``10⁻⁴``, ``→``) and runs only on display paths: the direct reply, the
answer fence, scene text and the molecule caption. It changes characters, never content, so
it is idempotent and never touches SMILES (callers pass ``verbatim`` text around it).
"""

from __future__ import annotations

import re

_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUPERSCRIPT = str.maketrans("0123456789+-−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻")

# ``^2-``  ``^3+``  ``^-4``  ``^{-4}``  ``^(−4)``  ``^2``: a body of digits and one sign only.
# ``e^(-kt)`` and ``x^(1/2)`` are expressions, not exponents, and keep their caret.
_SIGN = r"[+\-−]"
_CARET = re.compile(
    rf"\^(?:\{{(?P<brace>[^}}]*)\}}|\((?P<paren>[^)]*)\)|(?P<bare>{_SIGN}?\d+{_SIGN}?|{_SIGN}))"
)
_CARET_BODY = re.compile(rf"^(?:{_SIGN}?\d+{_SIGN}?|{_SIGN})$")
# ``Fe2+`` ``Al3+``: a lone element symbol, a digit, a sign. ``NH4+`` is not matched: the
# lookbehind sees the N, so its 4 stays a subscript and only the sign is a charge.
_GLUED_CHARGE = re.compile(r"(?<![A-Za-z0-9])([A-Z][a-z]?)(\d)([+\-])(?![A-Za-z0-9])")
# ``[Fe(CN)6]3-``: a charge written after a closing bracket.
_BRACKET_CHARGE = re.compile(r"(?<=\])(\d?)([+\-])(?=$|[\s,.;:)])")
_SUBSCRIPT_DIGITS = re.compile(r"([A-Z][a-z]?|\))(\d+)")
# ``H+`` ``OH-`` ``NH4+`` ``[A-]`` ``e-``: a sign straight after a letter, bracket, parenthesis
# or subscript and before a boundary. ``n+1`` and ``half-life`` have a letter or digit after it.
_SINGLE_CHARGE = re.compile(r"(?<=[A-Za-z\)\]₀-₉])([+\-])(?=$|[\s\]\),.;:])")
_LOG10 = re.compile(r"\blog10\b")
_LEADING_MINUS = re.compile(r"(?<![\w.)\]⁰-⁹₀-₉])-(?=\.?\d)")


def _caret(match: re.Match[str]) -> str:
    body = match.group("brace")
    if body is None:
        body = match.group("paren")
    if body is None:
        body = match.group("bare")
    if not _CARET_BODY.match(body.strip()):
        return match.group(0)
    return body.strip().translate(_SUPERSCRIPT)


def _glued_charge(match: re.Match[str]) -> str:
    symbol, magnitude, sign = match.groups()
    return f"{symbol}{f'{magnitude}{sign}'.translate(_SUPERSCRIPT)}"


def _bracket_charge(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}".translate(_SUPERSCRIPT)


def _subscript(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2).translate(_SUBSCRIPT)}"


def typeset(text: str) -> str:
    """ASCII chemistry text as it should read: sub/superscripts, real arrows, true minus."""
    if not text:
        return text
    out = text.replace("<=>", "⇌").replace("->", "→")
    out = _CARET.sub(_caret, out)
    out = _GLUED_CHARGE.sub(_glued_charge, out)
    out = _BRACKET_CHARGE.sub(_bracket_charge, out)
    out = _SUBSCRIPT_DIGITS.sub(_subscript, out)
    out = _SINGLE_CHARGE.sub(lambda match: match.group(1).translate(_SUPERSCRIPT), out)
    out = _LOG10.sub("log₁₀", out)
    return _LEADING_MINUS.sub("−", out)


def typeset_json(value: object) -> object:
    """``typeset`` every string in a JSON-shaped value; ``kind`` tags are identifiers, not text."""
    if isinstance(value, str):
        return typeset(value)
    if isinstance(value, list):
        return [typeset_json(item) for item in value]
    if isinstance(value, dict):
        return {key: item if key == "kind" else typeset_json(item) for key, item in value.items()}
    return value
