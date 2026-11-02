"""Place value, bonds, ten frames, arrays, decimals, and fraction pictures."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Literal

from app.modules.math.schemas.teaching import (
    ArraySpec,
    DecimalCompareSpec,
    FractionBarRow,
    FractionBarSpec,
    FractionLineSpec,
    NumberBondSpec,
    NumberLineMoveSpec,
    PlaceColumn,
    PlaceValueSpec,
    RoundingSpec,
    TenFrameSpec,
)
from app.services.school_rounding import format_places

_WHOLE_PLACES = (
    "ones",
    "tens",
    "hundreds",
    "thousands",
    "ten thousands",
    "hundred thousands",
    "millions",
)
_FRACTION_PLACES = ("tenths", "hundredths", "thousandths", "ten-thousandths")
_ROUND_PLACES = {
    "ones": 0,
    "tenths": 1,
    "hundredths": 2,
    "thousandths": 3,
    "tens": -1,
    "hundreds": -2,
    "thousands": -3,
}


def _split_number(number: str) -> tuple[str, str] | None:
    if not number or len(number) > 16 or number.count(".") > 1:
        return None
    if any(not (char.isdigit() or char == ".") for char in number):
        return None
    whole, dot, fraction = number.partition(".")
    if not whole.isdigit() or (dot and not fraction.isdigit()):
        return None
    if len(whole) > len(_WHOLE_PLACES) or len(fraction) > len(_FRACTION_PLACES):
        return None
    return whole, fraction


def _place_value(digit: int, power: int) -> str:
    value = Decimal(digit) * (Decimal(10) ** power)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def place_value_spec(
    number: str, *, blocks: bool = False, answer: str | None = None
) -> PlaceValueSpec | None:
    parts = _split_number(number)
    if parts is None:
        return None
    whole, fraction = parts
    columns: list[PlaceColumn] = []
    for index, char in enumerate(reversed(whole)):
        columns.append(
            PlaceColumn(
                place=_WHOLE_PLACES[index],
                digit=int(char),
                value=_place_value(int(char), index),
            )
        )
    columns.reverse()
    for index, char in enumerate(fraction):
        columns.append(
            PlaceColumn(
                place=_FRACTION_PLACES[index],
                digit=int(char),
                value=_place_value(int(char), -(index + 1)),
            )
        )
    pieces = [column.value for column in columns if column.digit != 0]
    expanded = " + ".join(pieces) if pieces else "0"
    show_blocks = blocks or (not fraction and int(whole) <= 999)
    hundreds = tens = ones = 0
    if not fraction and len(whole) <= 3:
        padded = whole.zfill(3)
        hundreds, tens, ones = (int(padded[0]), int(padded[1]), int(padded[2]))
        show_blocks = True
    speech_places = ", ".join(
        f"{column.digit} {column.place}" for column in columns if column.digit or not fraction
    )
    speech = f"{number} is {speech_places}, which is {expanded}."
    return PlaceValueSpec(
        number=number,
        columns=columns,
        expanded=expanded,
        show_blocks=show_blocks,
        hundreds=hundreds,
        tens=tens,
        ones=ones,
        answer=answer or expanded,
        speech=speech,
    )


def place_digit_spec(digit: str, number: str) -> PlaceValueSpec | None:
    if len(digit) != 1 or not digit.isdigit():
        return None
    spec = place_value_spec(number)
    if spec is None:
        return None
    matches = [column for column in spec.columns if column.digit == int(digit)]
    if len(matches) != 1:
        return None
    column = matches[0]
    speech = f"The {digit} is in the {column.place} place, so its value is {column.value}."
    return spec.model_copy(update={"answer": column.value, "speech": speech})


def number_bond_spec(
    whole: int, left: int, right: int, answer: str | None = None
) -> NumberBondSpec | None:
    if not 0 <= left <= 20 or not 0 <= right <= 20 or left + right != whole or whole > 20:
        return None
    return NumberBondSpec(
        whole=whole,
        left=left,
        right=right,
        answer=answer or str(whole),
        speech=f"{whole} is {left} plus {right}.",
    )


def ten_frame_spec(first: int, second: int, answer: str | None = None) -> TenFrameSpec | None:
    if not 0 <= first <= 9 or not 0 <= second <= 9:
        return None
    total = first + second
    make_ten = total >= 10
    fill = 10 - first if make_ten else second
    leftover = second - fill
    if make_ten:
        speech = (
            f"{first} plus {fill} makes 10, and {leftover} remain, "
            f"so 10 plus {leftover} is {total}."
        )
    else:
        speech = f"{first} plus {second} fills {total} cells in the ten frame."
    return TenFrameSpec(
        first=first,
        second=second,
        make_ten=make_ten,
        fill=fill,
        leftover=leftover,
        total=total,
        answer=answer or str(total),
        speech=speech,
    )


def array_spec(rows: int, columns: int, answer: str | None = None) -> ArraySpec | None:
    if not 1 <= rows <= 10 or not 1 <= columns <= 10:
        return None
    product = rows * columns
    return ArraySpec(
        rows=rows,
        columns=columns,
        product=product,
        answer=answer or str(product),
        speech=f"{rows} rows of {columns} makes {product}.",
    )


def number_line_move(start: int, change: int, answer: str) -> NumberLineMoveSpec | None:
    end = start + change
    if abs(start) > 20 or abs(change) > 20 or abs(end) > 24:
        return None
    # Bonds and columns own a non-negative start. Bare subtraction stays a chip.
    if start >= 0 or change <= 0:
        return None
    low = min(start, end) - 1
    high = max(start, end) + 1
    speech = f"Start at {start} and move {change} to the right. You land on {end}."
    return NumberLineMoveSpec(
        start=start,
        change=change,
        end=end,
        low=low,
        high=high,
        answer=answer,
        speech=speech,
    )


def number_line_for_expr(expr: str, answer: str) -> NumberLineMoveSpec | None:
    compact = expr.replace(" ", "")
    if compact.count("+") + compact.count("-") != 1 and not (
        compact.startswith("-") and compact[1:].count("+") + compact[1:].count("-") == 1
    ):
        return None
    if any(char in compact for char in "*/^()."):
        return None
    sign_at = None
    for index, char in enumerate(compact):
        if char in "+-" and index > 0:
            sign_at = index
    if sign_at is None:
        return None
    left, right = compact[:sign_at], compact[sign_at + 1 :]
    if not _signed_int(left) or not right.isdigit():
        return None
    start = int(left)
    change = int(right) if compact[sign_at] == "+" else -int(right)
    return number_line_move(start, change, answer)


def _signed_int(value: str) -> bool:
    digits = value[1:] if value.startswith("-") else value
    return bool(digits) and digits.isdigit() and len(digits) <= 2


def fraction_line_spec(numerator: int, denominator: int) -> FractionLineSpec | None:
    if denominator < 1 or denominator > 12 or not 0 <= numerator <= denominator:
        return None
    speech = f"{numerator}/{denominator} sits {numerator} of {denominator} equal steps from 0 to 1."
    return FractionLineSpec(
        numerator=numerator,
        denominator=denominator,
        answer=rf"\frac{{{numerator}}}{{{denominator}}}",
        speech=speech,
    )


def fraction_bar_spec(operation: str, operands: list[str], answer: str) -> FractionBarSpec | None:
    if operation not in {"add", "subtract"} or len(operands) != 2:
        return None
    parsed = [_fraction(value) for value in operands]
    if any(item is None for item in parsed):
        return None
    left, right = parsed[0], parsed[1]
    if left is None or right is None:
        return None
    slots = _lcm(left.denominator, right.denominator)
    if slots > 12:
        return None
    left_filled = left.numerator * (slots // left.denominator)
    right_filled = right.numerator * (slots // right.denominator)
    if operation == "add":
        result = left_filled + right_filled
    else:
        result = left_filled - right_filled
    if result < 0 or result > slots:
        return None
    rows = [
        FractionBarRow(label=operands[0], filled=left_filled, slots=slots),
        FractionBarRow(label=operands[1], filled=right_filled, slots=slots),
        FractionBarRow(label=answer, filled=result, slots=slots),
    ]
    speech = f"In {slots} equal parts, the fractions combine to {result}/{slots}."
    return FractionBarSpec(rows=rows, answer=answer, speech=speech)


def _fraction(value: str) -> Fraction | None:
    numerator, separator, denominator = value.partition("/")
    if not separator or not numerator.isdigit() or not denominator.isdigit():
        return None
    if int(denominator) == 0:
        return None
    return Fraction(int(numerator), int(denominator))


def _lcm(left: int, right: int) -> int:
    return left * right // _gcd(left, right)


def _gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return left


def decimal_compare_spec(left: str, right: str, ask: str) -> DecimalCompareSpec | None:
    left_parts = _split_number(left)
    right_parts = _split_number(right)
    if left_parts is None or right_parts is None or "." not in left + right:
        return None
    places = max(len(left_parts[1]), len(right_parts[1]), 1)
    whole = max(len(left_parts[0]), len(right_parts[0]))
    headers = [_WHOLE_PLACES[index] for index in range(whole - 1, -1, -1)]
    headers.extend(_FRACTION_PLACES[:places])
    left_digits = _aligned_digits(left_parts, whole, places)
    right_digits = _aligned_digits(right_parts, whole, places)
    left_value, right_value = Decimal(left), Decimal(right)
    relation: Literal["<", ">", "="]
    if left_value < right_value:
        relation = "<"
        larger, smaller = right, left
    elif left_value > right_value:
        relation = ">"
        larger, smaller = left, right
    else:
        relation = "="
        larger = smaller = left
    if relation == "=":
        answer = f"{left} = {right}" if ask == "compare" else left
        speech = f"{left} and {right} match in every place."
    else:
        difference = next(
            header
            for header, left_digit, right_digit in zip(
                headers, left_digits, right_digits, strict=True
            )
            if left_digit != right_digit
        )
        if ask == "smaller":
            answer = smaller
            outcome = f"{smaller} is smaller"
        elif ask == "larger":
            answer = larger
            outcome = f"{larger} is larger"
        else:
            answer = f"{left} {relation} {right}"
            outcome = f"{left} {relation} {right}"
        speech = f"The first difference is the {difference} place, so {outcome}."
    return DecimalCompareSpec(
        left=left,
        right=right,
        headers=headers,
        left_digits=left_digits,
        right_digits=right_digits,
        relation=relation,
        answer=answer,
        speech=speech,
    )


def _aligned_digits(parts: tuple[str, str], whole: int, places: int) -> list[str]:
    integer, fraction = parts
    return list(integer.zfill(whole) + fraction.ljust(places, "0"))


def rounding_spec(value: str, place: str) -> RoundingSpec | None:
    places = _ROUND_PLACES.get(place)
    if places is None or _split_number(value) is None:
        return None
    rendered = format_places(value, places)
    place_digit, follower = _rounding_digits(value, places)
    direction: Literal["up", "down"] = "up" if follower >= 5 else "down"
    speech = (
        f"The {place} digit is {place_digit} and the next digit is {follower}, "
        f"so round {direction}. {value} rounds to {rendered}."
    )
    return RoundingSpec(
        value=value,
        place=place,
        place_digit=place_digit,
        follower=follower,
        direction=direction,
        rounded=rendered,
        answer=rendered,
        speech=speech,
    )


def _rounding_digits(value: str, places: int) -> tuple[int, int]:
    """Return the digit in the chosen place and the digit that decides it."""
    whole, _dot, fraction = value.partition(".")
    digits = list(whole + fraction)
    point = len(whole)
    # Ones sit just left of the decimal point. Positive places step right.
    place_index = point + places - 1
    follower_index = place_index + 1
    place_digit = int(digits[place_index]) if 0 <= place_index < len(digits) else 0
    follower = int(digits[follower_index]) if 0 <= follower_index < len(digits) else 0
    return place_digit, follower
