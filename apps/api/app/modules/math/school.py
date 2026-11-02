"""School homework ops that are not 2D geometry or single-variable calc I."""

from __future__ import annotations

import logging
import math
import re
from fractions import Fraction
from math import gcd
from typing import Any

from sympy import (
    Add,
    Eq,
    Rational,
    S,
    Symbol,
    cos,
    cot,
    csc,
    diff,
    expand,
    expand_trig,
    factorial,
    ilcm,
    latex,
    nan,
    nsimplify,
    oo,
    pi,
    sec,
    series,
    simplify,
    sin,
    solve,
    solveset,
    tan,
    trigsimp,
    zoo,
)

from app.modules.math.schemas import MathExprResult
from app.modules.math.solve import SolveServiceError, parse_expression

logger = logging.getLogger(__name__)


UNDEFINED_LATEX = r"\text{undefined}"


def _defined_value_latex(value: Any) -> str:
    """The value, or ``\\text{undefined}`` for ``5/0``, ``0/0``, ``log 0`` and ``tan 90°``.

    SymPy writes those as complex infinity or NaN; neither is an answer a
    student can use. A real infinity is not undefined either, so it is not
    verified at all.
    """
    from app.modules.math.solve.display import format_verified_latex

    if value is nan or value is zoo or value.has(nan, zoo):
        return UNDEFINED_LATEX
    if value.has(oo, -oo):
        raise SolveServiceError("result is not a finite number")
    return format_verified_latex(value)


def evaluate_arithmetic(expr: str) -> str:
    parsed = parse_expression(expr, ["x"])
    if isinstance(parsed, tuple):
        raise SolveServiceError("not a numeric arithmetic expression")
    if parsed.free_symbols:
        raise SolveServiceError("arithmetic expression still has variables")
    from app.modules.math.solve.real_reading import complex_without_cause, read_written

    # ∛(-27) is -3, as everywhere in school algebra; SymPy's principal root is complex.
    # Read as written: evaluated, (-2.5)^(2/3) is already the principal value.
    written = parse_expression(expr, ["x"], evaluate=False)
    value = simplify(read_written(written))
    if complex_without_cause(written, value):
        raise SolveServiceError("could not verify: an odd root kept no real value")
    return _defined_value_latex(value)


def percent_of(rate: float, base: float) -> str:
    value = (rate / 100.0) * base
    return f"{value:g}"


def _format_school_number(value: float) -> str:
    if not math.isfinite(value):
        raise SolveServiceError("result is not a finite number")
    return f"{value:.12g}"


def percent_increase(base: float, rate: float) -> str:
    if not math.isfinite(base) or not math.isfinite(rate):
        raise SolveServiceError("percent change needs finite numbers")
    return _format_school_number(base * (1.0 + rate / 100.0))


def percent_decrease(base: float, rate: float) -> str:
    if not math.isfinite(base) or not math.isfinite(rate):
        raise SolveServiceError("percent change needs finite numbers")
    return _format_school_number(base * (1.0 - rate / 100.0))


def percent_is(part: float, whole: float) -> str:
    if not math.isfinite(part) or not math.isfinite(whole):
        raise SolveServiceError("percent-is needs finite numbers")
    if whole == 0:
        raise SolveServiceError("cannot take a percent of zero")
    return _format_school_number((part / whole) * 100.0)


def split_ratio(total: float, parts: list[float]) -> str:
    if not math.isfinite(total) or any(not math.isfinite(part) for part in parts):
        raise SolveServiceError("ratio split needs finite numbers")
    if len(parts) < 2:
        raise SolveServiceError("ratio split needs at least two parts")
    if any(part < 0 for part in parts):
        raise SolveServiceError("ratio parts cannot be negative")
    weight = sum(parts)
    if weight <= 0:
        raise SolveServiceError("ratio parts must sum to more than zero")
    shares = [total * part / weight for part in parts]
    return ":".join(_format_school_number(share) for share in shares)


def _term_fraction(value: float) -> Fraction:
    if not math.isfinite(value):
        raise SolveServiceError("sequence terms must be finite")
    return Fraction(str(value))


def _progression(
    terms: list[float],
) -> tuple[str, Fraction, Fraction] | None:
    """Prefer AP when a list is both arithmetic and geometric."""
    if len(terms) < 2:
        return None
    fracs = [_term_fraction(term) for term in terms]
    first = fracs[0]
    delta = fracs[1] - fracs[0]
    if all(fracs[i] - fracs[i - 1] == delta for i in range(1, len(fracs))):
        return ("ap", first, delta)
    if any(prev == 0 for prev in fracs[:-1]):
        return None
    ratio = fracs[1] / fracs[0]
    if all(fracs[i] / fracs[i - 1] == ratio for i in range(1, len(fracs))):
        return ("gp", first, ratio)
    return None


def is_ap_or_gp(terms: list[float]) -> bool:
    try:
        return _progression(terms) is not None
    except SolveServiceError:
        return False


def sequence_nth(terms: list[float], n: int) -> str:
    if n < 1:
        raise SolveServiceError("sequence index must be a positive term number")
    kind = _progression(terms)
    if kind is None:
        raise SolveServiceError("list is not an arithmetic or geometric sequence")
    op, first, step = kind
    if op == "ap":
        value = first + (n - 1) * step
    else:
        value = first * (step ** (n - 1))
    return _format_school_number(float(value))


def sequence_sum(terms: list[float], n: int) -> str:
    if n < 1:
        raise SolveServiceError("sequence length must be a positive term count")
    kind = _progression(terms)
    if kind is None:
        raise SolveServiceError("list is not an arithmetic or geometric sequence")
    op, first, step = kind
    if op == "ap":
        value = n * (2 * first + (n - 1) * step) / 2
    elif step == 1:
        value = first * n
    else:
        value = first * (step**n - 1) / (step - 1)
    return _format_school_number(float(value))


def simple_interest(principal: float, rate: float, years: int) -> str:
    if not math.isfinite(principal) or not math.isfinite(rate) or years < 1:
        raise SolveServiceError("interest needs a finite principal, rate, and positive years")
    return _format_school_number(principal * (rate / 100.0) * years)


def compound_interest(principal: float, rate: float, years: int) -> str:
    if not math.isfinite(principal) or not math.isfinite(rate) or years < 1:
        raise SolveServiceError("interest needs a finite principal, rate, and positive years")
    amount = principal * ((1.0 + rate / 100.0) ** years)
    return _format_school_number(amount - principal)


def compound_amount(principal: float, rate: float, years: int) -> str:
    if not math.isfinite(principal) or not math.isfinite(rate) or years < 1:
        raise SolveServiceError("interest needs a finite principal, rate, and positive years")
    return _format_school_number(principal * ((1.0 + rate / 100.0) ** years))


def _format_school_set(values: set[Fraction]) -> str:
    parts = [_format_school_number(float(value)) for value in sorted(values)]
    return "{" + ", ".join(parts) + "}"


def set_union(left: list[float], right: list[float]) -> str:
    return _format_school_set(_fraction_set(left) | _fraction_set(right))


def set_intersection(left: list[float], right: list[float]) -> str:
    return _format_school_set(_fraction_set(left) & _fraction_set(right))


def set_difference(left: list[float], right: list[float]) -> str:
    return _format_school_set(_fraction_set(left) - _fraction_set(right))


def work_together(hours_a: float, hours_b: float) -> str:
    if hours_a <= 0 or hours_b <= 0:
        raise SolveServiceError("work-together needs two positive times")
    return _format_school_number((hours_a * hours_b) / (hours_a + hours_b))


def mixture_percent(vol_a: float, pct_a: float, vol_b: float, pct_b: float) -> str:
    total = vol_a + vol_b
    if vol_a < 0 or vol_b < 0 or total <= 0:
        raise SolveServiceError("mixture needs two non-negative volumes")
    return _format_school_number((vol_a * pct_a + vol_b * pct_b) / total)


def twice_as_many(total: float) -> str:
    if total <= 0:
        raise SolveServiceError("twice-as-many needs a positive total")
    small = total / 3.0
    large = 2.0 * total / 3.0
    return f"{_format_school_number(small)} and {_format_school_number(large)}"


def analyze_identity(lhs: str, rhs: str) -> tuple[bool, str | None, str | None]:
    """Identity truth, equality set, and a small exact counterexample."""
    from app.modules.math.solve.discrete import guess_variables

    names = list(dict.fromkeys([*guess_variables(f"{lhs} {rhs}"), "theta", "x", "y", "t"]))
    left = parse_expression(lhs, names, real=True)
    right = parse_expression(rhs, names, real=True)
    difference = simplify(trigsimp(expand_trig(expand(left - right))))
    if difference == 0:
        return True, None, None
    variables = sorted(left.free_symbols | right.free_symbols, key=str)
    if len(variables) != 1:
        return False, None, None
    variable = variables[0]
    condition: str | None = None
    try:
        condition = latex(solveset(Eq(left, right), variable, domain=S.Reals))
    except Exception as exc:
        logger.debug("Could not solve identity equality set", exc_info=exc)
    counterexample: str | None = None
    for candidate in (-2, -1, 0, 1, 2):
        try:
            left_value = simplify(left.subs(variable, candidate))
            right_value = simplify(right.subs(variable, candidate))
            if left_value.is_finite is False or right_value.is_finite is False:
                continue
            if simplify(left_value - right_value) != 0:
                counterexample = (
                    rf"{latex(variable)}={candidate}:\;"
                    rf"\text{{left}}={latex(left_value)},\;\text{{right}}={latex(right_value)}"
                )
                break
        except Exception as exc:
            logger.debug("Could not test identity counterexample", exc_info=exc)
            continue
    return False, condition, counterexample


def _fraction_set(values: list[float]) -> set[Fraction]:
    return {_term_fraction(value) for value in values}


def simplify_ratio(a: float, b: float) -> str:

    if not math.isfinite(a) or not math.isfinite(b) or (a == 0 and b == 0):
        raise SolveServiceError("Ratio needs finite values that are not both zero")
    left, right = Rational(str(a)), Rational(str(b))
    scale = ilcm(left.q, right.q)
    numerator, denominator = int(left * scale), int(right * scale)
    divisor = gcd(numerator, denominator)
    return f"{numerator // divisor}:{denominator // divisor}"


def evaluate_trig_degrees(func: str, degrees: float) -> str:
    table = {"sin": sin, "cos": cos, "tan": tan, "sec": sec, "csc": csc, "cot": cot}
    if func not in table:
        raise SolveServiceError(f"unsupported trig function {func}")
    return _defined_value_latex(simplify(table[func](nsimplify(degrees) * pi / 180)))


def coord_distance(x1: float, y1: float, x2: float, y2: float) -> str:
    """``5``, or ``2 \\sqrt{2} \\approx 2.828``: a root shown to places is said to be one."""
    from sympy import latex, nsimplify, sqrt

    d = sqrt((nsimplify(x2) - nsimplify(x1)) ** 2 + (nsimplify(y2) - nsimplify(y1)) ** 2)
    if d.is_Rational:
        return _plain_number(float(d))
    return rf"{latex(d)} \approx {float(d):.4g}"


def _plain_number(value: float) -> str:
    """A terminating value as written, never in e-notation."""
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def coord_midpoint(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"({(x1 + x2) / 2:g}, {(y1 + y2) / 2:g})"


def coord_slope(x1: float, y1: float, x2: float, y2: float) -> str:
    if x2 == x1:
        return r"\text{undefined}"
    from sympy import latex, nsimplify

    # 1/3 is \frac{1}{3}, not a rounded 0.333333.
    slope = (nsimplify(y2) - nsimplify(y1)) / (nsimplify(x2) - nsimplify(x1))
    return str(latex(slope))


def vector_magnitude(vec: list[float]) -> str:
    mag = math.sqrt(sum(c * c for c in vec))
    return f"{mag:g}"


def vector_dot(a: list[float], b: list[float]) -> str:
    if len(a) != len(b):
        raise SolveServiceError("dot product needs matching dimension")
    return f"{sum(x * y for x, y in zip(a, b, strict=True)):g}"


def vector_cross(a: list[float], b: list[float]) -> str:
    if len(a) == 2:
        a = [a[0], a[1], 0.0]
        b = [b[0], b[1], 0.0]
    if len(a) != 3 or len(b) != 3:
        raise SolveServiceError("cross product needs 2D or 3D vectors")
    cx = a[1] * b[2] - a[2] * b[1]
    cy = a[2] * b[0] - a[0] * b[2]
    cz = a[0] * b[1] - a[1] * b[0]
    return f"({cx:g}, {cy:g}, {cz:g})"


def binomial_pmf(n: int, k: int, p: float) -> str:
    if not (0 <= k <= n) or not (0.0 <= p <= 1.0):
        raise SolveServiceError("invalid binomial parameters")
    coeff = int(factorial(n) / (factorial(k) * factorial(n - k)))
    value = coeff * (p**k) * ((1.0 - p) ** (n - k))
    return f"{value:g}"


def expected_value(values: list[float], probs: list[float] | None) -> str:
    if not values:
        raise SolveServiceError("expected value needs data")
    if probs is None:
        return f"{sum(values) / len(values):g}"
    if len(probs) != len(values):
        raise SolveServiceError("values and probabilities must match")
    if any(probability < 0 or probability > 1 for probability in probs):
        raise SolveServiceError("probabilities must be between 0 and 1")
    if not math.isclose(sum(probs), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise SolveServiceError("probabilities must sum to 1")
    return f"{sum(v * p for v, p in zip(values, probs, strict=True)):g}"


_LETTER_TIMES_I = re.compile(r"(?<![A-Za-z_\\])([a-hk-oq-z])i(?![A-Za-z_0-9(])")


def _imaginary_unit_to_sympy(expr: str) -> str:
    """Map standalone ``i``/``j`` to SymPy ``I`` without rewriting ``sin``/``pi``.

    A naive ``str.replace("i", "I")`` turns ``sin`` into ``sIn`` and ``pi``
    into ``pI``. Only replace when the letter is not inside an identifier.
    """
    # ``a + bi``: one letter written against i is a product with it (never ``pi``).
    expr = _LETTER_TIMES_I.sub(r"\1*i", expr)
    out: list[str] = []
    n = len(expr)
    for idx, ch in enumerate(expr):
        if ch in ("i", "j"):
            prev_letter = idx > 0 and expr[idx - 1].isalpha()
            next_letter = idx + 1 < n and expr[idx + 1].isalpha()
            if not prev_letter and not next_letter:
                out.append("I")
                continue
        out.append(ch)
    return "".join(out)


def evaluate_complex(expr: str, *, expanded: bool = False) -> str:
    """The value in complex numbers; an odd root of a negative number has two readings there
    (-2 or the principal 1 + √3 i), so it is declined."""
    from app.modules.math.solve.complex_form import a_plus_bi
    from app.modules.math.solve.real_reading import (
        odd_root_of_a_negative_number,
        real_odd_roots,
    )

    sympy_text = _imaginary_unit_to_sympy(expr)
    written = parse_expression(sympy_text, ["x"])
    if odd_root_of_a_negative_number(parse_expression(sympy_text, ["x"], evaluate=False)):
        # ∛(-8) asked in complex numbers is -2 or the principal 1 + √3 i: no one value.
        raise SolveServiceError(
            "could not verify: an odd root of a negative number has two values in complex numbers"
        )
    parsed = real_odd_roots(written)
    value = expand(parsed) if expanded else simplify(parsed)
    if not getattr(value, "free_symbols", None) and _defined_value_latex(value) == UNDEFINED_LATEX:
        return UNDEFINED_LATEX
    return a_plus_bi(value) or str(latex(value))


def restates_complex(expr: str, answer: str) -> bool:
    """The complex answer is the question as typed, so it certifies nothing."""
    from app.modules.math.solve.complex_form import restates

    return restates(_imaginary_unit_to_sympy(expr), answer)


def taylor_series(
    expr: str, variable: str, point: str, order: int, *, nonzero_terms: int | None = None
) -> MathExprResult:
    """The Taylor polynomial to ``order``, or with ``nonzero_terms`` terms.

    "cos x to 4 terms" means four non-zero terms (up to x^6), not order 3. A
    series about 0 is written in ascending powers, as textbooks write it.
    """
    parsed = parse_expression(expr, [variable])
    var = Symbol(variable)
    pt = parse_expression(point, [variable])
    out = series(parsed, var, pt, order + 1).removeO()
    if nonzero_terms is not None:
        for longer in range(nonzero_terms, 31):
            out = series(parsed, var, pt, longer + 1).removeO()
            if len(Add.make_args(out)) >= nonzero_terms:
                break
        terms = sorted(Add.make_args(out), key=lambda term: term.as_poly(var).degree())
        out = Add(*terms[:nonzero_terms])
    tex = str(latex(out, order="rev-lex")) if pt == 0 else str(latex(out))
    return MathExprResult(result=tex, latex=tex, solved=True)


def partial_derivative(expr: str, variable: str) -> MathExprResult:
    parsed = parse_expression(expr, [variable])
    out = diff(parsed, Symbol(variable))
    tex = str(latex(out))
    return MathExprResult(result=tex, latex=tex, solved=True)


def critical_points(expr: str, variable: str = "x") -> MathExprResult:
    """Solve ``f'(x) = 0`` for polynomial/elementary ``f``."""
    if not (expr or "").strip():
        raise SolveServiceError("could not find critical points")
    sym = Symbol(variable)
    parsed = parse_expression(expr, [variable])
    deriv = diff(parsed, sym)
    try:
        sols = solve(deriv, sym)
    except Exception as exc:
        raise SolveServiceError("could not find critical points") from exc
    if not sols:
        tex = r"\emptyset"
    else:
        tex = ", ".join(str(latex(s)) for s in sols)
    return MathExprResult(result=str(sols), latex=tex, solved=True)


def evaluate_trig_expr(expr: str) -> str:
    parsed = parse_expression(expr.replace("\u00b0", "*pi/180"), ["x"])
    if parsed.free_symbols:
        raise SolveServiceError("trig evaluation still has variables")
    return _defined_value_latex(simplify(parsed))
