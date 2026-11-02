"""Whole-request guards and direct formatting for written arithmetic."""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.modules.math.response_intent import MathResponseMode, classify_math_response_intent
from app.modules.math.schemas import ArithmeticWorkSpec, FractionWorkSpec
from app.modules.math.tools.lesson import lesson_math_text
from app.services.solving import VerifiedMathBlock
from app.services.workout import math_line


def equation_line_hides_for_answer_only(verified: VerifiedMathBlock) -> bool:
    """Just the answer is the number when the ordinary line is an equation."""
    value = (verified.canonical_answer or "").strip()
    if not value:
        return False
    if arithmetic_work_spec(verified) is not None:
        return True
    shown = (verified.display_answer or "").strip()
    return shown.endswith(f"= {value}")


def arithmetic_work_spec(verified: VerifiedMathBlock) -> ArithmeticWorkSpec | None:
    specs = [verified.canonical_fence, *verified.canonical_fences]
    candidates = [
        spec for spec in specs if isinstance(spec, dict) and spec.get("type") == "arithmetic"
    ]
    if len(candidates) != 1:
        return None
    try:
        return ArithmeticWorkSpec.model_validate(candidates[0])
    except ValidationError:
        return None


def fraction_work_spec(verified: VerifiedMathBlock) -> FractionWorkSpec | None:
    specs = [verified.canonical_fence, *verified.canonical_fences]
    candidates = [
        spec for spec in specs if isinstance(spec, dict) and spec.get("type") == "fraction"
    ]
    if len(candidates) != 1:
        return None
    try:
        return FractionWorkSpec.model_validate(candidates[0])
    except ValidationError:
        return None


def final_answer(spec: ArithmeticWorkSpec) -> str:
    """The column result without the zeros it carries for alignment: ``10.50`` -> ``10.5``.

    The column itself keeps ``10.50`` under ``2.5`` and ``4.2``; the answer is
    the number.
    """
    whole, dot, decimals = spec.answer.partition(".")
    if not dot or not whole.lstrip("-").isdigit() or not decimals.isdigit():
        return spec.answer
    decimals = decimals.rstrip("0")
    return f"{whole}.{decimals}" if decimals else whole


def can_direct_written_arithmetic(
    verified: VerifiedMathBlock, user_text: str, spec: ArithmeticWorkSpec
) -> bool:
    """Require the entire request to describe the exact traced operation."""
    if len(user_text) > 1000 or verified.canonical_answer != final_answer(spec):
        return False
    from app.modules.math import match as mtm

    if spec.operation == "addition" and len(spec.operands) > 2:
        requested_addends = mtm.written_addition_request(lesson_math_text(user_text))
        return requested_addends == spec.operands
    requested = mtm.written_arithmetic_request(lesson_math_text(user_text))
    solved = mtm.written_arithmetic_request(f"calculate {spec.expression}")
    return requested is not None and requested == solved


def can_direct_fraction(
    verified: VerifiedMathBlock, user_text: str, spec: FractionWorkSpec
) -> bool:
    if len(user_text) > 1000 or verified.canonical_answer != spec.answer:
        return False
    from app.modules.math.tools.extractors.fractions import extract_fraction_intent

    intent = extract_fraction_intent(user_text)
    if intent is None:
        return False
    operation = (intent.school_op or "").removeprefix("fraction_")
    operation = {
        "mixed_to_improper": "mixed_to_improper",
        "improper_to_mixed": "improper_to_mixed",
        "of_quantity": "of_quantity",
    }.get(operation, operation)
    request_operands = intent.fraction_operands or []
    return (
        operation == spec.operation and request_operands == spec.operands[: len(request_operands)]
    )


def _shown_operand(token: str) -> str:
    """Drop column padding so ``03.60`` reads as ``3.60`` on the answer line."""
    whole, dot, fraction = token.partition(".")
    whole = whole.lstrip("0") or "0"
    return f"{whole}.{fraction}" if dot else whole


_DISPLAY_OPERATOR = {
    "+": "+",
    "-": "\u2212",
    "*": "\u00d7",
    "/": "\u00f7",
}


def arithmetic_equation(expr: str, answer: str) -> str | None:
    """``8-8-8`` and ``8-8*2`` read as one checked line, like ``8 - 8 = 0``."""
    tokens = _arithmetic_tokens(expr.replace(" ", ""))
    if tokens is None:
        return None
    shown: list[str] = []
    for index, token in enumerate(tokens):
        if index % 2 == 1:
            shown.append(_DISPLAY_OPERATOR[token])
            continue
        if token.startswith("-"):
            shown.append(f"\u2212{token[1:]}")
        elif token.startswith("+"):
            shown.append(token[1:])
        else:
            shown.append(token)
    return f"{' '.join(shown)} = {answer}"


def _arithmetic_tokens(expr: str) -> list[str] | None:
    """Numbers and the four operators, at most six numbers. No powers or groups."""
    if not expr or len(expr) > 80:
        return None
    tokens: list[str] = []
    index = 0
    expect_number = True
    while index < len(expr):
        if expect_number:
            sign = ""
            if expr[index] in "+-":
                sign = expr[index]
                index += 1
            start = index
            saw_dot = False
            while index < len(expr) and (expr[index].isdigit() or expr[index] == "."):
                if expr[index] == ".":
                    if saw_dot:
                        return None
                    saw_dot = True
                index += 1
            if index == start:
                return None
            tokens.append(sign + expr[start:index])
            expect_number = False
            continue
        if expr[index] not in _DISPLAY_OPERATOR:
            return None
        tokens.append(expr[index])
        index += 1
        expect_number = True
    if expect_number or len(tokens) < 3 or len(tokens) > 11:
        return None
    return tokens


def written_fact_line(spec: ArithmeticWorkSpec) -> str:
    """One line for every operation: ``4 x 4 = 16``."""
    shown = f" {spec.operator} ".join(_shown_operand(token) for token in spec.operands)
    return f"{shown} = {final_answer(spec)}"


def format_direct_written_arithmetic(spec: ArithmeticWorkSpec, user_text: str) -> str:
    response = classify_math_response_intent(user_text)
    shown = (
        final_answer(spec)
        if response.mode == MathResponseMode.ANSWER_ONLY or response.wants_explanation
        else written_fact_line(spec)
    )
    answer = f"```answer\n{shown}\n```\n"
    if response.mode == MathResponseMode.ANSWER_ONLY:
        return answer
    # Small whole numbers are shown as objects to count when the user asks how ("explain
    # 3-3", "show the steps for 3-3"): "what's 2+2" from an adult got "2 fish and 2 more
    # make 4 fish" (2026-10-29).
    from app.modules.math.match.written import requests_written_method
    from app.modules.math.tools.direct_counting import counting_picture

    # A named written method ("8 + 7 using carrying") keeps its column trace.
    picture = (
        counting_picture(spec)
        if response.wants_explanation and not requests_written_method(user_text)
        else None
    )
    if picture is not None:
        body = json.dumps(picture.model_dump(), separators=(",", ":"), ensure_ascii=False)
        return f"```arithmetic\n{body}\n```\n\n{picture.speech}\n\n{answer}"
    # Operation chooses the mathematical procedure; response intent alone
    # chooses whether that procedure is visible.  Division is not implicitly
    # a request for a tutorial.
    if not response.wants_explanation:
        return answer
    body = json.dumps(spec.model_dump(), separators=(",", ":"))
    return f"```arithmetic\n{body}\n```\n\n{answer}"


def format_direct_fraction(spec: FractionWorkSpec, user_text: str) -> str:
    response = classify_math_response_intent(user_text)
    answer = f"```answer\n{spec.answer}\n```\n"
    if response.mode == MathResponseMode.ANSWER_ONLY:
        return answer
    if not response.wants_explanation:
        from app.modules.math.solve.fractions import fraction_working

        # ``3/4 divided by 2/5 = 3/4 times 5/2``, then the answer on its own line.
        working = fraction_working(spec)
        return f"{math_line(working)}\n\n{answer}" if working else answer
    body = json.dumps(spec.model_dump(), separators=(",", ":"))
    return f"```arithmetic\n{body}\n```\n\n{answer}"
