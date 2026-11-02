"""Verified affine half-planes; nonlinear regions remain unsupported."""

from __future__ import annotations

import math
import re
from typing import Literal, cast

from sympy import Expr, Poly, Symbol
from sympy.polys.polyerrors import PolynomialError

from app.modules.math.schemas import GraphBlockSpec
from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy
from app.modules.math.solve.parse import SolveServiceError, parse_expression


def affine_inequality_graph_spec(
    expr: str, *, x_min: float = -10, x_max: float = 10
) -> GraphBlockSpec | None:
    """Verify a two-variable linear relation without dropping its domain.

    Parsing unevaluated first keeps ``x/x`` from cancelling to 1 before
    the polynomial check. Number lines retain ownership of one-variable
    inequalities; unknown parameters and nonlinear boundaries stay out.
    """
    if not expr or len(expr) > 256:
        return None
    cleaned = normalize_latex_to_sympy(expr).replace("\u2264", "<=").replace("\u2265", ">=")
    parts = re.split(r"(<=|>=|<|>)", cleaned)
    if len(parts) != 3:
        return None
    lhs, comparator, rhs = parts
    x, y = Symbol("x", real=True), Symbol("y", real=True)
    try:
        left = parse_expression(lhs, ["x", "y"], real=True, evaluate=False)
        right = parse_expression(rhs, ["x", "y"], real=True, evaluate=False)
        if not isinstance(left, Expr) or not isinstance(right, Expr):
            return None
        if left.free_symbols | right.free_symbols != {x, y}:
            return None
        if not left.is_polynomial(x, y) or not right.is_polynomial(x, y):
            return None
        boundary = Poly(left - right, x, y)
        if boundary.total_degree() != 1:
            return None
        exact = [
            boundary.coeff_monomial(x),
            boundary.coeff_monomial(y),
            -boundary.coeff_monomial(1),
        ]
        coefficients = [float(value) for value in exact]
        if any(not math.isfinite(value) for value in coefficients):
            return None
        # Underflow must not erase a real term and change the shaded side.
        if any(
            original != 0 and value == 0
            for original, value in zip(exact, coefficients, strict=True)
        ):
            return None
        a, b, c = coefficients
        return GraphBlockSpec(
            type="inequality",
            expr=cleaned.strip(),
            a=a,
            b=b,
            c=c,
            comparator=cast(Literal["<", "<=", ">", ">="], comparator),
            x_min=x_min,
            x_max=x_max,
            y_min=-10,
            y_max=10,
        )
    except (SolveServiceError, PolynomialError, TypeError, ValueError, OverflowError):
        return None
