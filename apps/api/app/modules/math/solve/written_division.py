"""Exact long-division traces, including terminating decimal work."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP
from math import gcd
from typing import Literal, cast

from app.modules.math.schemas import ArithmeticWorkSpec, LongDivisionStep
from app.modules.math.solve.written_arithmetic_common import (
    MAX_DECIMAL_PLACES,
    MAX_DIVISION_DIGITS,
    format_scaled,
    scaled_number_parts,
)
from app.services.school_rounding import trim_zeros

_APPROX_DECIMAL_PLACES = 2
_ROUNDING_GUARD_PLACES = 1


def _plain_decimal(raw: str) -> str:
    return trim_zeros(raw) or "0"


def _terminating_places(numerator: int, denominator: int) -> int | None:
    common = gcd(numerator, denominator)
    denominator //= common
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    places = max(twos, fives)
    return places if denominator == 1 and places <= MAX_DECIMAL_PLACES else None


def _fixed_decimal(
    numerator: int,
    denominator: int,
    places: int,
    *,
    rounding: str,
) -> str:
    """Format a non-negative rational without depending on Decimal precision.

    The school arithmetic grammar accepts integers wider than Decimal's
    process-wide 28 significant digits.  Scaling the numerator and rounding
    the integer quotient keeps the calculation exact for every accepted
    operand size and avoids ``InvalidOperation`` during ``quantize``.
    """
    scale = 10**places
    scaled, remainder = divmod(numerator * scale, denominator)
    if rounding == ROUND_HALF_UP:
        if remainder * 2 >= denominator:
            scaled += 1
    elif rounding != ROUND_DOWN:
        raise ValueError(f"Unsupported division rounding mode: {rounding}")
    digits = str(scaled)
    if places == 0:
        return digits
    digits = digits.zfill(places + 1)
    return f"{digits[:-places]}.{digits[-places:]}"


def _division_steps(
    digits: str, divisor: int, extra_zeros: int
) -> tuple[list[LongDivisionStep], int]:
    remainder = 0
    current = 0
    steps: list[LongDivisionStep] = []
    working_digits = [int(char) for char in digits]
    working_digits.extend([0] * extra_zeros)
    for digit_index, digit in enumerate(working_digits):
        current = remainder * 10 + digit
        if not steps and current < divisor:
            remainder = current
            continue
        quotient_digit, remainder = divmod(current, divisor)
        next_digit = (
            working_digits[digit_index + 1] if digit_index + 1 < len(working_digits) else None
        )
        next_partial = str(remainder * 10 + next_digit) if next_digit is not None else None
        steps.append(
            LongDivisionStep(
                index=len(steps),
                column_end=digit_index,
                partial_dividend=str(current),
                quotient_digit=quotient_digit,
                product=str(quotient_digit * divisor),
                remainder=str(remainder),
                bring_down=next_digit,
                next_partial=next_partial,
            )
        )
    if not steps:
        # No partial dividend reached the divisor, so every column, including
        # appended placeholder zeros, folds into one zero step at the last
        # working column. Its remainder is the running value, not the bare input.
        steps.append(
            LongDivisionStep(
                index=0,
                column_end=max(0, len(working_digits) - 1),
                partial_dividend=str(remainder),
                quotient_digit=0,
                product="0",
                remainder=str(remainder),
            )
        )
    return steps, remainder


def build_long_division(
    left_token: str,
    right_token: str,
    expression: str,
    *,
    answer_mode: str | None = None,
) -> ArithmeticWorkSpec | None:
    left_parts = scaled_number_parts(left_token, max_digits=MAX_DIVISION_DIGITS)
    right_parts = scaled_number_parts(right_token, max_digits=MAX_DIVISION_DIGITS)
    if left_parts is None or right_parts is None:
        return None
    left, left_scale = left_parts
    right, right_scale = right_parts
    if right == 0:
        return None
    shift = right_scale
    working_scale = max(0, left_scale - shift)
    working_left = left * (10 ** max(0, shift - left_scale))
    divisor = right
    if divisor <= 0:
        return None
    working_text = _plain_decimal(format_scaled(working_left, working_scale))
    digits = working_text.replace(".", "")
    integer_digits = len(working_text.partition(".")[0])
    numerator = int(digits or "0")
    denominator = divisor * (10 ** max(0, len(digits) - integer_digits))
    # The solver's neutral default is the numerical quotient.  Callers that
    # need Euclidean quotient/remainder semantics must request them explicitly;
    # integer operands alone do not change what division means.
    requested_mode = answer_mode or "decimal"
    if requested_mode not in {"remainder", "fraction", "decimal", "round_up", "discard"}:
        return None
    places = _terminating_places(numerator, denominator)
    existing_fraction_places = max(0, len(digits) - integer_digits)
    integer_quotient, integer_remainder = divmod(numerator, denominator)
    repeating = places is None and requested_mode == "decimal"
    if integer_remainder == 0:
        quotient = str(integer_quotient)
        target_extra = 0
        answer = quotient
        answer_places = 0
        resolved_mode = "exact"
    elif requested_mode == "remainder":
        quotient = str(integer_quotient)
        target_extra = 0
        answer = f"{quotient} R{integer_remainder}"
        answer_places = 0
        resolved_mode = "remainder"
    elif requested_mode == "fraction":
        quotient = str(integer_quotient)
        target_extra = 0
        common = gcd(numerator, denominator)
        exact_numerator, exact_denominator = numerator // common, denominator // common
        answer = f"\\frac{{{exact_numerator}}}{{{exact_denominator}}}"
        answer_places = 0
        resolved_mode = "fraction"
    elif requested_mode in {"round_up", "discard"}:
        quotient = str(integer_quotient)
        target_extra = 0
        answer = str(integer_quotient + (1 if requested_mode == "round_up" else 0))
        answer_places = 0
        resolved_mode = requested_mode
    elif places is not None:
        quotient = _plain_decimal(
            _fixed_decimal(
                numerator,
                denominator,
                places,
                rounding=ROUND_DOWN,
            )
        )
        target_extra = max(0, places - existing_fraction_places)
        answer = quotient
        answer_places = places
        resolved_mode = "decimal"
    else:
        working_places = max(
            existing_fraction_places,
            _APPROX_DECIMAL_PLACES + _ROUNDING_GUARD_PLACES,
        )
        quotient = _fixed_decimal(
            numerator,
            denominator,
            working_places,
            rounding=ROUND_DOWN,
        )
        rounded = _fixed_decimal(
            numerator,
            denominator,
            _APPROX_DECIMAL_PLACES,
            rounding=ROUND_HALF_UP,
        )
        common = gcd(numerator, denominator)
        exact_numerator, exact_denominator = numerator // common, denominator // common
        answer = f"\\frac{{{exact_numerator}}}{{{exact_denominator}}}\\approx {rounded}"
        answer_places = _APPROX_DECIMAL_PLACES
        target_extra = max(0, working_places - existing_fraction_places)
        resolved_mode = "decimal"
    steps, remainder = _division_steps(digits, divisor, target_extra)
    division_display = working_text
    if target_extra:
        separator = "" if "." in division_display else "."
        division_display += separator + ("0" * target_extra)
    explanations: list[str] = []
    if shift:
        plural = "" if shift == 1 else "s"
        explanations.append(
            f"Move both decimal points {shift} place{plural} right: {working_text} ÷ {divisor}."
        )
    if target_extra:
        plural = "" if target_extra == 1 else "s"
        explanations.append(
            f"Append {target_extra} placeholder zero{plural} to continue the division."
        )
    for step in steps:
        text = (
            f"{step.partial_dividend} ÷ {divisor} gives {step.quotient_digit}. "
            f"Multiply: {step.quotient_digit} x {divisor} = {step.product}. "
            f"Subtract: {step.partial_dividend} - {step.product} = {step.remainder}."
        )
        if step.bring_down is not None:
            text += f" Bring down {step.bring_down} → {step.next_partial}."
        explanations.append(text)
    remainder_text = str(remainder)
    if resolved_mode == "remainder":
        explanations.append(
            f"Quotient: {integer_quotient}; remainder: {integer_remainder}. "
            f"Check: {divisor} x {integer_quotient} + {integer_remainder} = {numerator}."
        )
    elif resolved_mode == "fraction":
        explanations.append(f"Write the exact quotient as the simplified fraction {answer}.")
    elif resolved_mode == "round_up":
        explanations.append(
            f"There are {integer_quotient} full groups and {integer_remainder} left over, "
            f"so one more group is required: {answer}."
        )
    elif resolved_mode == "discard":
        explanations.append(
            f"There are {integer_quotient} complete groups; discard the remainder "
            f"{integer_remainder}."
        )
    elif repeating:
        explanations.append(
            "The decimal continues. Keep one guard digit, then round to "
            f"{_APPROX_DECIMAL_PLACES} decimal places."
        )
    else:
        explanations.append(f"Quotient: {quotient}.")
    return ArithmeticWorkSpec(
        operation="division",
        operator="÷",
        expression=expression,
        operands=[
            format_scaled(left, left_scale),
            format_scaled(right, right_scale),
        ],
        working_operands=[division_display, str(divisor)],
        answer=answer,
        decimal_places=answer_places or 0,
        quotient=quotient,
        remainder=(str(integer_remainder) if resolved_mode != "decimal" else remainder_text),
        answer_mode=cast(
            Literal["exact", "remainder", "fraction", "decimal", "round_up", "discard"],
            resolved_mode,
        ),
        division_steps=steps,
        explanations=explanations,
    )
