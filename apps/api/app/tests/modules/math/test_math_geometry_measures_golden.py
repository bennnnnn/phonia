"""Golden verified blocks: one closed school geometry question per operation, byte for byte.

``golden/geometry_measures.json`` holds what ``geometry_measure_block`` builds
for one prompt per solver, read by the real extraction: every field that
differs from an empty block. A deliberate layout change regenerates it:

    uv run python -m app.tests.modules.math.test_math_geometry_measures_golden
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.school.geometry_measures import _SOLVERS, geometry_measure_block
from app.services.solving import VerifiedMathBlock

FIXTURE = Path(__file__).with_name("golden") / "geometry_measures.json"

# The two operations that read an expression; the rest are in ``_SOLVERS``.
EXPRESSION_OPS = ("circle_centre_radius", "perpendicular_gradient")

PROMPTS: dict[str, str] = {
    "semicircle": "Find the perimeter of a semicircle with diameter 10 cm",
    "hemisphere": "volume of a hemisphere with radius 3",
    "circle_from_circumference": "find the radius of a circle with circumference 31.4",
    "circle_from_area": "find the diameter of a circle with area 50",
    "circle_from_circumference_pi": "find the area of a circle with circumference 10π",
    "circle_from_area_pi": "find the radius of a circle with area 16π",
    "square_from_diagonal": "What is the side of a square with diagonal 6 m?",
    "rhombus": "area of a rhombus with diagonals 6 and 8",
    "equilateral": "area of an equilateral triangle with side 6",
    "cube_diagonal": "diagonal of a cube with side 2",
    "cuboid_diagonal": "find the diagonal of a cuboid 3 by 4 by 12 cm",
    "extreme_angle": "a triangle has sides 7, 8 and 9, find the largest angle",
    "third_angle": "two angles of a triangle are 50 and 60 degrees, find the third angle",
    "isosceles": "an isosceles triangle has a base angle of 70 degrees, find the apex angle",
    "supplement": "find the supplement of 35 degrees",
    "complement": "find the complement of 28 degrees",
    "polygon_sides": (
        "how many sides does a regular polygon have if each interior angle is 140 degrees"
    ),
    "ladder": (
        "a 10 m ladder leans against a wall with its foot 6 m from the wall, "
        "how high up the wall does it reach"
    ),
    "circle_equation": "equation of a circle with center (2, -3) and radius 4",
    "circle_centre_radius": "find the center and radius of x^2 + y^2 - 4x + 6y - 3 = 0",
    "triangle_vertices": "area of a triangle with vertices (0, 0), (4, 0) and (0, 3)",
    "perpendicular_gradient": "gradient of a line perpendicular to y = 2x + 1",
    "perpendicular_bisector": "equation of the perpendicular bisector of (1, 2) and (5, 6)",
    "reflection_line": (
        "In a reflection, the image of the point P(3, 10) is P'(7, 2). "
        "Find the equation of the line of reflection."
    ),
    "sine_rule": "in triangle ABC, A = 40 degrees, B = 60 degrees, a = 10, find b",
    "right_angle_from_sides": (
        "in a right triangle the opposite side is 5 and the hypotenuse is 10, find the angle"
    ),
    "right_side_from_angle": (
        "a right triangle has an angle of 30 degrees and hypotenuse 12, find the opposite side"
    ),
}

_EMPTY = asdict(VerifiedMathBlock(text=""))


def _block(op: str) -> dict[str, Any]:
    intent = extract_math_intent(PROMPTS[op])
    assert intent is not None and intent.school_op == f"geometry_measure:{op}"
    block = geometry_measure_block(intent, [])
    assert block is not None
    changed = {name: value for name, value in asdict(block).items() if value != _EMPTY[name]}
    return json.loads(json.dumps(changed, ensure_ascii=False))


def _golden() -> dict[str, dict[str, Any]]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {row["op"]: row["block"] for row in rows}


@pytest.mark.parametrize("op", sorted(PROMPTS))
def test_geometry_measure_block_matches_golden(op: str) -> None:
    assert _block(op) == _golden()[op]


def test_every_operation_has_one_golden_prompt() -> None:
    assert set(PROMPTS) == set(_SOLVERS) | set(EXPRESSION_OPS)
    assert set(_golden()) == set(PROMPTS)


def _regenerate() -> None:
    rows = [{"op": op, "prompt": prompt, "block": _block(op)} for op, prompt in PROMPTS.items()]
    FIXTURE.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    _regenerate()
