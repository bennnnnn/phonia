"""Simplify, factor and expand an expression."""

from __future__ import annotations

from sympy import expand, factor, latex

from app.modules.math.schemas import MathExprResult
from app.modules.math.solve.display import format_verified_latex
from app.modules.math.solve.parse import parse_expression
from app.modules.math.solve.real_reading import complex_without_cause, read_written
from app.modules.math.solve.simplest_form import simplest_form
from app.services.solving import SolveServiceError


def simplify_expression(expr: str, variable: str = "x") -> MathExprResult:
    # School-level simplification is over the reals unless the prompt names a
    # complex domain.  The real assumption is essential for identities such
    # as sqrt(x^2) = |x|; an unconstrained complex symbol leaves it unchanged.
    parse_expression(expr, [variable], real=True)  # the evaluated parse's checks
    # Read as written: evaluated, (-2.5)^(2/3) is already SymPy's complex principal value.
    written = parse_expression(expr, [variable], real=True, evaluate=False)
    result, book_latex = simplest_form(read_written(written))
    if complex_without_cause(written, result):
        raise SolveServiceError("could not verify: an odd root kept no real value")
    return MathExprResult(result=str(result), latex=book_latex or format_verified_latex(result))


def factor_expression(expr: str, variable: str = "x") -> MathExprResult:
    """Factor a polynomial/expression into a product of irreducible factors."""
    parsed = parse_expression(expr, [variable])
    result = factor(parsed)
    # General display simplification can expand a product again. Preserve
    # the requested factor form, including exact symbolic coefficients.
    return MathExprResult(result=str(result), latex=latex(result))


def expand_expression(expr: str, variable: str = "x") -> MathExprResult:
    """Expand a factored expression into a sum of terms."""
    parsed = parse_expression(expr, [variable])
    result = expand(parsed)
    return MathExprResult(result=str(result), latex=latex(result))
