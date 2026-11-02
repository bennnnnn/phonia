"""Parse expressions for SymPy (server-side only): normalize, run the safety checks, then
``parse_expr``. The rewrites are ``latex_normalize.py`` and ``unicode_normalize.py``; a
result is printed by ``display.py``."""

from __future__ import annotations

import re
from typing import Any

from sympy import Abs, Basic, E, Eq, I, Mul, Pow, Symbol, ceiling, log, parse_expr, pi
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    standard_transformations,
)

from app.core.config import get_settings
from app.core.sympy_notation import use_school_log_notation
from app.modules.math.schemas import EquationInput
from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy
from app.modules.math.solve.number_size import reject_huge_numbers
from app.modules.math.solve.written_names import (
    lone_quantity,
    reject_unknown_names,
    reject_unwritten_symbols,
)
from app.services.solving import SolveServiceError

# A bare ``log`` is base 10 here, so a natural log has to print as ``\ln``.
use_school_log_notation()

_TRANSFORMATIONS = (
    *standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)


def _school_log(arg: Any, base: Any = 10, evaluate: bool = True) -> Any:
    """``log(x)`` is base 10, as on a school calculator; ``ln(x)`` is natural.

    ``log(x, b)`` keeps its written base. Unevaluated, SymPy's two-argument ``log``
    prints without its base, so the quotient is built by hand."""
    if evaluate:
        return log(arg, base)
    return Mul(
        log(arg, evaluate=False), Pow(log(base, evaluate=False), -1, evaluate=False), evaluate=False
    )


_LOCALS: dict[str, Any] = {
    "pi": pi,
    "e": E,
    "E": E,
    # The math keyboard's i key types ``\\mathrm{i}``; a bare ``i`` stays a variable.
    "I": I,
    "Abs": Abs,
    "log": _school_log,
    "lg": _school_log,
    "ceil": ceiling,  # SymPy's name; unmapped, ``ceil`` was split into c*e*i*l
}


# A glued exponent ends the token. `^` is absent so `x2^3` is left for
# implicit multiplication (`x*2**3`), and `(` is absent so `log2(8)` stays a name.
_GLUED_EXPONENT_END = frozenset("+-*/=<>),] \t\n")


def _exponent_mark(prev: str, ch: str) -> bool:
    """The e of ``1e5`` or ``1.8e-5``: a float literal's exponent, never Euler's e."""
    return ch == "e" and (prev.isdigit() or prev == ".")


def _lift_glued_exponents(text: str) -> str:
    """`3x2+4` is `3x**2+4`, not `3*x*2`.

    Homework and OCR write `x2` for `x^2`. Implicit multiplication would
    otherwise split that into `x*2` and solve a different equation (`6x`).
    `x0` / `x1` stay names, a capital with digits (`P2`, `K2`) is a subscripted
    quantity, and a digit run after another letter (`sin2`, `log2`) is not an exponent.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        prev = text[i - 1] if i else ""
        if ch.islower() and not prev.isalpha() and prev != "\\" and not _exponent_mark(prev, ch):
            j = i + 1
            if j < n and text[j].isdigit():
                k = j + 1
                while k < n and text[k].isdigit():
                    k += 1
                digits = text[j:k]
                nxt = text[k] if k < n else ""
                if digits not in {"0", "1"} and (k == n or nxt in _GLUED_EXPONENT_END):
                    out.append(ch)
                    out.append("**")
                    out.append(digits)
                    i = k
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


# ``2 1/2`` is two and a half, never ``2 * 1/2``: x + 2 1/2 = 5 is x = 5/2. A power's,
# a product's or a decimal's digits (``x^2 1/2``, ``0.2 1/2``) do not start one.
_MIXED_NUMBER = re.compile(r"(?<![\w.^*/)])(\d+)\s+(\d+)\s*/\s*(\d+)(?![\d.])")


def _normalize_expr(text: str) -> str:
    s = text.strip()
    s = normalize_latex_to_sympy(s)
    s = _MIXED_NUMBER.sub(r"(\1+\2/\3)", s)
    # Lift `x2` before `^` becomes `**`, so a real caret (`x2^3`) is not
    # reread as a glued exponent.
    s = _lift_glued_exponents(s)
    s = s.replace("^", "**")
    # Python tokenizes 0x as the start of a hexadecimal literal before
    # SymPy's implicit-multiplication transform can see it. Explicitly mark
    # every number-letter boundary (2x, 0x, 3pi) as multiplication.
    s = re.sub(r"(?<=\d)(?![eE][+-]?\d)(?=[A-Za-z])", "*", s)
    s = re.sub(r"\s+", " ", s)
    return s


# Only characters a real math expression ever needs. Rejects backslashes,
# quotes, braces, semicolons, and every other punctuation a Python-eval
# gadget would need to reach beyond a plain arithmetic/algebraic expression.
_SAFE_EXPR_CHARS = re.compile(r"^[\w\s+\-*/().,=<>!]*$")
_DECIMAL_NUMBER = re.compile(r"\d+(?:\.\d*)?|\.\d+")
_LONG_EXPONENT = re.compile(r"\d[eE][+-]?\d{4}")


def _reject_unsafe_expr(normalized: str) -> None:
    """Refuse what could run code: parse_expr/sympify evaluate the input via
    Python's eval() internally. Restricting local_dict to declared variable
    names (as this module already did) only stops BARE names from resolving
    to something dangerous via auto_symbol — it does nothing to stop
    ATTRIBUTE ACCESS on an already-resolved object. A Symbol instance is a
    real Python object, so "x.__class__.__mro__[1].__subclasses__()[N](...)"
    is valid Python syntax that walks the class hierarchy to reach e.g.
    subprocess.Popen and executes arbitrary shell commands — entirely inside
    SymPy's parse-time eval(), no further .doit()/evaluation needed. This is
    reachable from a plain chat message (math/tools keyword-triggered
    intent extraction has no sanitization) and from the sympy MCP tool the
    model can call directly. SymPy's own docs are explicit that
    sympify/parse_expr must never see untrusted input un-validated.

    Reject anything that isn't plainly arithmetic/algebraic before it ever
    reaches parse_expr: no "__" (blocks every dunder-attribute gadget chain),
    no "." outside a decimal number (blocks attribute access while still
    allowing "3.14"), no "[" or "]" (blocks subscripting), and a strict
    character allowlist as a second, independent layer against whatever this
    doesn't anticipate. Do not loosen this without a real threat-model
    review — this is the only thing standing between a chat message and
    eval() in the API process.
    """
    if "__" in normalized:
        raise SolveServiceError("Invalid expression")
    if _LONG_EXPONENT.search(normalized):  # 1e-1000000 is beyond any number a student means
        raise SolveServiceError("Number out of range")
    if "[" in normalized or "]" in normalized:
        raise SolveServiceError("Invalid expression")
    if "." in _DECIMAL_NUMBER.sub("", normalized):
        raise SolveServiceError("Invalid expression")
    if not _SAFE_EXPR_CHARS.match(normalized):
        raise SolveServiceError("Invalid expression")


def parse_expression(
    expr: str,
    variable_names: list[str] | None = None,
    *,
    real: bool = False,
    evaluate: bool = True,
):
    normalized = _normalize_expr(expr)
    if len(normalized) > get_settings().math_max_expr_length:
        raise SolveServiceError("Expression too long")
    _reject_unsafe_expr(normalized)
    local_dict = dict(_LOCALS)
    for name in [*(variable_names or []), *lone_quantity(expr)]:
        local_dict[name] = Symbol(name, real=True) if real else Symbol(name)
    reject_unknown_names(normalized, set(local_dict))
    if evaluate:
        reject_huge_numbers(normalized, local_dict, _TRANSFORMATIONS)
    try:
        parsed = parse_expr(
            normalized,
            local_dict=local_dict,
            transformations=_TRANSFORMATIONS,
            evaluate=evaluate,
        )
    except Exception as exc:
        raise SolveServiceError(f"Could not parse expression: {expr}") from exc
    if not isinstance(parsed, Basic | tuple):
        # A bare SymPy name parses to what it names (``Q``, ``CC``, ``limit``, the class ``O``)
        # and ``x == 1`` to a bool: neither is an expression. ``2, 3`` stays a tuple.
        raise SolveServiceError(f"Could not parse expression: {expr}")
    reject_unwritten_symbols(expr, parsed)
    return parsed


def _expr_needs_real_domain(*parts: str) -> bool:
    """Abs-value homework needs a real domain; SymPy rejects Abs(complex) solve."""
    return any("Abs(" in p or "abs(" in p for p in parts)


def parse_equation(data: EquationInput) -> tuple[Any, Any, list[Any]]:
    real = _expr_needs_real_domain(data.lhs, data.rhs)
    lhs = parse_expression(data.lhs, data.variables, real=real)
    rhs = parse_expression(data.rhs, data.variables, real=real)
    return Eq(lhs, rhs), lhs, rhs
