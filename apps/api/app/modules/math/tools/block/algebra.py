"""Equation / inequality / system / Newton verified blocks."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import (
    EquationInput,
    MathIntent,
    NewtonMethodInput,
    SystemOfEquationsInput,
)
from app.modules.math.solve.declines import declines, sympy_decline
from app.modules.math.solve.key_steps import (
    KeyStep,
    equation_check_latex,
    equation_key_steps,
    rewrite_label,
    stringify_key_steps,
    used_factor_trace,
    written_side,
)
from app.modules.math.solve.parse import parse_equation as parse_eq
from app.modules.math.solve.step_rules import (
    evaluate_powers,
    substitution_check,
    with_powers_evaluated,
)
from app.modules.math.solve.traces import (
    compound_inequality_trace,
    inequality_trace,
    system_trace,
)
from app.modules.math.tools.block.answer_text import (
    _format_equation_answer,
    _format_system_answer,
)
from app.modules.math.tools.block.canonical import _diagram_block, finish_with_answer
from app.services.solving import VerifiedMathBlock


def _number_line_interval_latex(spec: object) -> str | None:
    intervals = getattr(spec, "intervals", None)
    if not intervals:
        return None

    def endpoint(value: float | None, *, left: bool) -> str:
        if value is None:
            return r"-\infty" if left else r"\infty"
        return str(int(value)) if float(value).is_integer() else f"{value:g}"

    pieces: list[str] = []
    for interval in intervals:
        left_bracket = "[" if interval.start_inclusive else "("
        right_bracket = "]" if interval.end_inclusive else ")"
        pieces.append(
            rf"\left{left_bracket}{endpoint(interval.start, left=True)},\;"
            rf"{endpoint(interval.end, left=False)}\right{right_bracket}"
        )
    return r" \cup ".join(pieces)


@declines(False)
def _rational_interval_is_clearer(intent: MathIntent) -> bool:
    """Use intervals for sign-chart problems with both zeros and poles."""
    from sympy import Expr

    lhs = math_solve.parse_expression(intent.lhs or "", [intent.variable], real=True)
    rhs = math_solve.parse_expression(intent.rhs or "", [intent.variable], real=True)
    if not (isinstance(lhs, Expr) and isinstance(rhs, Expr)):
        return False
    parsed = lhs - rhs
    variable = next(
        (symbol for symbol in parsed.free_symbols if str(symbol) == intent.variable),
        None,
    )
    if variable is None:
        return False
    numerator, denominator = parsed.as_numer_denom()
    return variable in denominator.free_symbols and variable in numerator.free_symbols


_COMPLEX_ROOT_CUE = re.compile(
    r"\b(?:complex|imaginary|all\s+(?:the\s+)?(?:roots|solutions|zeros))\b|\\mathbb\{C\}|\u2102",
    re.IGNORECASE,
)


def wants_complex_roots(text: str) -> bool:
    """``complex roots of x^3 = 8`` asks for every root; ``solve x^3 = 8`` does not."""
    return _COMPLEX_ROOT_CUE.search(text) is not None


def _written_given(
    intent: MathIntent,
    lhs: Any,
    rhs: Any,
    key_steps: list[KeyStep],
    result: Any,
) -> tuple[str, list[KeyStep]]:
    """Given is the equation as typed; the solver's tidy form is the first step.

    ``3(x-2)+4 = 2x+5`` used to show ``Given: 3x - 2 = 2x + 5`` with the
    expansion silently done. The typed form comes first and the expansion (or
    the collected like terms) is its own line, the same equation the trace
    then starts from.
    """
    evaluated = f"{result.lhs_latex} = {result.rhs_latex}"
    variables = [intent.variable or "x"]
    left = written_side(intent.lhs or "", variables)
    right = written_side(intent.rhs or "", variables)
    if left is None or right is None:
        return evaluated, key_steps
    written = f"{left[1]} = {right[1]}"
    if written == evaluated or not key_steps:
        return written if key_steps else evaluated, key_steps
    if r"\log" in written:
        return written, key_steps
    label = rewrite_label(left[0], lhs) or rewrite_label(right[0], rhs)
    # ``5^2`` typed is ``25`` to the solver; that number work is its own step,
    # then the equation it gives (a Simplify line joins that step).
    powers = evaluate_powers(left[0], right[0])
    if powers is not None:
        left_tex = with_powers_evaluated(left[1], left[0])
        replaced = f"{left_tex} = {with_powers_evaluated(right[1], right[0])}"
        steps = [KeyStep(label=powers[0], formula=powers[1])]
        steps.append(KeyStep(label="Simplify", formula=replaced))
        if replaced != evaluated:
            # ``x^2 + 8 \cdot 3`` still has number work before ``x^2 + 24``.
            product = re.search(r"\d\s*\\cdot\s*\d", replaced) is not None
            arithmetic = "Multiply the numbers" if product else "Calculate"
            steps.append(KeyStep(label=label or arithmetic, formula=evaluated))
        return written, [*steps, *key_steps]
    if label is None:
        return written, key_steps
    return written, [KeyStep(label=label, formula=evaluated), *key_steps]


def _typed_check(intent: MathIntent, lhs: Any, rhs: Any) -> str | None:
    """The check substitutes into the equation as typed, else the solver's sides."""
    variable = intent.variable or "x"
    left = written_side(intent.lhs or "", [variable])
    right = written_side(intent.rhs or "", [variable])
    if left is not None and right is not None:
        typed = substitution_check(left[1], right[1], lhs, rhs, variable)
        if typed is not None:
            return typed
    return equation_check_latex(lhs, rhs, variable)


def _verified_block_equation(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.lhs and intent.rhs):
        return None
    eq = EquationInput(
        lhs=intent.lhs[: settings.math_max_expr_length],
        rhs=intent.rhs[: settings.math_max_expr_length],
        variables=[intent.variable],
        complex_roots=wants_complex_roots(intent._request_text or ""),
    )
    result = math_solve.solve_equation(eq)
    lines.extend(result.steps)
    answer = _format_equation_answer(
        result.canonical_solutions_latex or result.solutions_latex,
        result.solution_kind,
    )
    if result.domain_conditions_latex:
        conditions_to_display = result.domain_conditions_latex
        if result.solution_kind == "finite":
            variable_exclusion = rf"{intent.variable} \ne "
            # Finite roots already satisfy any original x-domain exclusions;
            # keep those restrictions in the working, not in the result chip.
            # Parameter conditions (for example a != 0 in ax=5) still belong
            # in the final because they change whether the formula is valid.
            conditions_to_display = [
                condition
                for condition in conditions_to_display
                if not condition.startswith(variable_exclusion)
            ]
        conditions = r",\; ".join(conditions_to_display)
        if result.solution_kind == "infinite":
            answer = rf"{intent.variable} \in \mathbb{{R}},\; {conditions}"
        elif conditions:
            answer = rf"{answer},\quad {conditions}"
    if result.alternate_cases_latex:
        answer = answer + "\n" + r";\quad ".join(result.alternate_cases_latex)
    _, lhs, rhs = parse_eq(eq)
    key_steps = equation_key_steps(
        lhs,
        rhs,
        intent.variable or "x",
        force_quadratic_formula=intent.school_op == "quadratic_formula",
    )
    zero_power = re.search(
        rf"\b{re.escape(intent.variable or 'x')}\s*\^\s*(?:\{{\s*0\s*\}}|0)(?!\w)",
        f"{intent.lhs} {intent.rhs}",
        re.IGNORECASE,
    )
    if zero_power is not None:
        symbol = intent.variable or "x"
        zero_step = KeyStep(
            label="Use the zero-exponent law",
            formula=rf"{symbol}^0 = 1",
            reason="any nonzero base raised to the zero power equals 1",
            conditions=rf"{symbol} \ne 0",
        )
        key_steps = [zero_step, *key_steps]
        lines.insert(
            0,
            rf"Zero-exponent law: {symbol}^0 = 1 for {symbol} \ne 0.",
        )
    given_latex, key_steps = _written_given(intent, lhs, rhs, key_steps, result)
    alt = None
    if used_factor_trace(key_steps):
        alt = "Another method is the quadratic formula; it gives the same two solutions."
    block = finish_with_answer(
        lines,
        answer,
        key_steps=key_steps,
        given_latex=given_latex,
        check_latex=_typed_check(intent, lhs, rhs),
        alternate_method_note=alt,
    )
    block = replace(
        block,
        domain_conditions=tuple(result.domain_conditions_latex),
        excluded_values=tuple(
            condition for condition in result.domain_conditions_latex if r"\ne" in condition
        ),
    )
    if intent.school_op != "exact_and_decimal":
        return block
    with sympy_decline() as declined:
        from sympy import Eq, Symbol, latex, solve

        variable = next(
            (
                symbol
                for symbol in getattr(lhs, "free_symbols", set())
                | getattr(rhs, "free_symbols", set())
                if str(symbol) == (intent.variable or "x")
            ),
            Symbol(intent.variable or "x"),
        )
        values = solve(Eq(lhs, rhs), variable)
        approximations = [str(latex(value.evalf(6))) for value in values]
    if declined:
        return block
    if not approximations:
        return block
    approx_answer = r" \text{ or } ".join(
        f"{intent.variable or 'x'} \\approx {value}" for value in approximations
    )
    direct = (
        f"**Exact answer**\n\n${answer}$\n\n"
        f"**Decimal approximation**\n\n${approx_answer}$\n\n"
        f"```answer\n{answer}\n```\n"
    )
    return replace(block, direct_reply=direct)


def _verified_block_inequality(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.lhs and intent.rhs and intent.comparator):
        return None
    max_len = settings.math_max_expr_length
    if intent.lower is not None and intent.comparator_upper is not None:
        result = math_solve.solve_compound_inequality(
            intent.lower[:max_len],
            intent.comparator,
            intent.lhs[:max_len],
            intent.comparator_upper,
            intent.rhs[:max_len],
            intent.variable,
        )
    else:
        result = math_solve.solve_inequality(
            intent.lhs[:max_len],
            intent.rhs[:max_len],
            intent.variable,
            intent.comparator,
        )
    lines.extend(result.steps)
    answer = _format_equation_answer(result.solutions_latex, result.solution_kind)
    if intent.lower is not None and intent.comparator_upper is not None:
        key_steps, given = compound_inequality_trace(
            intent.lower[:max_len],
            intent.comparator,
            intent.lhs[:max_len],
            intent.comparator_upper,
            intent.rhs[:max_len],
            intent.variable,
        )
    else:
        key_steps, given = inequality_trace(
            intent.lhs[:max_len], intent.rhs[:max_len], intent.variable, intent.comparator
        )
    lines.extend(stringify_key_steps(key_steps))
    # Reconstruct the inequality text ("x > 4" / "1 < x < 5") so the
    # number-line builder can render the solution set as a diagram. The
    # model often emits a malformed ```graph fence for the number line and
    # validate_math_fences then shows "Could not render that diagram.";
    # attaching the verified number_line as canonical_fence lets the
    # post-stream rewriter replace that broken fence with the real one.
    if intent.lower is not None and intent.comparator_upper is not None:
        ineq_text = (
            f"{intent.lower} {intent.comparator} {intent.lhs} "
            f"{intent.comparator_upper} {intent.rhs}"
        )
    else:
        ineq_text = f"{intent.lhs} {intent.comparator} {intent.rhs}"
    line_spec = math_solve.number_line_spec_from_expr(ineq_text[:max_len], intent.variable)
    if line_spec is not None:
        # SymPy prints ``x \leq -2 \wedge -\infty < x``; the trace's last
        # line (``x \le -2``) is the same verified set, spelled for people.
        return replace(
            _diagram_block(
                lines,
                line_spec,
                answer,
                display_answer=(
                    key_steps[-1].formula
                    if key_steps
                    else (
                        _number_line_interval_latex(line_spec)
                        if _rational_interval_is_clearer(intent)
                        else None
                    )
                ),
            ),
            key_steps=tuple(key_steps),
            given_latex=given,
        )
    return finish_with_answer(lines, answer, key_steps=key_steps, given_latex=given)


def _verified_block_system(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.system_equations:
        return None
    capped_equations = [
        (
            lhs[: settings.math_max_expr_length],
            rhs[: settings.math_max_expr_length],
        )
        for lhs, rhs in intent.system_equations
    ]
    sys_input = SystemOfEquationsInput(
        equations=capped_equations,
        variables=intent.system_variables or ["x", "y"],
    )
    sys_result = math_solve.solve_system(sys_input)
    lines.extend(sys_result.steps)
    answer = _format_system_answer(sys_result.solutions, sys_result.solution_kind)
    key_steps, given, check = system_trace(capped_equations, sys_input.variables)
    lines.extend(stringify_key_steps(key_steps))
    return finish_with_answer(
        lines, answer, key_steps=key_steps, given_latex=given, check_latex=check
    )


def _verified_block_numerical_method(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.expr and intent.newton_guess is not None):
        return None
    newton_input = NewtonMethodInput(
        expr=intent.expr[: settings.math_max_expr_length],
        variable=intent.variable,
        initial_guess=intent.newton_guess,
    )
    newton_result = math_solve.newton_method(newton_input)
    lines.append(f"Newton's method for {newton_input.expr} = 0, x0 = {newton_input.initial_guess}:")
    for step in newton_result.iterations:
        lines.append(f"  n={step.n}: x_{step.n} = {step.x_n}, f(x_{step.n}) = {step.f_x_n}")
    if not newton_result.converged or newton_result.root is None:
        lines.append(
            f"Did not converge within {newton_result.iterations_used} iterations "
            "(the derivative may have vanished, or more iterations are needed)."
        )
        # No ```answer — post-stream must not force a root that was not found.
        return VerifiedMathBlock(
            text="\n".join(lines),
            newton_input=newton_input.model_copy(deep=True),
            newton_result=newton_result.model_copy(deep=True),
        )

    lines.append(
        f"Converged after {newton_result.iterations_used} iterations: root ≈ {newton_result.root}"
    )
    answer = f"{newton_result.root:g}"
    return replace(
        finish_with_answer(lines, answer),
        # A numerical root is an approximation of the variable; its card says so.
        display_answer=rf"{newton_input.variable} \approx {answer}",
        newton_input=newton_input.model_copy(deep=True),
        newton_result=newton_result.model_copy(deep=True),
    )
