"""Deterministic primary-school written arithmetic.

The trace is the teaching source of truth. Clients lay it out; they never
recalculate a carry, regroup, partial product, or long-division step.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.math.schemas import (
    AdditionColumn,
    ArithmeticWorkSpec,
    MultiplicationColumn,
    PartialProduct,
    SubtractionColumn,
)
from app.modules.math.solve.written_arithmetic_common import (
    format_scaled as _format_scaled,
)
from app.modules.math.solve.written_arithmetic_common import (
    number_parts as _number_parts,
)
from app.modules.math.solve.written_arithmetic_common import (
    place_name as _place_name,
)
from app.modules.math.solve.written_arithmetic_common import (
    scaled_integer as _scaled_integer,
)
from app.modules.math.solve.written_division import build_long_division

_OPERATOR = {
    "column_addition": ("addition", "+"),
    "column_subtraction": ("subtraction", "\u2212"),
    "column_multiplication": ("multiplication", "\u00d7"),
    "long_division": ("division", "\u00f7"),
}


def _aligned_operands(values: list[Decimal], scale: int) -> tuple[list[int], list[str]]:
    integers = [_scaled_integer(value, scale) for value in values]
    width = max(len(str(value)) for value in integers)
    rendered = [_format_scaled(value, scale) for value in integers]
    if scale:
        integer_width = width - scale
        rendered = [value.zfill(integer_width + scale + 1) for value in rendered]
    return integers, rendered


def _column_digits(value: int, width: int) -> list[int]:
    return [int(ch) for ch in str(value).zfill(width)][::-1]


def _addition(values: list[Decimal], scales: list[int], expression: str) -> ArithmeticWorkSpec:
    scale = max(scales)
    integers, operands = _aligned_operands(values, scale)
    total = sum(integers)
    width = max(*(len(str(value)) for value in integers), len(str(total)))
    digits = [_column_digits(value, width) for value in integers]
    carry = 0
    columns: list[AdditionColumn] = []
    explanations: list[str] = []
    for position in range(width):
        addends = [row[position] for row in digits]
        column_total = sum(addends) + carry
        result_digit, carry_out = column_total % 10, column_total // 10
        place = _place_name(position, scale)
        columns.append(
            AdditionColumn(
                position=position,
                place=place,
                addends=addends,
                carry_in=carry,
                result_digit=result_digit,
                carry_out=carry_out,
            )
        )
        terms = " + ".join(str(value) for value in (*addends, carry) if value or len(addends) == 0)
        if carry == 0:
            terms = " + ".join(str(value) for value in addends)
        action = (
            f" Write {result_digit}."
            if carry_out == 0
            else f" Write {result_digit}; carry {carry_out}."
        )
        explanations.append(f"{place.capitalize()}: {terms} = {column_total}.{action}")
        carry = carry_out
    return ArithmeticWorkSpec(
        operation="addition",
        operator="+",
        expression=expression,
        operands=operands,
        working_operands=operands,
        answer=_format_scaled(total, scale),
        decimal_places=scale,
        addition_columns=columns,
        explanations=explanations,
    )


def _subtraction(
    left: Decimal, right: Decimal, scales: tuple[int, int], expression: str
) -> ArithmeticWorkSpec | None:
    scale = max(scales)
    integers, operands = _aligned_operands([left, right], scale)
    top, bottom = integers
    if top < bottom:
        return None
    width = max(len(str(top)), len(str(bottom)))
    top_digits = _column_digits(top, width)
    original_top = top_digits.copy()
    bottom_digits = _column_digits(bottom, width)
    columns: list[SubtractionColumn] = []
    explanations: list[str] = []
    for position in range(width):
        working = top_digits[position]
        regrouped_from: list[str] = []
        if working < bottom_digits[position]:
            donor = position + 1
            while donor < width and top_digits[donor] == 0:
                donor += 1
            if donor >= width:
                return None
            top_digits[donor] -= 1
            regrouped_from.append(_place_name(donor, scale))
            for index in range(donor - 1, position, -1):
                top_digits[index] = 9
                regrouped_from.append(_place_name(index, scale))
            top_digits[position] += 10
            working = top_digits[position]
        result_digit = working - bottom_digits[position]
        place = _place_name(position, scale)
        columns.append(
            SubtractionColumn(
                position=position,
                place=place,
                top_digit=original_top[position],
                bottom_digit=bottom_digits[position],
                working_top=working,
                result_digit=result_digit,
                regrouped_from=regrouped_from,
            )
        )
        if regrouped_from:
            route = " → ".join(regrouped_from)
            lead = f"Regroup through {route}, making {working} in the {place}. "
        else:
            lead = ""
        explanations.append(
            f"{place.capitalize()}: {lead}{working} - {bottom_digits[position]} = {result_digit}."
        )
    regrouped = [str(value) for value in reversed(top_digits)]
    return ArithmeticWorkSpec(
        operation="subtraction",
        operator="\u2212",
        expression=expression,
        operands=operands,
        working_operands=operands,
        answer=_format_scaled(top - bottom, scale),
        decimal_places=scale,
        subtraction_columns=columns,
        regrouped_minuend=regrouped,
        explanations=explanations,
    )


def _multiplication(
    left: Decimal, right: Decimal, scales: tuple[int, int], expression: str
) -> ArithmeticWorkSpec:
    left_int = _scaled_integer(left, scales[0])
    right_int = _scaled_integer(right, scales[1])
    total_scale = scales[0] + scales[1]
    products: list[PartialProduct] = []
    explanations: list[str] = []
    multiplicand_digits = _column_digits(left_int, len(str(left_int)))
    for position, char in enumerate(reversed(str(right_int))):
        digit = int(char)
        unshifted = left_int * digit
        shifted = unshifted * (10**position)
        place = _place_name(position, 0)
        carry = 0
        columns: list[MultiplicationColumn] = []
        for multiplicand_position, multiplicand_digit in enumerate(multiplicand_digits):
            column_total = multiplicand_digit * digit + carry
            result_digit, carry_out = column_total % 10, column_total // 10
            columns.append(
                MultiplicationColumn(
                    position=multiplicand_position,
                    place=_place_name(multiplicand_position, 0),
                    multiplicand_digit=multiplicand_digit,
                    carry_in=carry,
                    result_digit=result_digit,
                    carry_out=carry_out,
                )
            )
            carry = carry_out
        products.append(
            PartialProduct(
                position=position,
                place=place,
                multiplier_digit=digit,
                unshifted_product=str(unshifted),
                shifted_product=str(shifted),
                columns=columns,
            )
        )
        carries = [str(column.carry_out) for column in columns if column.carry_out]
        carry_note = f" Carries: {', '.join(carries)}." if carries else ""
        plural = "" if position == 1 else "s"
        explanations.append(
            f"Multiply {left_int} by the {place} digit {digit}: {unshifted}; "
            f"shift {position} place{plural} → {shifted}.{carry_note}"
        )
    result_int = left_int * right_int
    if len(products) > 1:
        explanations.append(
            "Add the partial products: "
            + " + ".join(product.shifted_product for product in products)
            + f" = {result_int}."
        )
    if total_scale:
        plural = "" if total_scale == 1 else "s"
        explanations.append(
            f"The factors have {total_scale} decimal place{plural} altogether, "
            f"so place the decimal {total_scale} place{plural} from the right."
        )
    operands = [_format_scaled(left_int, scales[0]), _format_scaled(right_int, scales[1])]
    return ArithmeticWorkSpec(
        operation="multiplication",
        operator="\u00d7",
        expression=expression,
        operands=operands,
        working_operands=[str(left_int), str(right_int)],
        answer=_format_scaled(result_int, total_scale),
        decimal_places=total_scale,
        partial_products=products,
        explanations=explanations,
    )


def build_written_arithmetic_operands(
    tokens: list[str],
    school_op: str,
    expression: str,
    *,
    division_answer_mode: str | None = None,
) -> ArithmeticWorkSpec | None:
    """Build exact typed work for a complete two-to-six operand request."""
    operation = _OPERATOR.get(school_op)
    if school_op == "long_division":
        if len(tokens) != 2:
            return None
        return build_long_division(
            tokens[0],
            tokens[1],
            expression,
            answer_mode=division_answer_mode,
        )
    if operation is None or not 2 <= len(tokens) <= 6:
        return None
    parts = [_number_parts(token) for token in tokens]
    if any(part is None for part in parts):
        return None
    parsed = [part for part in parts if part is not None]
    values = [part[0] for part in parsed]
    scales = [part[1] for part in parsed]
    if school_op == "column_addition":
        return _addition(values, scales, expression)
    if len(values) != 2:
        return None
    left, right = values
    binary_scales = (scales[0], scales[1])
    if school_op == "column_subtraction":
        return _subtraction(left, right, binary_scales, expression)
    if school_op == "column_multiplication":
        return _multiplication(left, right, binary_scales, expression)
    return None
