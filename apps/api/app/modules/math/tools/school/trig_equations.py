"""A trig equation solved in a bounded interval: every solution in it, with the periodic law.

``sin x = 1/2`` for ``0 <= x <= 360`` (degrees) or ``0 <= x < 2pi`` (radians).
"""

from __future__ import annotations

from typing import Any

from app.modules.math.schemas import EquationInput, MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.workout import Workout, math_line, render_workout, text_line


def _exact_decimals(side: Any) -> Any:
    """``-0.5`` -> ``-1/2``, so the angles solve exactly instead of as floats."""
    from sympy import Float, nsimplify

    return nsimplify(side, rational=True) if side.has(Float) else side


def _degrees_in_k(expr: Any, k: Any) -> str:
    """``90 + 180 k`` (degrees) -> ``90^\\circ + 180^\\circ k``."""
    from sympy import expand, latex

    expr = expand(expr)
    constant = expr.subs(k, 0)
    step = expr.coeff(k)
    parts = [f"{latex(constant)}^\\circ"] if constant != 0 else []
    if step != 0:
        parts.append(f"{latex(step)}^\\circ k")
    return " + ".join(parts) or "0^\\circ"


def bounded_equation_block(
    intent: MathIntent,
    lines: list[str],
    *,
    lhs_text: str,
    rhs_text: str,
    lower: str,
    upper: str,
) -> VerifiedMathBlock | None:
    """The solutions of ``lhs_text = rhs_text`` between ``lower`` and ``upper``.

    Declines when the solutions in the interval are not a finite set.
    """
    from sympy import (
        Eq,
        FiniteSet,
        Interval,
        Symbol,
        latex,
        nsimplify,
        pi,
        simplify,
        solveset,
    )

    from app.modules.math import solve as math_solve
    from app.modules.math.solve.parse import parse_equation

    _, lhs, rhs = parse_equation(
        EquationInput(lhs=lhs_text, rhs=rhs_text, variables=[intent.variable])
    )
    # ``cos(x) = -0.5``: a decimal value is read exactly, or the angles
    # come back as floats and print as ``376.99/pi`` degrees.
    lhs, rhs = _exact_decimals(lhs), _exact_decimals(rhs)
    symbols = getattr(lhs, "free_symbols", set()) | getattr(rhs, "free_symbols", set())
    variable = next(
        (symbol for symbol in symbols if str(symbol) == intent.variable),
        Symbol(intent.variable, real=True),
    )
    degrees = intent.school_op == "bounded_degree_equation"
    if degrees:
        low = nsimplify(lower, rational=True) * pi / 180
        high = nsimplify(upper, rational=True) * pi / 180
    else:
        low = math_solve.parse_expression(lower, [])
        high = math_solve.parse_expression(upper, [])
    domain = Interval(
        low,
        high,
        left_open=intent.comparator == "<",
        right_open=intent.comparator_upper == "<",
    )
    solved = solveset(Eq(lhs, rhs), variable, domain=domain)
    if not isinstance(solved, FiniteSet):
        return None
    radian_values = sorted(solved, key=lambda value: float(value))
    display_values = (
        [simplify(value * 180 / pi) for value in radian_values] if degrees else radian_values
    )
    # ``asin(3/10)`` in degrees has no exact school form: two decimals.
    approximate = degrees and not all(value.is_Rational for value in display_values)
    if not display_values:
        answer = r"\text{no solution}"
    else:
        suffix = "^\\circ" if degrees else ""
        joined = r",\;".join(
            f"{float(value):.2f}{suffix}" if approximate else f"{latex(value)}{suffix}"
            for value in display_values
        )
        relation = r"\approx" if approximate else "="
        answer = f"{intent.variable} {relation} {joined}"
    degree_suffix = "^\\circ" if degrees else ""
    left_comparator = r"\le" if intent.comparator == "<=" else "<"
    right_comparator = r"\le" if intent.comparator_upper == "<=" else "<"
    # In degrees the domain reads as written: ``0^\circ \le x \le 360^\circ``.
    shown_low = latex(low * 180 / pi) if degrees else latex(low)
    shown_high = latex(high * 180 / pi) if degrees else latex(high)
    domain_tex = (
        f"{shown_low}{degree_suffix} {left_comparator} {intent.variable} "
        f"{right_comparator} {shown_high}{degree_suffix}"
    )
    periodic = _periodic_steps(intent, lhs, rhs, variable, radian_values, domain_tex, degrees)
    direct = render_workout(
        Workout(
            given=(
                math_line(f"{latex(lhs)} = {latex(rhs)}"),
                math_line(domain_tex, "domain"),
            ),
            find=(math_line(intent.variable),),
            steps=(*(periodic or ()), math_line(answer, "solutions in the domain")),
        ),
        answer,
    )
    lines.extend(
        [
            f"Equation: {latex(lhs)} = {latex(rhs)}",
            f"Domain: {domain_tex}",
            f"Solutions in the domain: {answer}",
        ]
    )
    block = finish_with_answer(lines, answer)
    return VerifiedMathBlock(
        text=block.text,
        canonical_fence=block.canonical_fence,
        canonical_answer=block.canonical_answer,
        direct_reply=direct,
    )


def _periodic_steps(
    intent: MathIntent,
    lhs: Any,
    rhs: Any,
    variable: Any,
    radian_values: list[Any],
    domain_tex: str,
    degrees: bool,
) -> tuple[str, ...] | None:
    """``sin(2x) = 0``: the zero law with ``k``, then the values of ``k`` in the interval."""
    from sympy import Eq, Symbol, cos, latex, pi, simplify, sin, solve, tan

    periodic: tuple[str, ...] | None = None
    if rhs == 0 and getattr(lhs, "func", None) in {sin, cos, tan} and len(lhs.args) == 1:
        integer = Symbol("k", integer=True)
        angle = lhs.args[0]
        if lhs.func == cos:
            angle_solution = pi / 2 + integer * pi
            zero_law = r"\cos(\theta)=0 \Rightarrow \theta=\frac{\pi}{2}+k\pi"
        else:
            angle_solution = integer * pi
            function_name = "sin" if lhs.func == sin else "tan"
            zero_law = rf"\{function_name}(\theta)=0 \Rightarrow \theta=k\pi"
        solved_general = solve(Eq(angle, angle_solution), variable)
        if len(solved_general) == 1:
            general = simplify(solved_general[0])
            k_values: list[str] = []
            for value in radian_values:
                candidates = solve(Eq(general, value), integer)
                if len(candidates) == 1 and candidates[0].is_integer:
                    rendered = latex(candidates[0])
                    if rendered not in k_values:
                        k_values.append(rendered)
            joined_k = r",\;".join(k_values)
            interval_step = (
                math_line(f"k = {joined_k}", f"the values that keep ${intent.variable}$ in range")
                if k_values
                else text_line(
                    f"Keep the values of $k$ that place ${intent.variable}$ in ${domain_tex}$."
                )
            )
            if degrees:
                # The same law in degrees: ``\sin\theta = 0 \Rightarrow \theta = 180^\circ k``.
                zero_law = zero_law.replace(r"\frac{\pi}{2}", r"90^\circ").replace(
                    r"k\pi", r"180^\circ k"
                )
                angle_shown = _degrees_in_k(angle_solution * 180 / pi, integer)
                general_shown = _degrees_in_k(general * 180 / pi, integer)
            else:
                angle_shown, general_shown = latex(angle_solution), latex(general)
            periodic = (
                math_line(f"{zero_law}, \\quad k\\in\\mathbb{{Z}}", "periodic zero law"),
                math_line(f"{latex(angle)} = {angle_shown}", "substitute the angle"),
                math_line(f"{intent.variable} = {general_shown}", "solve"),
                interval_step,
            )
    return periodic
