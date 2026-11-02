"""Build a typed teaching picture from an internal payload."""

from __future__ import annotations

from app.modules.math.schemas.teaching import TeachingSpec
from app.modules.math.solve.teaching_algebra import (
    polynomial_division,
    transformation_spec,
    unit_circle_spec,
)
from app.modules.math.solve.teaching_data import (
    box_plot_spec,
    frequency_table_spec,
    histogram_spec,
    probability_tree_spec,
    scatter_spec,
    stem_leaf_spec,
)
from app.modules.math.solve.teaching_elementary import (
    array_spec,
    decimal_compare_spec,
    fraction_line_spec,
    number_bond_spec,
    number_line_move,
    place_digit_spec,
    place_value_spec,
    rounding_spec,
    ten_frame_spec,
)


def build_teaching(operation: str, payload: str) -> TeachingSpec | None:
    """Return the picture for one closed teaching operation, or None."""
    parts = payload.split("|")
    if operation == "place_value" and len(parts) == 1:
        return place_value_spec(parts[0])
    if operation == "base_ten" and len(parts) == 1:
        return place_value_spec(parts[0], blocks=True)
    if operation == "place_value" and len(parts) == 2:
        return place_digit_spec(parts[0], parts[1])
    if operation == "number_bond" and len(parts) == 3 and all(part.isdigit() for part in parts):
        whole, left, right = (int(part) for part in parts)
        return number_bond_spec(whole, left, right)
    if operation == "ten_frame" and len(parts) == 2 and all(part.isdigit() for part in parts):
        return ten_frame_spec(int(parts[0]), int(parts[1]))
    if operation == "array" and len(parts) == 2 and all(part.isdigit() for part in parts):
        return array_spec(int(parts[0]), int(parts[1]))
    if operation == "fraction_line" and len(parts) == 2 and all(part.isdigit() for part in parts):
        return fraction_line_spec(int(parts[0]), int(parts[1]))
    if operation == "decimal_compare" and len(parts) == 3:
        return decimal_compare_spec(parts[0], parts[1], parts[2])
    if operation == "round_place" and len(parts) == 2:
        return rounding_spec(parts[0], parts[1])
    if operation == "number_line_move" and len(parts) == 2 and _signed_move(parts[0], parts[1]):
        start, change = int(parts[0]), int(parts[1])
        return number_line_move(start, change, str(start + change))
    if operation in {"polynomial_division", "synthetic_division"} and len(parts) == 2:
        method = "synthetic" if operation == "synthetic_division" else "long"
        return polynomial_division(parts[0], parts[1], method)
    if operation == "unit_circle" and len(parts) == 1 and _signed_digits(parts[0]):
        return unit_circle_spec(int(parts[0]))
    if operation == "box_plot":
        return box_plot_spec(payload)
    if operation == "frequency_table":
        return frequency_table_spec(payload)
    if operation == "stem_leaf":
        return stem_leaf_spec(payload)
    if operation == "histogram":
        return histogram_spec(payload)
    if operation == "scatter":
        return scatter_spec(payload)
    if operation == "probability_tree" and len(parts) == 1:
        return probability_tree_spec(parts[0])
    if operation == "transformation" and len(parts) == 3:
        return transformation_spec(parts[0], parts[1], parts[2])
    return None


def _signed_digits(value: str) -> bool:
    digits = value[1:] if value.startswith("-") else value
    return bool(digits) and digits.isdigit()


def _signed_move(start: str, change: str) -> bool:
    return _signed_digits(start) and _signed_digits(change) and start.startswith("-")
