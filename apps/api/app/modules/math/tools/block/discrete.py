"""Combinatorics and number theory verified blocks."""

from __future__ import annotations

from dataclasses import replace

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import (
    CombinatoricsInput,
    MathIntent,
    NumberTheoryInput,
    NumberTheoryResult,
)
from app.modules.math.tools.block.canonical import finish_with_answer
from app.services.solving import VerifiedMathBlock
from app.services.workout import math_line


def _format_number_theory_answer(result: NumberTheoryResult) -> str:
    """Short final for ```answer — matches the verified step language."""
    if result.operation == "factorize" and result.factors is not None:
        parts = [f"{p}^{{{e}}}" if e > 1 else f"{p}" for p, e in sorted(result.factors.items())]
        return " \\times ".join(parts)
    if result.operation == "is_prime" and result.result_bool is not None:
        return "prime" if result.result_bool else "not prime"
    if result.result_int is not None:
        return str(result.result_int)
    return result.steps[-1] if result.steps else ""


def _verified_block_combinatorics(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.combo_op is None or intent.combo_n is None:
        return None
    if intent.combo_op != "factorial" and intent.combo_k is None:
        return None
    result = math_solve.compute_combinatorics(
        CombinatoricsInput(operation=intent.combo_op, n=intent.combo_n, k=intent.combo_k)
    )
    lines.extend(result.steps)
    lines.append(f"Result: {result.result}")
    answer = str(result.result)
    n = intent.combo_n
    if intent.combo_op == "factorial" and 2 <= n <= 10:
        # One checked line, like ``17 * 23 = 391``: ``5! = 5 * 4 * 3 * 2 * 1 = 120``.
        product = " \u00d7 ".join(str(factor) for factor in range(n, 0, -1))
        answer = f"{n}! = {product} = {answer}"
    working = _counting_working(intent.combo_op, n, intent.combo_k)
    if working is None:
        return finish_with_answer(lines, answer)
    lines.append(f"Working: ${working}$")
    return replace(
        finish_with_answer(lines, answer),
        worked_reply=f"{math_line(working)}\n\n```answer\n{answer}\n```\n",
    )


def _counting_working(op: str | None, n: int, k: int | None) -> str | None:
    """Choose or arrange: the factorial formula, then the short product.

    ``{}^{10}C_{3} = \\frac{10!}{3!\\,7!} = \\frac{10 \\times 9 \\times 8}{3 \\times 2 \\times 1}``
    and ``{}^{7}P_{3} = \\frac{7!}{4!} = 7 \\times 6 \\times 5``. Long products are left out.
    """
    if k is None or op not in {"combinations", "permutations"}:
        return None
    if op == "permutations":
        if not 0 < k <= 8:
            return None
        product = r" \times ".join(str(factor) for factor in range(n, n - k, -1))
        return rf"{{}}^{{{n}}}P_{{{k}}} = \frac{{{n}!}}{{{n - k}!}} = {product}"
    shorter = min(k, n - k)
    if not 0 < shorter <= 6:
        return None
    top = r" \times ".join(str(factor) for factor in range(n, n - shorter, -1))
    bottom = r" \times ".join(str(factor) for factor in range(shorter, 0, -1))
    return rf"{{}}^{{{n}}}C_{{{k}}} = \frac{{{n}!}}{{{k}!\,{n - k}!}} = \frac{{{top}}}{{{bottom}}}"


def _verified_block_number_theory(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.numtheory_op == "crt":
        if not intent.vec_a or len(intent.vec_a) != 4:
            return None
        from app.modules.math.formulas import chinese_remainder

        a, m, b, n = (int(value) for value in intent.vec_a)
        answer = chinese_remainder(a, m, b, n)
        lines.append(f"x \\equiv {answer} \\pmod{{{int(intent.vec_a[1] * intent.vec_a[3])}}}")
        return finish_with_answer(lines, answer)
    if intent.numtheory_op is None or intent.numtheory_a is None:
        return None
    result = math_solve.compute_number_theory(
        NumberTheoryInput(
            operation=intent.numtheory_op,
            a=intent.numtheory_a,
            b=intent.numtheory_b,
            values=intent.numtheory_values,
        )
    )
    lines.extend(result.steps)
    answer = _format_number_theory_answer(result)
    if not answer:
        return VerifiedMathBlock(text="\n".join(lines))
    return finish_with_answer(
        lines,
        answer,
    )
