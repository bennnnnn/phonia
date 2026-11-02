"""Integrals: which integral to evaluate, improper results, and how the working reads."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathExprResult, MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.integral_steps import integral_trace
from app.modules.math.solve.key_steps import KeyStep
from app.modules.math.tools.calculus_outcome import infinite_integral_note, undefined_integral_note
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout


def _integral(
    intent: MathIntent, expr: str, settings: Settings
) -> tuple[MathExprResult, list[KeyStep], str | None, str | None]:
    """Triple, double, definite or indefinite; an indefinite one also gets its trace."""
    if (
        intent.integral_lower is not None
        and intent.integral_upper is not None
        and intent.integral_lower2 is not None
        and intent.integral_upper2 is not None
        and intent.integral_lower3 is not None
        and intent.integral_upper3 is not None
    ):
        out = math_solve.integrate_triple(
            expr,
            intent.variable,
            intent.integral_lower,
            intent.integral_upper,
            intent.variable2 or "y",
            intent.integral_lower2,
            intent.integral_upper2,
            intent.variable3 or "z",
            intent.integral_lower3,
            intent.integral_upper3,
        )
    elif (
        intent.integral_lower is not None
        and intent.integral_upper is not None
        and intent.integral_lower2 is not None
        and intent.integral_upper2 is not None
    ):
        out = math_solve.integrate_double(
            expr,
            intent.variable,
            intent.integral_lower,
            intent.integral_upper,
            intent.variable2 or "y",
            intent.integral_lower2,
            intent.integral_upper2,
        )
    elif intent.integral_lower is not None and intent.integral_upper is not None:
        out = math_solve.integrate_definite(
            expr,
            intent.variable,
            intent.integral_lower,
            intent.integral_upper,
        )
    else:
        out = math_solve.integrate_expression(expr, intent.variable)
        trace, given, checked_answer = integral_trace(
            expr[: settings.math_max_expr_length], intent.variable
        )
        return out, trace, given, checked_answer
    return out, [], None, None


def _improper_integral_block(out: MathExprResult, lines: list[str]) -> VerifiedMathBlock | None:
    undefined_note = undefined_integral_note(out.result)
    if undefined_note is not None:
        lines.append(undefined_note)
        return VerifiedMathBlock(
            text="\n".join(lines),
            direct_reply=(
                "This ordinary improper integral does not converge. "
                "A Cauchy principal value is a separate convention and was not requested."
            ),
        )
    infinite_note = infinite_integral_note(out.result)
    if infinite_note is not None:
        lines.append(infinite_note)
        direction = "+\u221e" if out.result == "oo" else "\u2212\u221e"
        message = (
            f"This improper integral diverges to {direction}; "
            "it does not converge to a finite value."
        )
        return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
    return None


def _is_log_over_x_integral(expr: str, variable: str) -> bool:
    from sympy import Expr, Symbol, log, simplify

    sym = Symbol(variable, real=True)
    with sympy_decline():
        parsed = math_solve.parse_expression(expr, [variable], real=True)
        return isinstance(parsed, Expr) and bool(simplify(parsed - 1 / (sym * log(sym))) == 0)
    return False


def _log_over_x_reply(var: str, answer: str) -> str:
    return render_workout(
        Workout(
            find=(math_line(f"\\int \\frac{{1}}{{{var} \\ln({var})}}\\,d{var}"),),
            steps=(
                math_line(
                    f"u = \\ln({var}), \\quad du = \\frac{{1}}{{{var}}}\\,d{var}",
                    "substitute",
                ),
                math_line(r"\int \frac{1}{u}\,du = \ln|u| + C", "integrate"),
                math_line(answer, "substitute back"),
                math_line(f"{var} > 0,\\; {var} \\ne 1", "domain for real values"),
            ),
        ),
        answer,
    )


def _definite_integral_reply(intent: MathIntent, expr: str, answer: str) -> str:
    from sympy import latex

    parsed = math_solve.parse_expression(expr, [intent.variable], real=True)
    integrand = rf"\left({latex(parsed)}\right)" if parsed.is_Add else latex(parsed)
    low_tex, high_tex = _bound_tex(intent.integral_lower), _bound_tex(intent.integral_upper)
    integral = f"\\int_{{{low_tex}}}^{{{high_tex}}} {integrand}\\,d{intent.variable}"
    unbounded = _unbounded_at_an_endpoint(parsed, intent)
    worked = None if unbounded else _fundamental_theorem_working(intent, parsed, integral)
    note = "evaluate as a limit at the endpoint" if unbounded else "evaluate"
    return render_workout(
        worked
        or Workout(
            find=(math_line(integral),),
            steps=(math_line(f"{integral} = {answer}", note),),
        ),
        answer,
    )


def _bound_tex(bound: object) -> str:
    """``pi`` as ``\\pi``; an unreadable bound stays as written."""
    from sympy import latex

    with sympy_decline():
        return str(latex(math_solve.parse_expression(str(bound), [], real=True)))
    return str(bound)


def _fundamental_theorem_working(intent: MathIntent, parsed: Any, integral: str) -> Workout | None:
    """``∫_0^3 x² dx = [x³/3]_0^3 = 9 - 0``: the antiderivative, then F(b) - F(a)."""
    from sympy import Expr, Integral, Symbol, integrate, latex, oo, simplify, zoo

    symbol = next(
        (s for s in parsed.free_symbols if str(s) == intent.variable), Symbol(intent.variable)
    )
    with sympy_decline() as declined:
        low = math_solve.parse_expression(str(intent.integral_lower), [], real=True)
        high = math_solve.parse_expression(str(intent.integral_upper), [], real=True)
        if any(not isinstance(bound, Expr) or bound.has(oo, -oo, zoo) for bound in (low, high)):
            return None
        from app.modules.math.solve.calculus import _absolute_logs

        antiderivative = _absolute_logs(integrate(parsed, symbol), parsed, symbol)
        if antiderivative.has(Integral):
            return None
        at_high = simplify(antiderivative.subs(symbol, high))
        at_low = simplify(antiderivative.subs(symbol, low))
        value = simplify(math_solve.definite_integral(parsed, symbol, low, high))
        if not (at_high.is_finite and at_low.is_finite) or simplify(at_high - at_low - value) != 0:
            return None
    if declined:
        return None
    var = latex(symbol)
    low_tex = (
        rf"\left({latex(at_low)}\right)" if at_low.could_extract_minus_sign() else latex(at_low)
    )
    return Workout(
        find=(math_line(integral),),
        formula=(
            math_line(r"\int_{a}^{b} f(x)\,dx = F(b) - F(a)", "Fundamental theorem of calculus"),
        ),
        substitution=(
            math_line(f"F({var}) = {latex(antiderivative)}", "antiderivative"),
            math_line(
                rf"{integral} = \left[{latex(antiderivative)}\right]"
                rf"_{{{latex(low)}}}^{{{latex(high)}}}"
            ),
            math_line(
                " = ".join(
                    ["", *dict.fromkeys([f"{latex(at_high)} - {low_tex}", latex(value)])]
                ).strip(),
                "evaluate at the limits",
            ),
        ),
    )


def _unbounded_at_an_endpoint(parsed: Any, intent: MathIntent) -> bool:
    """``ln(x)`` on ``[0, 1]``: the integral is a limit at 0, not a plain value."""
    from sympy import Symbol, nan, zoo

    symbol = next(
        (s for s in parsed.free_symbols if str(s) == intent.variable), Symbol(intent.variable)
    )
    for bound in (intent.integral_lower, intent.integral_upper):
        with sympy_decline() as declined:
            point = math_solve.parse_expression(str(bound), [], real=True)
            value = parsed.subs(symbol, point)
        if declined:  # an unreadable bound is not evidence either way
            continue
        if value in (zoo, nan) or getattr(value, "is_finite", True) is False:
            return True
    return False
