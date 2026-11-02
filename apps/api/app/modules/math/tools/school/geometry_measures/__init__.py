"""Closed school geometry the shape solvers do not read.

Each rule reads one stated question shape and nothing else, and its solver
returns the worked layout (Given, Required, Formula, Substitution) and the answer:

- circles from their circumference or area; semicircles; hemispheres
- a square from its diagonal; a rhombus from its diagonals; equilateral triangles
- cube and cuboid diagonals
- angle facts: the third angle, isosceles triangles, supplements and complements,
  the number of sides from an angle
- the sine rule; right-triangle trigonometry; a ladder against a wall
- circles, lines and triangles on coordinates; the line of reflection taking a point to its image

Before this, "the radius of a circle with circumference 31.4" was read as a
circle of radius 31.4, and "the area of a semicircle" was a whole circle's.

``rules`` reads the question; ``circles``, ``polygons``, ``triangle_trig`` and
``coordinates`` solve it in the layout ``working`` defines.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school.geometry_measures.circles import (
    _circle_from_area,
    _circle_from_area_pi,
    _circle_from_circumference,
    _circle_from_circumference_pi,
    _hemisphere,
    _semicircle,
)
from app.modules.math.tools.school.geometry_measures.coordinates import (
    _circle_centre_radius,
    _circle_equation,
    _perpendicular_bisector,
    _perpendicular_gradient,
    _triangle_vertices,
    reflection_line,
)
from app.modules.math.tools.school.geometry_measures.polygons import (
    _complement,
    _cube_diagonal,
    _cuboid_diagonal,
    _equilateral,
    _isosceles,
    _polygon_sides,
    _rhombus,
    _square_from_diagonal,
    _supplement,
    _third_angle,
)
from app.modules.math.tools.school.geometry_measures.rules import extract_geometry_measure_intent
from app.modules.math.tools.school.geometry_measures.triangle_trig import (
    _extreme_angle,
    _ladder,
    _right_angle_from_sides,
    _right_side_from_angle,
    _sine_rule,
)
from app.modules.math.tools.school.geometry_measures.working import _Solved
from app.services.workout import Workout, render_workout

__all__ = [
    "extract_geometry_measure_intent",
    "geometry_measure_block",
    "is_geometry_measure",
]

_SOLVERS: dict[str, Callable[[list[float], list[str]], _Solved | None]] = {
    "semicircle": _semicircle,
    "hemisphere": _hemisphere,
    "circle_from_circumference": _circle_from_circumference,
    "circle_from_area": _circle_from_area,
    "circle_from_circumference_pi": _circle_from_circumference_pi,
    "circle_from_area_pi": _circle_from_area_pi,
    "square_from_diagonal": _square_from_diagonal,
    "rhombus": _rhombus,
    "equilateral": _equilateral,
    "cube_diagonal": _cube_diagonal,
    "cuboid_diagonal": _cuboid_diagonal,
    "extreme_angle": _extreme_angle,
    "third_angle": _third_angle,
    "isosceles": _isosceles,
    "supplement": _supplement,
    "complement": _complement,
    "polygon_sides": _polygon_sides,
    "ladder": _ladder,
    "circle_equation": _circle_equation,
    "triangle_vertices": _triangle_vertices,
    "perpendicular_bisector": _perpendicular_bisector,
    "reflection_line": reflection_line,
    "sine_rule": _sine_rule,
    "right_angle_from_sides": _right_angle_from_sides,
    "right_side_from_angle": _right_side_from_angle,
}


def is_geometry_measure(school_op: str | None) -> bool:
    return bool(school_op and school_op.startswith("geometry_measure:"))


def geometry_measure_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    op = (intent.school_op or "").partition(":")[2]
    numbers = list(intent.stats_numbers or [])
    words = [word for word in (intent.trial_outcome or "").split("|") if word]
    try:
        if op == "circle_centre_radius":
            solved = _circle_centre_radius(intent)
        elif op == "perpendicular_gradient":
            solved = _perpendicular_gradient(intent, words)
        else:
            solver = _SOLVERS.get(op)
            solved = solver(numbers, words) if solver is not None else None
    except (ValueError, ZeroDivisionError, IndexError):
        return None
    if solved is None:
        return None
    lines.extend(row.split(" — ")[0] for row in solved.substitution)
    block = finish_with_answer(lines, solved.answer)
    working = render_workout(
        Workout(
            given=solved.given,
            find=solved.find,
            formula=solved.formula,
            substitution=solved.substitution,
        ),
        solved.answer,
    )
    return replace(block, worked_reply=working)
