"""A shape question is read at its printed numbers only when no measure is related,
changed or combined, and a solid's surface only when it is the closed total."""

from __future__ import annotations

import pytest

from app.modules.math.match.measure_relations import (
    measures_not_as_printed,
    surface_not_closed_total,
)


@pytest.mark.parametrize(
    "text",
    [
        "A cylinder has radius 3 cm and its height is 4 cm more than its radius.",
        "If the radius is doubled, find the new volume.",
        "Find the volume of a sphere with twice the radius.",
        "a parallelogram with base 8 cm and height 3 times its base",
        "a parallelogram with base 8 cm and height 3 * its base",
        "the area of a circle of radius 7 cm - the area of a circle of radius 3 cm",
        "Find its area if the length is increased by 2 cm.",
        "If the radius is 20% larger, find the area.",
        "inner radius 3 cm, outer radius 5 cm",
        "Find the sum of their areas.",
        "The sides of a rectangle are in the ratio 3:2.",
    ],
)
def test_a_related_changed_or_combined_measure_is_not_as_printed(text: str) -> None:
    assert measures_not_as_printed(text)


@pytest.mark.parametrize(
    "text",
    [
        "If the radius of a circle is 5 cm, find its area.",
        "Find the area of a rectangle 8 times 5 cm.",
        "Find the total surface area of a cylinder with radius 3 cm and height 5 cm.",
        "Two angles of a triangle are 50° and 60°. Find the remaining angle.",
        "Find the area of a right-angled triangle with legs 3 cm and 4 cm.",
        "Find the area of a half-cylinder's base of radius 2 cm.",
    ],
)
def test_one_shape_at_its_printed_numbers_is_read(text: str) -> None:
    assert not measures_not_as_printed(text)


@pytest.mark.parametrize(
    ("text", "asks_surface", "other"),
    [
        ("Find the lateral surface area of a cylinder", True, True),
        ("Find the curved surface area of a cone", True, True),
        ("Find the lateral area of a cylinder", False, True),
        ("Find the surface area of an open cylinder", True, True),
        ("Find the surface area of a box without a lid", True, True),
        ("Find the volume of an open box 10 cm by 8 cm by 5 cm", False, False),
        ("Find the total surface area of a cylinder", True, False),
        ("Find the surface area of a closed cylinder", True, False),
    ],
)
def test_only_the_closed_total_surface_is_worked(
    text: str, asks_surface: bool, other: bool
) -> None:
    assert surface_not_closed_total(text, asks_surface=asks_surface) is other
