"""Taylor, partial, and ODE extractor plus the calculus block extension."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.core.config import Settings
from app.modules.math import match as mtm
from app.modules.math import school as math_school
from app.modules.math.ode import solve_ode
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.workout import Workout, math_line, note_from_label, render_workout, text_line

_ODE_START_RE = re.compile(r"dy\s*/\s*dx|d\^?2\s*y\s*/\s*dx\^?2|[A-Za-z]'")
_ODE_INITIAL_RE = re.compile(
    r"\b([A-Za-z])\s*\(\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*\)\s*=\s*"
    r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))\b"
)


def _ode_equation(cleaned: str) -> str | None:
    """Span from the first derivative mark through the rhs. Linear scan.

    Accepts the bare first-order forms (``dy/dx = 2y``) and the general linear
    ones (``y'' + y = 0``, ``y'' + 3y' + 2y = 0``). Everything between the
    derivative and the ``=`` must be math: ``Find dy/dx if y = x^2`` is a
    derivative ask, not an ODE, and the word ``if`` is what says so.
    """
    from app.modules.math.tools.request_text import strip_trailing_filler

    match = _ODE_START_RE.search(cleaned)
    if match is None:
        return None
    rest = cleaned[match.start() :]
    eq_at = rest.find("=")
    if eq_at == -1:
        return None
    between = rest[:eq_at]
    for token in between.split():
        word = token.strip(".,?!:;()[]").lower()
        if word.isalpha() and len(word) >= 2:
            return None
    return strip_trailing_filler(rest)


def _extract_taylor_or_ode(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    taylor_ok = (
        "taylor of " in lower or "maclaurin" in lower or ("taylor" in lower and "series" in lower)
    )
    if taylor_ok:
        expr = mtm.graph_expr(cleaned) or cleaned
        n = mtm.number_after(cleaned, "order") or mtm.number_after(cleaned, "degree") or 5
        # "up to x^3" is order 3; "the first 4 terms" is order 3.
        power = re.search(
            r"\b(?:up\s+to|through|as\s+far\s+as)\s+(?:and\s+including\s+)?(?:the\s+)?"
            r"x\s*\^\s*\{?(\d+)\}?",
            lower,
        )
        terms = re.search(r"\b(?:first\s+|to\s+)?(\d+)\s+(?:non-?zero\s+)?terms\b", lower)
        term_count: int | None = None
        if power is not None:
            n = int(power.group(1))
        elif terms is not None and 1 <= int(terms.group(1)) <= 12:
            term_count = int(terms.group(1))
        point = "0"
        if "maclaurin" not in lower and "at " in lower:
            pt = mtm.number_after(cleaned, "at")
            if pt is not None:
                point = f"{pt:g}"
        # pull expr after "of "
        idx = lower.find(" of ")
        if idx != -1:
            rest = cleaned[idx + 4 :]
            for stop in (
                " at ",
                " order",
                " degree",
                " around",
                " up to",
                " through ",
                " as far as",
                " to ",
                ",",
                " first ",
            ):
                sidx = rest.lower().find(stop)
                if sidx != -1:
                    rest = rest[:sidx]
            expr = rest.strip()
        from app.modules.math.tools.expr_rewrite import math_expr_or_none

        # Leftover words ("up to") would become variables in the series.
        if math_expr_or_none(expr) is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="taylor",
            expr=expr,
            taylor_n=int(n),
            # "to 4 terms": four non-zero terms, however high the order.
            combo_n=term_count,
            limit_point=point,
            variable="x",
        )
    if "partial" in lower and (
        "partial of " in lower
        or "partial derivative" in lower
        or " wrt" in lower
        or "with respect to" in lower
    ):
        var = "x"
        if "wrt" in lower:
            after = cleaned.lower().find("wrt")
            rest = cleaned[after + 3 :].strip()
            if rest:
                var = rest[0]
        elif "with respect to" in lower:
            after = lower.find("with respect to")
            rest = cleaned[after + len("with respect to") :].strip()
            if rest:
                var = rest[0]
        idx = lower.find(" of ")
        expr = cleaned[idx + 4 :] if idx != -1 else cleaned
        for stop in (" wrt", " with respect"):
            sidx = expr.lower().find(stop)
            if sidx != -1:
                expr = expr[:sidx]
        return MathIntent(
            kind="calculus",
            operation="partial",
            expr=expr.strip(),
            variable=var,
        )
    if "dy/dx" in lower or "'" in cleaned or "dsolve" in lower:
        initial = _ODE_INITIAL_RE.search(cleaned)
        ode_source = cleaned
        initial_x: str | None = None
        initial_y: str | None = None
        if initial is not None:
            initial_x, initial_y = initial.group(2), initial.group(3)
            ode_source = cleaned[: initial.start()].rstrip(" ,;.")
            for suffix in (" with", " where", " and"):
                if ode_source.lower().endswith(suffix):
                    ode_source = ode_source[: -len(suffix)].rstrip()
                    break
        ode_eq = _ode_equation(ode_source)
        if ode_eq is None:
            return None
        return MathIntent(
            kind="calculus",
            operation="dsolve",
            expr=ode_eq,
            variable="x",
            initial_x=initial_x,
            initial_y=initial_y,
        )
    return None


def _average_value_working(intent: MathIntent, answer: str) -> str | None:
    """``\\frac{1}{b - a}\\int_a^b f\\,dx``, the integral worked, then the mean."""
    from sympy import Symbol, integrate, latex, simplify

    from app.modules.math import solve as math_solve

    variable = intent.variable or "x"
    with sympy_decline() as declined:
        expr = math_solve.parse_expression(intent.expr or "", [variable])
        low = math_solve.parse_expression(str(intent.integral_lower), [])
        high = math_solve.parse_expression(str(intent.integral_upper), [])
    if declined:
        return None
    x = Symbol(variable)
    if isinstance(expr, tuple) or expr.free_symbols - {x} or high == low:
        return None
    antiderivative = integrate(expr, x)
    total = simplify(antiderivative.subs(x, high) - antiderivative.subs(x, low))
    width = simplify(high - low)
    lo, hi = latex(low), latex(high)
    integral = rf"\int_{{{lo}}}^{{{hi}}} {latex(expr)}\,d{variable}"
    return render_workout(
        Workout(
            given=(math_line(f"f({variable}) = {latex(expr)}"), math_line(rf"[{lo}, {hi}]")),
            find=(math_line(r"\bar{f}", "the average value"),),
            formula=(
                math_line(
                    rf"\bar{{f}} = \frac{{1}}{{b - a}}\int_{{a}}^{{b}} f({variable})\,d{variable}",
                    "Average value of a function",
                ),
            ),
            substitution=(
                math_line(
                    rf"{integral} = \left[{latex(antiderivative)}\right]_{{{lo}}}^{{{hi}}}"
                    rf" = {latex(total)}"
                ),
                math_line(rf"\bar{{f}} = \frac{{1}}{{{latex(width)}}} \times {latex(total)}"),
            ),
        ),
        answer,
    )


_DY_DX = re.compile(r"^\s*dy\s*/\s*dx\s*=\s*(?P<rhs>[^=]+)$", re.IGNORECASE)


def _direct_integration_working(intent: MathIntent) -> tuple[str, str] | None:
    """``dy/dx = f(x)``: integrate both sides, then the initial value fixes C.

    Returns the working and the answer, ``y = x^{2} + 1`` (or ``... + C``).
    """
    from sympy import Eq, Symbol, integrate, latex, solve, sympify

    from app.modules.math import solve as math_solve

    match = _DY_DX.match(intent.expr or "")
    if match is None:
        return None
    variable = intent.variable or "x"
    with sympy_decline() as declined:
        rate = math_solve.parse_expression(match["rhs"], [variable])
    if declined:
        return None
    x = Symbol(variable)
    if isinstance(rate, tuple) or rate.free_symbols - {x}:
        return None
    from app.modules.math.tools.school.function_value import _substituted_tex

    antiderivative = integrate(rate, x)
    integrand = rf"\left({latex(rate)}\right)" if rate.is_Add else latex(rate)
    given = [math_line(rf"\frac{{dy}}{{d{variable}}} = {latex(rate)}")]
    steps = [
        math_line(
            rf"y = \int {integrand}\,d{variable} = {latex(antiderivative)} + C",
            "integrate both sides",
        )
    ]
    answer = f"y = {latex(antiderivative)} + C"
    if intent.initial_x is not None and intent.initial_y is not None:
        x0, y0 = sympify(intent.initial_x), sympify(intent.initial_y)
        c = Symbol("C")
        constant = solve(Eq(antiderivative.subs(x, x0) + c, y0), c)
        if len(constant) != 1:
            return None
        given.append(math_line(f"y({latex(x0)}) = {latex(y0)}"))
        steps.append(
            math_line(
                rf"y({latex(x0)}) = {_substituted_tex(antiderivative, variable, x0)} + C = "
                rf"{latex(y0)} \Rightarrow C = {latex(constant[0])}",
                "use the initial value",
            )
        )
        answer = f"y = {latex(antiderivative + constant[0])}"
    working = render_workout(
        Workout(given=tuple(given), find=(math_line("y"),), steps=tuple(steps)), answer
    )
    return working, answer


def apply_calculus_extension(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.operation == "taylor" and intent.expr:
        out = math_school.taylor_series(
            intent.expr,
            intent.variable,
            intent.limit_point or "0",
            intent.taylor_n or 5,
            nonzero_terms=intent.combo_n,
        )
        lines.append(f"Taylor: {out.latex}")
        return finish_with_answer(lines, out.latex)
    if (
        intent.operation == "partial"
        and intent.expr
        and intent.school_op
        not in {
            "gradient",
            "directional",
            "divergence",
            "curl",
        }
    ):
        out = math_school.partial_derivative(intent.expr, intent.variable)
        lines.append(f"Partial: {out.latex}")
        return finish_with_answer(lines, out.latex)
    if intent.operation == "dsolve" and intent.expr:
        out = solve_ode(
            intent.expr,
            intent.variable,
            initial_x=intent.initial_x,
            initial_y=intent.initial_y,
        )
        lines.append(f"ODE: {out.latex}")
        block = finish_with_answer(lines, out.latex)
        if not out.steps:
            integrated = _direct_integration_working(intent)
            if integrated is None:
                return block
            working, answer = integrated
            return replace(finish_with_answer(lines, answer), direct_reply=working)
        labels = ["Separate variables", "Integrate both sides", "Write the general solution"]
        if len(out.steps) == 4:
            labels.append("Use the initial condition")
        steps = tuple(
            math_line(formula, note_from_label(label))
            for label, formula in zip(labels, out.steps, strict=True)
        )
        given_ode = re.sub(r"\bdy\s*/\s*dx\b", r"\\frac{dy}{dx}", intent.expr or "")
        direct = render_workout(
            Workout(given=(math_line(given_ode),), find=(math_line("y"),), steps=steps),
            out.latex,
        )
        return replace(block, direct_reply=direct)
    if intent.operation == "critical_points" and intent.expr:
        out = math_school.critical_points(intent.expr, intent.variable)
        lines.append(f"Critical points: {out.latex}")
        return finish_with_answer(lines, out.latex)
    if intent.school_op == "identity" and intent.lhs and intent.rhs:
        holds, condition, counterexample = math_school.analyze_identity(intent.lhs, intent.rhs)
        if holds:
            lines.append("Identity holds for every real value in its domain.")
            return finish_with_answer(lines, "true")
        lines.append("The equality is not an identity over the real numbers.")
        details: list[str] = []
        if condition:
            lines.append(f"Equality set: {condition}")
            details.append(f"It holds only for ${condition}$.")
        if counterexample:
            lines.append(f"Counterexample: {counterexample}")
            details.append(f"For example, ${counterexample}$.")
        answer = r"\text{false}"
        direct = render_workout(
            Workout(
                given=(math_line(f"{intent.lhs} = {intent.rhs}"),),
                steps=(text_line("Not an identity: it is not true for every value."), *details),
            ),
            answer,
        )
        return replace(
            finish_with_answer(lines, answer),
            direct_reply=direct,
            direct_answer_binding=answer,
        )
    from app.modules.math import formulas as math_formulas

    if intent.school_op == "average_value" and intent.expr and intent.integral_lower is not None:
        if intent.integral_upper is None:
            return None
        answer = math_formulas.average_value(
            intent.expr, intent.variable, intent.integral_lower, intent.integral_upper
        )
        lines.append(f"Average value: {answer}")
        block = finish_with_answer(lines, answer)
        average_working = _average_value_working(intent, answer)
        return replace(block, worked_reply=average_working) if average_working else block
    if intent.school_op == "linear_approx" and intent.expr and intent.limit_point is not None:
        answer = math_formulas.linear_approximation(
            intent.expr, intent.variable, intent.limit_point
        )
        lines.append(f"Linear approximation: {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "gradient" and intent.expr:
        answer = math_formulas.gradient_of(intent.expr)
        lines.append(f"Gradient: {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "directional" and intent.expr and intent.vec_a and intent.vec_b:
        answer = math_formulas.directional_derivative(
            intent.expr, tuple(intent.vec_a), intent.vec_b
        )
        lines.append(f"Directional derivative: {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "divergence" and intent.expr:
        answer = math_formulas.divergence_of(intent.expr)
        lines.append(f"Divergence: {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "curl" and intent.expr:
        answer = math_formulas.curl_of(intent.expr)
        lines.append(f"Curl: {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "implicit" and intent.lhs and intent.rhs:
        from app.modules.math import solve as math_solve

        answer = math_formulas.implicit_derivative(intent.lhs, intent.rhs)
        lines.append(f"dy/dx = {answer}")
        block = finish_with_answer(lines, answer)
        with sympy_decline():
            from sympy import Derivative, Expr, Function, Symbol, diff, latex

            independent = Symbol(intent.variable or "x", real=True)
            dependent = Symbol("y", real=True)
            dependent_fn = Function("y")(independent)
            sides = [
                math_solve.parse_expression(side, [str(independent), "y"], real=True)
                for side in (intent.lhs, intent.rhs)
            ]
            if not all(isinstance(side, Expr) for side in sides):
                return block  # ``x == 1`` parses to False: no side to differentiate
            left, right = (side.xreplace({dependent: dependent_fn}) for side in sides)
            marker = Symbol("DERIVATIVE_MARKER")
            left_d = diff(left, independent).xreplace(
                {Derivative(dependent_fn, independent): marker, dependent_fn: dependent}
            )
            right_d = diff(right, independent).xreplace(
                {Derivative(dependent_fn, independent): marker, dependent_fn: dependent}
            )

            def _derivative_tex(value: Any) -> str:
                return (
                    latex(value)
                    .replace("DERIVATIVE_{MARKER}", r"\frac{dy}{dx}")
                    .replace("DERIVATIVE\\_MARKER", r"\frac{dy}{dx}")
                )

            differentiated = f"{_derivative_tex(left_d)} = {_derivative_tex(right_d)}"
            given_eq = (
                f"{latex(left.xreplace({dependent_fn: dependent}))} = "
                f"{latex(right.xreplace({dependent_fn: dependent}))}"
            )
            direct = render_workout(
                Workout(
                    given=(math_line(given_eq),),
                    find=(math_line(r"\frac{dy}{dx}"),),
                    steps=(
                        math_line(differentiated, "differentiate both sides with respect to $x$"),
                        math_line(
                            f"\\frac{{dy}}{{dx}} = {answer}",
                            "collect the $\\frac{dy}{dx}$ terms and solve",
                        ),
                    ),
                ),
                f"\\frac{{dy}}{{dx}} = {answer}",
            )
            return replace(block, direct_reply=direct)
        return block
    return None
