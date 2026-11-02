"""The graph fence's expression, printed so the phone can resample it.

``sample_function`` plots SymPy's reading of what was written. The phone's
``lib/math/graphExpr.ts`` re-reads the fence's ``expr`` to resample on zoom, and
its grammar is narrower than SymPy's: a function needs brackets (``sin x`` is
refused), there is no ``√`` or ``|``, and ``xe`` is one unknown name. So the fence
carries the parsed expression printed in that grammar alone: ``sin(x)``,
``cos(2x)``, ``sqrt(x)``, ``abs(x)``, ``x*e^x``, ``log(x)`` for base 10 and
``ln(x)`` for natural. SymPy stays the one reader of the user's text; the phone
reads only this printer's output. ``docs/fixtures/graph_expr_cases.json`` holds
both sides to it (the ``fence`` field).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from sympy import (
    Abs,
    Pow,
    S,
    acos,
    asin,
    atan,
    ceiling,
    cos,
    cosh,
    exp,
    floor,
    log,
    sin,
    sinh,
    tan,
    tanh,
)

# GraphBlockSpec.expr and the phone's reader both stop at 256 characters.
_MAX_TEXT = 256
# SymPy's function → the phone's name for it (``FUNCS`` in graphExpr.ts). SymPy's
# ``log`` is natural; a base-10 log is ``log(x)/log(10)``, printed back as ``log``.
_FUNCTIONS: dict[Any, str] = {
    sin: "sin",
    cos: "cos",
    tan: "tan",
    asin: "asin",
    acos: "acos",
    atan: "atan",
    sinh: "sinh",
    cosh: "cosh",
    tanh: "tanh",
    Abs: "abs",
    floor: "floor",
    ceiling: "ceil",
    log: "ln",
}
_LN_TEN = log(10)


class _NoSpelling(Exception):
    """A node the phone's grammar cannot write (another symbol, ``sec``, ``I``, ∞)."""


def graph_expr_text(expr: Any, variable: str) -> str | None:
    """``expr`` in the phone's plot grammar, or None when that grammar cannot write it."""
    try:
        text = _Printer(variable).text(expr)
    except _NoSpelling:
        return None
    return text if len(text) <= _MAX_TEXT else None


class _Printer:
    def __init__(self, variable: str) -> None:
        self.variable = variable

    def text(self, node: Any) -> str:
        if node.is_Add:
            return self._sum(node)
        if node.is_Mul:
            return self._product(node)
        if node.is_Pow:
            return self._power(node)
        if isinstance(node, exp):
            return f"e^{self._operand(node.args[0])}"
        if node.is_Number:
            return _number(node)
        if node is S.Pi:
            return "pi"
        if node is S.Exp1:
            return "e"
        if node.is_Symbol and node.name == self.variable:
            return str(node.name)
        name = _FUNCTIONS.get(node.func)
        if name is None or len(node.args) != 1:
            raise _NoSpelling(str(node))
        return f"{name}({self.text(node.args[0])})"

    def _sum(self, node: Any) -> str:
        first, *rest = node.as_ordered_terms()
        out = self.text(first)
        for term in rest:
            if term.could_extract_minus_sign():
                out += f" - {self._factor(-term)}"
            else:
                out += f" + {self.text(term)}"
        return out

    def _product(self, node: Any) -> str:
        coeff, rest = node.as_coeff_Mul()
        if coeff.is_negative:
            return f"-{self._factor(-node)}"
        top: list[Any] = []
        bottom: list[Any] = []
        for factor in rest.as_ordered_factors():
            if factor.is_Pow and factor.exp.is_Rational and factor.exp.is_negative:
                bottom.append(Pow(factor.base, -factor.exp))
            else:
                top.append(factor)
        top_texts = [self._factor(factor) for factor in top]
        # log(x)/log(10) is the school log the server read ``log(x)`` as.
        base_ten = next((i for i, f in enumerate(top) if f.func is log and f != _LN_TEN), None)
        if _LN_TEN in bottom and base_ten is not None:
            bottom.remove(_LN_TEN)
            top_texts[base_ten] = f"log({self.text(top[base_ten].args[0])})"
        numerator = _juxtaposed(_coefficient(coeff.p if coeff.is_Rational else coeff), top_texts)
        if coeff.is_Rational and coeff.q != 1:
            bottom.insert(0, S(coeff.q))
        if not bottom:
            return numerator or "1"
        return f"{numerator or '1'}/{self._denominator(bottom)}"

    def _power(self, node: Any) -> str:
        base, power = node.base, node.exp
        if power.is_Rational and power.is_negative:
            return f"1/{self._denominator([Pow(base, -power)])}"
        if power == S.Half:
            return f"sqrt({self.text(base)})"
        return f"{self._operand(base)}^{self._operand(power)}"

    def _denominator(self, factors: list[Any]) -> str:
        """After ``/``: one number, name, call, power or bracketed sum; else a bracketed product."""
        first, *rest = factors
        coeff = _number(first) if first.is_Integer else None
        text = _juxtaposed(coeff, [self._factor(f) for f in (factors if coeff is None else rest)])
        return text if len(factors) == 1 and not first.is_Mul else f"({text})"

    def _factor(self, node: Any) -> str:
        """A product's factor: a sum takes brackets so ``*`` cannot split it."""
        text = self.text(node)
        return f"({text})" if node.is_Add else text

    def _operand(self, node: Any) -> str:
        """A base or exponent of ``^``, bracketed unless it is one name, number or call."""
        text = self.text(node)
        return text if _is_atom(node) else f"({text})"


def _is_atom(node: Any) -> bool:
    """A name, a number from 0 up, or a function call: ``^`` cannot split it."""
    if node.is_Integer or node.is_Float:
        return bool(node >= 0)
    return bool(node.is_Symbol or node.is_NumberSymbol or node.func in _FUNCTIONS)


def _juxtaposed(coeff: str | None, factors: list[str]) -> str:
    """``3x``, ``2sin(x)``, ``2(x + 1)``: a number before a name or bracket, as written.

    The phone and the server both read a number followed by a letter or ``(`` as a
    product; anything else (``3*2^x``, ``x*e^x``) keeps its ``*``.
    """
    product = "*".join(factors)
    if coeff is None:
        return product
    if not product:
        return coeff
    glue = "" if product[0].isalpha() or product[0] == "(" else "*"
    return f"{coeff}{glue}{product}"


def _coefficient(value: Any) -> str | None:
    """A product's leading number, or None for 1 (``x``, not ``1x``)."""
    return None if value == 1 else _number(S(value))


def _number(node: Any) -> str:
    if node.is_Integer:
        return str(int(node))
    if node.is_Rational:
        return f"{node.p}/{node.q}"
    if node.is_Float and math.isfinite(float(node)):
        # Positional digits only: the phone reads ``1e-20`` as ``1*e - 20``.
        return format(Decimal(repr(float(node))), "f")
    raise _NoSpelling(str(node))
