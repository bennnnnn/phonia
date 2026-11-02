"""Exact primary-school fraction procedures."""

from __future__ import annotations

import re
from fractions import Fraction
from math import gcd, lcm
from typing import cast

from app.modules.math.schemas import FractionStep, FractionWorkSpec, MathIntent
from app.modules.math.schemas.operations import FractionOp


def _parse_fraction(value: str) -> tuple[int, int] | None:
    numerator_text, separator, denominator_text = value.partition("/")
    if not separator:
        return None
    try:
        numerator, denominator = int(numerator_text), int(denominator_text)
    except ValueError:
        return None
    if numerator < 0 or denominator <= 0:
        return None
    return numerator, denominator


def _latex(numerator: int, denominator: int) -> str:
    return str(numerator) if denominator == 1 else rf"\frac{{{numerator}}}{{{denominator}}}"


def _finish(
    operation: str,
    operands: list[str],
    value: Fraction,
    steps: list[FractionStep],
    *,
    answer: str | None = None,
) -> FractionWorkSpec:
    return FractionWorkSpec(
        operation=cast(FractionOp, operation),
        operands=operands,
        answer=answer or _latex(value.numerator, value.denominator),
        exact_numerator=value.numerator,
        exact_denominator=value.denominator,
        steps=steps,
    )


def _add_or_subtract(
    a: int, b: int, c: int, d: int, *, subtract: bool
) -> tuple[Fraction, list[FractionStep]] | None:
    """Rewrite over the least common denominator, combine, then simplify.

    Each step changes something: equal denominators skip the rewrite ("1/2, 3/2 =
    1/2, 3/2" said nothing), and a result in lowest terms needs no simplify step.
    """
    common = lcm(b, d)
    left, right = a * (common // b), c * (common // d)
    combined = left - right if subtract else left + right
    if combined < 0:
        return None
    symbol, verb = ("-", "Subtract") if subtract else ("+", "Add")
    steps: list[FractionStep] = []
    if b == d:
        explanation = (
            f"The denominators are already the same, so {verb.lower()} the numerators "
            f"and keep the denominator {common}."
        )
    else:
        steps.append(
            FractionStep(
                kind="common_denominator",
                explanation=f"Rewrite both fractions over the least common denominator {common}.",
                expression=rf"\frac{{{a}}}{{{b}}} {symbol} \frac{{{c}}}{{{d}}}",
                result=rf"\frac{{{left}}}{{{common}}} {symbol} \frac{{{right}}}{{{common}}}",
            )
        )
        explanation = f"{verb} the numerators and keep the denominator {common}."
    value = Fraction(combined, common)
    divisor = gcd(combined, common)
    # 4/2 is shown, then simplified; 0/4 is 0 at once.
    simplifies = combined > 0 and divisor > 1
    steps.append(
        FractionStep(
            kind="combine",
            explanation=explanation,
            expression=rf"\frac{{{left} {symbol} {right}}}{{{common}}}",
            result=_latex(combined, common)
            if simplifies
            else _latex(value.numerator, value.denominator),
        )
    )
    if simplifies:
        steps.append(
            FractionStep(
                kind="gcd",
                explanation=f"Simplify: divide the top and bottom by {divisor}.",
                expression=rf"\frac{{{combined}\div {divisor}}}{{{common}\div {divisor}}}",
                result=_latex(value.numerator, value.denominator),
            )
        )
    return value, steps


def _binary(intent: MathIntent) -> FractionWorkSpec | None:
    operands = intent.fraction_operands or []
    if len(operands) != 2:
        return None
    left_parts, right_parts = _parse_fraction(operands[0]), _parse_fraction(operands[1])
    if left_parts is None or right_parts is None:
        return None
    a, b = left_parts
    c, d = right_parts
    left, right = Fraction(a, b), Fraction(c, d)
    op = intent.school_op
    steps: list[FractionStep] = []
    if op in {"fraction_add", "fraction_subtract"}:
        added = _add_or_subtract(a, b, c, d, subtract=op == "fraction_subtract")
        if added is None:
            return None
        value, steps = added
        operation = "subtract" if op == "fraction_subtract" else "add"
        return _finish(operation, operands, value, steps)
    if op == "fraction_multiply":
        value = left * right
        steps.append(
            FractionStep(
                kind="multiply",
                explanation="Multiply numerators and multiply denominators.",
                expression=rf"\frac{{{a}\times {c}}}{{{b}\times {d}}}",
                result=_latex(value.numerator, value.denominator),
            )
        )
        return _finish("multiply", operands, value, steps)
    if op == "fraction_divide" and c != 0:
        steps.append(
            FractionStep(
                kind="reciprocal",
                explanation=(
                    "Keep the first fraction, change division to multiplication, "
                    "and flip the second."
                ),
                expression=rf"\frac{{{a}}}{{{b}}}\div\frac{{{c}}}{{{d}}}",
                result=rf"\frac{{{a}}}{{{b}}}\times\frac{{{d}}}{{{c}}}",
            )
        )
        value = left / right
        steps.append(
            FractionStep(
                kind="multiply",
                explanation="Multiply, then simplify.",
                expression=rf"\frac{{{a}\times {d}}}{{{b}\times {c}}}",
                result=_latex(value.numerator, value.denominator),
            )
        )
        return _finish("divide", operands, value, steps)
    return None


def build_fraction_work(intent: MathIntent) -> FractionWorkSpec | None:
    operands = intent.fraction_operands or []
    op = intent.school_op
    if op in {"fraction_add", "fraction_subtract", "fraction_multiply", "fraction_divide"}:
        return _binary(intent)
    if op == "fraction_simplify" and len(operands) == 1:
        parts = _parse_fraction(operands[0])
        if parts is None:
            return None
        numerator, denominator = parts
        divisor = gcd(numerator, denominator)
        value = Fraction(numerator, denominator)
        return _finish(
            "simplify",
            operands,
            value,
            [
                FractionStep(
                    kind="gcd",
                    explanation=(
                        f"The greatest common divisor is {divisor}; divide both parts by it."
                    ),
                    expression=(
                        rf"\frac{{{numerator}\div {divisor}}}"
                        rf"{{{denominator}\div {divisor}}}"
                    ),
                    result=_latex(value.numerator, value.denominator),
                )
            ],
        )
    if op == "fraction_equivalent" and len(operands) == 1 and intent.fraction_target:
        parts = _parse_fraction(operands[0])
        if parts is None:
            return None
        numerator, denominator = parts
        target = intent.fraction_target
        if target <= 0 or target % denominator:
            return None
        factor = target // denominator
        result_numerator = numerator * factor
        value = Fraction(result_numerator, target)
        return _finish(
            "equivalent",
            [*operands, str(target)],
            value,
            [
                FractionStep(
                    kind="equivalent",
                    explanation=f"Multiply numerator and denominator by {factor}.",
                    expression=(
                        rf"\frac{{{numerator}\times {factor}}}"
                        rf"{{{denominator}\times {factor}}}"
                    ),
                    result=rf"\frac{{{result_numerator}}}{{{target}}}",
                )
            ],
            answer=rf"\frac{{{result_numerator}}}{{{target}}}",
        )
    if op == "fraction_mixed_to_improper" and len(operands) == 2:
        parts = _parse_fraction(operands[1])
        if parts is None:
            return None
        whole, (numerator, denominator) = int(operands[0]), parts
        improper = whole * denominator + numerator
        value = Fraction(improper, denominator)
        return _finish(
            "mixed_to_improper",
            operands,
            value,
            [
                FractionStep(
                    kind="convert",
                    explanation="Multiply the whole number by the denominator.",
                    expression=rf"{whole}\times {denominator}",
                    result=str(whole * denominator),
                ),
                FractionStep(
                    kind="convert",
                    explanation=("Add the old numerator, then keep the original denominator."),
                    expression=rf"\frac{{{whole * denominator}+{numerator}}}{{{denominator}}}",
                    result=rf"\frac{{{improper}}}{{{denominator}}}",
                ),
            ],
            answer=rf"\frac{{{improper}}}{{{denominator}}}",
        )
    if op == "fraction_improper_to_mixed" and len(operands) == 1:
        parts = _parse_fraction(operands[0])
        if parts is None:
            return None
        numerator, denominator = parts
        whole, remainder = divmod(numerator, denominator)
        value = Fraction(numerator, denominator)
        answer = str(whole) if not remainder else rf"{whole}\frac{{{remainder}}}{{{denominator}}}"
        return _finish(
            "improper_to_mixed",
            operands,
            value,
            [
                FractionStep(
                    kind="convert",
                    explanation=(
                        f"{denominator} goes into {numerator} exactly {whole} whole times, "
                        f"with {remainder} left over."
                    ),
                    expression=str(numerator),
                    result=rf"{denominator}\times {whole}+{remainder}",
                ),
                FractionStep(
                    kind="convert",
                    explanation=(
                        "Keep the quotient as the whole number and put the remainder over "
                        "the original denominator."
                    ),
                    expression=rf"\frac{{{numerator}}}{{{denominator}}}",
                    result=rf"{whole}+\frac{{{remainder}}}{{{denominator}}}",
                ),
            ],
            answer=answer,
        )
    if op == "fraction_of_quantity" and len(operands) == 2:
        parts = _parse_fraction(operands[0])
        if parts is None:
            return None
        try:
            quantity = Fraction(operands[1])
        except ValueError:
            return None
        numerator, denominator = parts
        value = Fraction(numerator, denominator) * quantity
        return _finish(
            "of_quantity",
            operands,
            value,
            [
                FractionStep(
                    kind="quantity",
                    explanation="'Of' means multiply.",
                    expression=rf"\frac{{{numerator}}}{{{denominator}}}\times {operands[1]}",
                    result=_latex(value.numerator, value.denominator),
                )
            ],
        )
    if op == "fraction_compare" and len(operands) == 2:
        left_parts, right_parts = _parse_fraction(operands[0]), _parse_fraction(operands[1])
        if left_parts is None or right_parts is None:
            return None
        a, b = left_parts
        c, d = right_parts
        left_cross, right_cross = a * d, c * b
        symbol = ">" if left_cross > right_cross else "<" if left_cross < right_cross else "="
        answer = rf"\frac{{{a}}}{{{b}}} {symbol} \frac{{{c}}}{{{d}}}"
        return FractionWorkSpec(
            operation="compare",
            operands=operands,
            answer=answer,
            steps=[
                FractionStep(
                    kind="compare",
                    explanation="Cross-multiply; both products use the same positive denominator.",
                    expression=rf"{a}\times {d}\ ?\ {c}\times {b}",
                    result=f"{left_cross} {symbol} {right_cross}",
                )
            ],
        )
    return None


_OPERATION_SYMBOL = {"add": "+", "subtract": "-", "multiply": r"\times", "divide": r"\div"}
_WRITTEN_FRACTION = re.compile(r"(?:(?P<whole>\d+) )?(?P<top>\d+)/(?P<bottom>\d+)")


def fraction_tex(value: str) -> str | None:
    """``5/2`` -> ``\\frac{5}{2}``; the mixed number ``2 1/2`` -> ``2\\frac{1}{2}``."""
    match = _WRITTEN_FRACTION.fullmatch(value.strip())
    if match is None:
        return None
    fraction = _latex_fraction(int(match["top"]), int(match["bottom"]))
    return f"{match['whole']}{fraction}" if match["whole"] else fraction


def _latex_fraction(numerator: int, denominator: int) -> str:
    return rf"\frac{{{numerator}}}{{{denominator}}}"


def mixed_number_tex(numerator: int, denominator: int) -> str:
    """``17/4`` -> ``4\\frac{1}{4}``."""
    whole, remainder = divmod(numerator, denominator)
    if not remainder:
        return str(whole)
    return rf"{whole}{_latex_fraction(remainder, denominator)}"


def fraction_working(work: FractionWorkSpec, written: tuple[str, str] | None = None) -> str | None:
    """One line from the question to the last step before the answer.

    ``\\frac{3}{4} \\div \\frac{2}{5} = \\frac{3}{4} \\times \\frac{5}{2}``. With
    ``written`` mixed numbers it starts from them:
    ``2\\frac{1}{2} + 1\\frac{3}{4} = \\frac{5}{2} + \\frac{7}{4} = \\frac{10}{4} + \\frac{7}{4}``.
    """
    if work.operation == "of_quantity" and len(work.operands) == 2:
        part = _parse_fraction(work.operands[0])
        if part is None:
            return None
        top, bottom = part
        quantity = work.operands[1]
        # "of" means multiply: ``\frac{2}{3} \times 60 = \frac{2 \times 60}{3}``.
        return rf"{_latex_fraction(top, bottom)} \times {quantity} = " + (
            rf"\frac{{{top} \times {quantity}}}{{{bottom}}}"
        )
    symbol = _OPERATION_SYMBOL.get(work.operation)
    if symbol is None or len(work.operands) != 2:
        return None
    parts = [_parse_fraction(operand) for operand in work.operands]
    if parts[0] is None or parts[1] is None:
        return None
    (a, b), (c, d) = parts[0], parts[1]
    chain = [f"{_latex_fraction(a, b)} {symbol} {_latex_fraction(c, d)}"]
    if written is not None:
        shown = [fraction_tex(operand) for operand in written]
        if shown[0] is None or shown[1] is None:
            return None
        chain.insert(0, f"{shown[0]} {symbol} {shown[1]}")
    if work.operation in {"add", "subtract"}:
        common = lcm(b, d)
        chain.append(
            f"{_latex_fraction(a * (common // b), common)} {symbol} "
            f"{_latex_fraction(c * (common // d), common)}"
        )
    elif work.operation == "multiply":
        chain.append(rf"\frac{{{a} \times {c}}}{{{b} \times {d}}}")
    elif c:
        chain.append(rf"{_latex_fraction(a, b)} \times {_latex_fraction(d, c)}")
    return " = ".join(dict.fromkeys(chain))
