"""Rule-by-rule derivative lessons, each line checked against SymPy's ``diff``.

The rule for each part is read from the expression's structure (sum, constant
multiple, power, product, quotient, chain, and the standard functions). A line
shows the rule applied with SymPy-computed pieces and ends on the same verified
spelling the answer card uses. A line whose value is not SymPy's derivative is
dropped with the whole trace, so a lesson never states a derivative SymPy did
not confirm.
"""

from __future__ import annotations

from typing import Any

from sympy import Add, Mul, Symbol, cos, diff, exp, latex, log, sin, tan

from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.display import derivative_latex
from app.modules.math.solve.key_steps import KeyStep
from app.modules.math.solve.root_latex import expr_equal

_MAX_TERMS = 6

_POWER_REASON = r"$\frac{d}{dx} x^n = n x^{n-1}$"
_PRODUCT_REASON = r"$(uv)' = u'v + uv'$"
_QUOTIENT_REASON = r"$\left(\frac{u}{v}\right)' = \frac{u'v - uv'}{v^2}$"
_CHAIN_REASON = "the outside's derivative times the inside's derivative"
_BASE_LOG_REASON = r"$\frac{d}{dx} \log_{b} x = \frac{1}{x \ln b}$"

_ELEMENTARY = {
    sin: r"the derivative of $\sin x$ is $\cos x$",
    cos: r"the derivative of $\cos x$ is $-\sin x$",
    tan: r"the derivative of $\tan x$ is $\sec^2 x$",
    exp: r"$e^x$ is its own derivative",
    log: r"the derivative of $\ln x$ is $\frac{1}{x}$",
}


def _d(var: Any, body: Any) -> str:
    return rf"\frac{{d}}{{d{latex(var)}}}\left({latex(body)}\right)"


def _factor(expr: Any) -> str:
    """A factor in a product: parenthesize sums and negatives only."""
    tex = str(latex(expr))
    if expr.is_Add or expr.could_extract_minus_sign():
        return rf"\left({tex}\right)"
    return tex


def _product(left: Any, right: Any) -> str:
    """``left right`` without a pointless leading ``1``."""
    if left == 1:
        return _factor(right)
    if right == 1:
        return _factor(left)
    shown = _factor(right)
    if shown[:1].isdigit() or shown.startswith("-"):
        # ``x \cdot 2 x``: side by side, ``x 2 x`` reads as one number in the middle.
        return f"{_factor(left)} \\cdot {shown}"
    return f"{_factor(left)} {shown}"


def _base_log(term: Any) -> tuple[Any, Any] | None:
    """``ln(u) / ln(b)`` with a whole-number base: ``(u, b)``, the parse of ``log_b(u)``."""
    numerator, denominator = term.as_numer_denom()
    if getattr(denominator, "func", None) is not log or len(denominator.args) != 1:
        return None
    base = denominator.args[0]
    if getattr(numerator, "func", None) is not log or not (base.is_Integer and base > 1):
        return None
    return numerator.args[0], base


def _is_const(expr: Any, var: Any) -> bool:
    return var not in getattr(expr, "free_symbols", set())


def _equals_chain(lhs: str, shown: str, value: str) -> str:
    """``d/dx(...) = rule form = value``; the value once if the rule form is it."""
    if shown.replace(" ", "") == value.replace(" ", ""):
        return f"{lhs} = {value}"
    return f"{lhs} = {shown} = {value}"


def _term_step(term: Any, var: Any) -> KeyStep | None:
    """One rule application for one term. None when the rule is not recognized."""
    derivative = diff(term, var)
    value = derivative_latex(derivative)
    lhs = _d(var, term)
    coefficient, rest = term.as_coeff_Mul() if term.is_Mul else (1, term)
    if coefficient != 1 and not _is_const(rest, var):
        inner = _term_step(rest, var)
        inner_value = diff(rest, var)
        if inner is None or not expr_equal(coefficient * inner_value, derivative):
            return None
        return KeyStep(
            label=f"Keep ${latex(coefficient)}$ and differentiate ${latex(rest)}$",
            formula=_equals_chain(
                lhs, f"{latex(coefficient)} \\cdot {_factor(inner_value)}", value
            ),
            reason=inner.reason,
        )
    if term == var:
        return KeyStep(
            label=f"Power rule on ${latex(var)}$", formula=f"{lhs} = 1", reason=_POWER_REASON
        )
    if term.is_Pow and term.base == var and _is_const(term.exp, var):
        power = term.exp
        if not expr_equal(power * var ** (power - 1), derivative):
            return None
        shown = f"{latex(power)} {latex(var)}^{{{latex(power - 1)}}}"
        return KeyStep(
            label=f"Power rule on ${latex(term)}$",
            formula=_equals_chain(lhs, shown, value),
            reason=_POWER_REASON,
        )
    base_log = _base_log(term)
    if base_log is not None:
        inside, base = base_log
        d_inside = diff(inside, var)
        if not expr_equal(d_inside / (inside * log(base)), derivative):
            return None
        if inside == var:
            return KeyStep(
                label=f"Derivative of ${latex(term)}$",
                formula=f"{lhs} = {value}",
                reason=_BASE_LOG_REASON,
            )
        outer = rf"\frac{{1}}{{{_factor(inside)} \ln {latex(base)}}}"
        return KeyStep(
            label=f"Chain rule with inside ${latex(inside)}$",
            formula=_equals_chain(lhs, f"{outer} \\cdot {_factor(d_inside)}", value),
            reason=_BASE_LOG_REASON,
        )
    numerator, denominator = term.as_numer_denom()
    if denominator != 1 and not _is_const(denominator, var):
        du, dv = diff(numerator, var), diff(denominator, var)
        if not expr_equal((du * denominator - numerator * dv) / denominator**2, derivative):
            return None
        shown = (
            rf"\frac{{{_product(du, denominator)} - {_product(numerator, dv)}}}"
            rf"{{{_factor(denominator)}^{{2}}}}"
        )
        return KeyStep(
            label=(f"Quotient rule with $u = {latex(numerator)}$ and $v = {latex(denominator)}$"),
            formula=_equals_chain(lhs, shown, value),
            reason=_QUOTIENT_REASON,
        )
    if term.is_Mul:
        factors = [factor for factor in term.args if not _is_const(factor, var)]
        if len(factors) >= 2:
            u = factors[0]
            v = Mul(*[factor for factor in term.args if factor is not u])
            du, dv = diff(u, var), diff(v, var)
            if not expr_equal(du * v + u * dv, derivative):
                return None
            shown = f"{_product(du, v)} + {_product(u, dv)}"
            return KeyStep(
                label=f"Product rule with $u = {latex(u)}$ and $v = {latex(v)}$",
                formula=_equals_chain(lhs, shown, value),
                reason=_PRODUCT_REASON,
            )
    if term.is_Pow and _is_const(term.exp, var):
        inside, power = term.base, term.exp
        d_inside = diff(inside, var)
        if not expr_equal(power * inside ** (power - 1) * d_inside, derivative):
            return None
        outer = _factor(inside) if power - 1 == 1 else f"{_factor(inside)}^{{{latex(power - 1)}}}"
        shown = f"{latex(power)} {outer} \\cdot {_factor(d_inside)}"
        return KeyStep(
            label=f"Chain rule with inside ${latex(inside)}$",
            formula=_equals_chain(lhs, shown, value),
            reason=_CHAIN_REASON,
        )
    if term.is_Pow and _is_const(term.base, var):
        inside = term.exp
        d_inside = diff(inside, var)
        if not expr_equal(term * log(term.base) * d_inside, derivative):
            return None
        chain = "" if inside == var else f" \\cdot {_factor(d_inside)}"
        shown = f"{latex(term)} \\ln {_factor(term.base)}{chain}"
        if inside == var:
            return KeyStep(
                label=f"Exponential rule on ${latex(term)}$",
                formula=_equals_chain(lhs, shown, value),
                reason=r"$\frac{d}{dx} a^x = a^x \ln a$",
            )
        return KeyStep(
            label=f"Chain rule with inside ${latex(inside)}$",
            formula=_equals_chain(lhs, shown, value),
            reason=_CHAIN_REASON,
        )
    func: Any = getattr(term, "func", None)
    if func is not None and func in _ELEMENTARY and len(term.args) == 1:
        inside = term.args[0]
        placeholder = Symbol("QUQ")
        outer = diff(func(placeholder), placeholder).subs(placeholder, inside)
        d_inside = diff(inside, var)
        if not expr_equal(outer * d_inside, derivative):
            return None
        if inside == var:
            return KeyStep(
                label=f"Derivative of ${latex(term)}$",
                formula=f"{lhs} = {value}",
                reason=_ELEMENTARY[func],
            )
        return KeyStep(
            label=f"Chain rule with inside ${latex(inside)}$",
            formula=_equals_chain(lhs, f"{_factor(outer)} \\cdot {_factor(d_inside)}", value),
            reason=f"{_CHAIN_REASON}; {_ELEMENTARY[func]}",
        )
    return None


def derivative_key_steps(expr: Any, variable: str) -> list[KeyStep]:
    """First derivative of an explicit one-variable expression, one rule per line.

    Empty when a part's rule is not recognized, when there is only one step
    (the answer card is the lesson), or for more than six terms.
    """
    var = next((s for s in getattr(expr, "free_symbols", set()) if str(s) == variable), None)
    if var is None:
        return []
    derivative = diff(expr, var)
    terms = expr.as_ordered_terms() if isinstance(expr, Add) else [expr]
    if len(terms) > _MAX_TERMS:
        return []
    steps: list[KeyStep] = []
    if len(terms) > 1:
        from app.modules.math.solve.integral_steps import split_sum

        negatives = [term.could_extract_minus_sign() for term in terms]
        split = split_sum(
            [
                _d(var, -term if negative else term)
                for term, negative in zip(terms, negatives, strict=True)
            ],
            negatives,
        )
        steps.append(
            KeyStep(
                label="Differentiate term by term",
                formula=f"{_d(var, expr)} = {split}",
                reason="the derivative of a sum is the sum of the derivatives",
            )
        )
    for term in terms:
        if _is_const(term, var):
            steps.append(
                KeyStep(
                    label=f"Constant rule on ${latex(term)}$",
                    formula=f"{_d(var, term)} = 0",
                    reason="a constant does not change",
                )
            )
            continue
        step = _term_step(term, var)
        if step is None:
            return []
        steps.append(step)
    if len(terms) > 1:
        if not expr_equal(Add(*[diff(term, var) for term in terms]), derivative):
            return []
        steps.append(KeyStep(label="Add the results", formula=derivative_latex(derivative)))
    return steps


def derivative_trace(expr: str, variable: str) -> tuple[list[KeyStep], str | None]:
    """Parse, then trace: (steps, ``\\frac{d}{dx}(...)`` to show as the problem)."""
    from app.modules.math.solve.parse import parse_expression

    with sympy_decline() as declined:
        parsed = parse_expression(expr, [variable])
    if declined:
        return [], None
    steps = derivative_key_steps(parsed, variable)
    if not steps:
        return [], None
    var = next((s for s in parsed.free_symbols if str(s) == variable), Symbol(variable))
    return steps, _d(var, parsed)
