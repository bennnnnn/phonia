"""The arithmetic block's last step: the expression the intent carries.

A power in index notation, an exact value beside its decimal, factorials worked
out, or a plain evaluation shown as an equation (with a number line for a short
sum or difference).
"""

from __future__ import annotations

from dataclasses import replace

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school.teaching import _attach_picture
from app.services.workout import Workout, math_line, render_workout


def expression_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if not intent.expr:
        return None
    if intent.school_op == "symbolic_power":
        return _symbolic_power_block(intent, intent.expr, lines)
    answer = math_school.evaluate_arithmetic(intent.expr)
    if intent.school_op == "eval_exact_decimal":
        return _exact_decimal_block(intent, intent.expr, answer, lines)
    factorials = _factorial_block(intent.expr or "", answer, lines)
    if factorials is not None:
        return factorials
    lines.append(f"Result: {answer}")
    block = finish_with_answer(lines, answer)
    from app.modules.math.tools.direct_arithmetic import arithmetic_equation

    shown = arithmetic_equation(intent.expr or "", answer)
    if shown is not None:
        if answer == math_school.UNDEFINED_LATEX:
            # "5 ÷ 0 is undefined", not an equation with a word on one side.
            shown = shown.removesuffix(f" = {answer}") + r" \text{ is undefined}"
        return replace(block, display_answer=shown)
    if intent.school_op != "eval" or not intent.expr:
        return block
    from app.modules.math.solve.teaching_elementary import number_line_for_expr

    move = number_line_for_expr(intent.expr, answer)
    if move is None:
        return block
    return _attach_picture(block, move, intent, direct=True)


def _symbolic_power_block(intent: MathIntent, expr: str, lines: list[str]) -> VerifiedMathBlock:
    """``x^3`` read from "x cubed": the power, and up to eight factors written out."""
    from app.modules.math import solve as math_solve

    answer = math_solve.simplify_expression(expr, intent.variable).latex
    lines.append(f"Power notation: {answer}")
    block = finish_with_answer(lines, answer)
    base, separator, exponent_text = expr.rpartition("^")
    if not separator or not exponent_text.isdigit():
        return block
    exponent = int(exponent_text)
    if exponent == 0:
        formula = math_line("a^0 = 1, \\quad a \\ne 0", "Zero-exponent law")
        line = math_line(f"{base}^0 = 1")
    elif exponent == 1:
        formula = math_line("a^1 = a", "First power")
        line = math_line(f"{base}^1 = {answer}")
    elif exponent <= 8:
        factors = r" \times ".join(base for _ in range(exponent))
        formula = math_line("a^{n} = a \\times \\cdots \\times a", "Power notation")
        line = math_line(f"{base}^{exponent} = {factors} = {answer}")
    else:
        formula = math_line("a^{n} = a \\times \\cdots \\times a", "Power notation")
        line = math_line(f"{base}^{exponent}", f"{exponent} factors of ${base}$")
    working = render_workout(
        Workout(
            given=(math_line(f"{base}^{{{exponent}}}"),),
            formula=(formula,),
            substitution=(line,),
        )
    )
    return replace(
        block,
        direct_reply=f"{working}\n\n```answer\n{answer}\n```\n",
    )


def _exact_decimal_block(
    intent: MathIntent, expr: str, answer: str, lines: list[str]
) -> VerifiedMathBlock | None:
    """The exact value and its decimal to six figures; declines an expression with a letter."""
    from app.modules.math import solve as math_solve

    parsed = math_solve.parse_expression(expr, [intent.variable])
    if isinstance(parsed, tuple) or parsed.free_symbols:
        return None
    decimal = str(parsed.evalf(6))
    direct = render_workout(
        Workout(
            given=(math_line(expr),),
            steps=(math_line(answer, "exact"), math_line(f"\\approx {decimal}", "decimal")),
        ),
        answer,
    )
    block = finish_with_answer(lines, answer)
    return VerifiedMathBlock(
        text=block.text,
        canonical_fence=block.canonical_fence,
        canonical_answer=block.canonical_answer,
        direct_reply=direct,
    )


def _factorial_block(expr: str, answer: str, lines: list[str]) -> VerifiedMathBlock | None:
    """``6!/4! = 720/24``, then the answer on its own line: the left side is written once."""
    if "!" not in expr:
        return None
    from sympy import Rational

    from app.modules.math import solve as math_solve
    from app.modules.math.solve.factorial_working import factorial_working

    working = factorial_working(expr)
    parsed = math_solve.parse_expression(expr, ["x"])
    if working is None or isinstance(parsed, tuple):
        return None
    if parsed != Rational(working.value.numerator, working.value.denominator):
        return None
    lines.append(f"Working: ${working.tex}$")
    lines.append(f"Result: {answer}")
    block = finish_with_answer(lines, answer)
    return replace(block, worked_reply=f"{math_line(working.tex)}\n\n```answer\n{answer}\n```\n")
