"""How SymPy results print for students.

School notation reads a bare ``log`` as base 10 and writes the natural log as
``ln``. SymPy's ``log`` is the natural log, so it prints as ``\\ln`` (a printed
``\\log 10`` would read as 1), and a change of base ``ln(x)/ln(10)`` prints as
the written ``\\log_{10}(x)``.
"""

from __future__ import annotations

import re
from typing import Any

# SymPy's text for its natural log, the only ``log(`` it writes.
_SSTR_LOG = re.compile(r"(?<![A-Za-z_])log\(")


def _argument(printer: Any, arg: Any) -> str:
    """``\\ln 10`` for a whole number, as textbooks write it; brackets otherwise."""
    if arg.is_Integer and arg > 0:
        return f" {printer._print(arg)}"
    return rf"\left({printer._print(arg)}\right)"


def _written_base_log(printer: Any, expr: Any) -> str | None:
    """``c ln(u) / ln(b)`` with a whole-number base ``b`` → ``c \\log_{b}(u)``."""
    from sympy import log

    numerator, denominator = expr.as_numer_denom()
    if getattr(denominator, "func", None) is not log or len(denominator.args) != 1:
        return None
    base = denominator.args[0]
    if not (base.is_Integer and base > 1):
        return None
    coefficient, rest = numerator.as_coeff_Mul()
    if getattr(rest, "func", None) is not log or len(rest.args) != 1:
        return None
    body = rf"\log_{{{printer._print(base)}}}{_argument(printer, rest.args[0])}"
    if coefficient == 1:
        return body
    if coefficient == -1:
        return f"- {body}"
    return f"{printer._print(coefficient)} {body}"


def use_school_log_notation() -> None:
    """Print natural logs as ``\\ln`` and a change of base as ``\\log_{b}``.

    Idempotent; call at import from each module whose parser reads ``log``.
    """
    from sympy import Abs
    from sympy.printing.latex import LatexPrinter

    LatexPrinter._default_settings["ln_notation"] = True
    # ``\arctan x``, not ``\operatorname{atan} x``.
    LatexPrinter._default_settings["inv_trig_style"] = "full"
    original_mul = LatexPrinter._print_Mul
    original_log = LatexPrinter._print_log
    original_add = LatexPrinter._print_Add
    if getattr(original_mul, "school_log_notation", False):
        return

    def _print_add(self: Any, expr: Any, order: Any = None) -> str:
        # A number with a whole-number part leads with the other term:
        # ``e - 1``, ``\frac{\pi}{2} - 1``, not SymPy's ``-1 + e``.
        if not expr.free_symbols:
            terms = list(expr.as_ordered_terms())
            if len(terms) > 1 and terms[0].is_Rational and terms[0].is_negative:
                from sympy import Add

                rest = original_add(self, Add(*terms[1:]), order)
                return f"{rest} - {self._print(-terms[0])}"
        return str(original_add(self, expr, order))

    def _print_mul(self: Any, expr: Any, *args: Any, **kwargs: Any) -> str:
        written = _written_base_log(self, expr)
        return written if written is not None else original_mul(self, expr, *args, **kwargs)

    def _print_log(self: Any, expr: Any, exp: Any = None) -> str:
        arg = expr.args[0]
        name = r"\ln" if exp is None else rf"\ln^{{{exp}}}"
        if arg.func is Abs:
            # ``\ln|x|``, as written, not ``\ln(|x|)``.
            return rf"{name}\left|{self._print(arg.args[0])}\right|"
        if not (arg.is_Integer and arg > 0):
            return str(original_log(self, expr, exp))
        return f"{name}{_argument(self, arg)}"

    # A function takes attributes; mypy models none.
    _print_mul.school_log_notation = True  # type: ignore[attr-defined]
    # SymPy has no setting for either spelling, so its printer is patched once.
    setattr(LatexPrinter, "_print_Mul", _print_mul)  # noqa: B010 - a plain assignment fails mypy
    setattr(LatexPrinter, "_print_log", _print_log)  # noqa: B010 - a plain assignment fails mypy
    setattr(LatexPrinter, "_print_Add", _print_add)  # noqa: B010 - a plain assignment fails mypy


def school_text(expr: Any) -> str:
    """SymPy's plain text, with natural logs written ``ln``.

    ``sstr`` writes a natural log as ``log``, which the parser and the phone's
    graph resampler read as base 10. Text that is parsed or plotted again must
    keep its meaning.
    """
    from sympy import sstr

    return _SSTR_LOG.sub("ln(", str(sstr(expr)))
