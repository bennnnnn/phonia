"""The lexical signals that a chat line is a problem for pre-stream SymPy.

Each is a named predicate over the prepared line and its lowercase form. None of
them runs an extractor: the gate asks the extractors only after every signal
here has declined (``tools/extractors/detection.py``).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.math.match.arithmetic import bare_arithmetic_expr
from app.modules.math.match.calculus import calc_object, calc_op, parse_limit, parse_series
from app.modules.math.match.coordinate_vector import is_closed_coordinate_vector_request
from app.modules.math.match.dimensions import (
    first_dim_pair,
    geometry_dim_context,
    has_draw_shape,
    measure_after,
    two_numbers_after,
)
from app.modules.math.match.discrete import (
    combinatorics_signal,
    gcd_lcm_list_signal,
    matrix_signal,
    number_theory_signal,
    stats_signal,
)
from app.modules.math.match.geometry import (
    parse_solid,
    trapezoid_dimensions,
    triangle_angles_signal,
    triangle_sides_signal,
)
from app.modules.math.match.graph import bare_coord, graph_expr, plot_point, vertical_line_x
from app.modules.math.match.literal_geometry import parse_named_rectangle_request
from app.modules.math.match.scan import (
    bare_equation_system,
    has_algebraic_equation,
    has_math_keyword,
    inequality_signal,
)
from app.modules.math.match.statistics import bivariate_stats_signal
from app.modules.math.match.units import strip_geometry_length_units
from app.modules.math.match.written import spoken_power_request, written_arithmetic_request
from app.services.text_match import has_equation, word_index

NeedSignal = Callable[[str, str], bool]
"""``(cleaned, lower) -> bool``: one reason a prepared line is maths."""

_DRAWN_SHAPES = (
    "rectangle",
    "right triangle",
    "square",
    "circle",
    "trapezoid",
    "trapezium",
    "parallelogram",
    "sector",
    "pie slice",
    "triangle",
)
# "make r the subject of A = pi r^2" is "solve A = pi r^2 for r".
_MAKE_SUBJECT = re.compile(r"\bmake\s+[a-zA-Z]\s+the\s+subject\s+of\s+\S.*=", re.IGNORECASE)
_COMPLEX_ARITHMETIC = re.compile(
    r"(?:(?:what\s+is|what's|whats|simplify|evaluate|compute|calculate|expand|multiply)\s+)?"
    r"[\d\s+\-*/().^i]+[?.]?"
)
_IMAGINARY_UNIT = re.compile(r"\d\s*i\b|\bi\s*[)^]")


def has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _base_and_height(cleaned: str) -> bool:
    base, height = measure_after(cleaned, "base"), measure_after(cleaned, "height")
    return base is not None and height is not None


def named_rectangle(cleaned: str, lower: str) -> bool:
    """A rectangle named by its corners: ``rectangle ABCD with AB = 5 and BC = 3``."""
    return parse_named_rectangle_request(cleaned) is not None


def drawn_shape(cleaned: str, lower: str) -> bool:
    """A draw, show or sketch verb with a shape."""
    return any(has_draw_shape(cleaned, shape) for shape in _DRAWN_SHAPES)


def shape_with_measures(cleaned: str, lower: str) -> bool:
    """A shape with the measures that size it.

    A shape word alone must not trigger verified geometry: bare "what is a
    trapezoid?" used to invent dimensions and sell them as SymPy-verified.
    """
    if ("trapezoid" in lower or "trapezium" in lower) and trapezoid_dimensions(cleaned):
        return True
    if "parallelogram" in lower and _base_and_height(cleaned):
        return True
    # "sector" alone is an ordinary English word ("the tech sector") far more
    # often than a circle sector: require geometry context AND both radius and
    # angle (partial dims used to invent the missing one).
    if (
        "sector" in lower
        and any(k in lower for k in ("circle", "radius", "pie", "arc"))
        and measure_after(cleaned, "radius") is not None
        and measure_after(cleaned, "angle") is not None
    ):
        return True
    if triangle_sides_signal(cleaned) is not None or triangle_angles_signal(cleaned) is not None:
        return True
    if parse_solid(cleaned) is not None:
        return True
    if geometry_dim_context(lower):
        dimensions = strip_geometry_length_units(cleaned)
        if first_dim_pair(dimensions) is not None:
            return True
        if "rectangle" in lower and (
            two_numbers_after(dimensions, "sides") is not None
            or two_numbers_after(dimensions, "side lengths") is not None
        ):
            return True
    if (
        "circle" in lower
        and "sector" not in lower
        and "pie slice" not in lower
        and (
            measure_after(cleaned, "radius") is not None
            or measure_after(cleaned, "diameter") is not None
        )
    ):
        return True
    if "triangle" in lower and _base_and_height(cleaned):
        return True
    return "right triangle" in lower and (
        first_dim_pair(cleaned) is not None
        or two_numbers_after(cleaned, "legs") is not None
        or two_numbers_after(cleaned, "leg") is not None
    )


def keyword_equation(cleaned: str, lower: str) -> bool:
    """An equation and a maths keyword: ``solve 2x + 3 = 7``."""
    return has_equation(cleaned) and has_math_keyword(lower)


def bare_equation(cleaned: str, lower: str) -> bool:
    """An equation, or a system of them, typed with no verb: ``2x+3=7``, ``y=x^2``.

    A standalone single-letter variable is required, so prose with an ``=``
    ("meeting = 3pm") is excluded.
    """
    return has_algebraic_equation(cleaned) or bool(bare_equation_system(cleaned))


def bare_arithmetic(cleaned: str, lower: str) -> bool:
    """Digits and operators with no leftover English, or the sum written in words.

    Without this, ``first_dim_pair`` read ``8*2`` inside ``8-8*2`` as a
    rectangle size, extraction found nothing, and the reply stamped
    *Couldn't verify this with SymPy.* under a correct -8.
    """
    return (
        bare_arithmetic_expr(cleaned) is not None
        or written_arithmetic_request(cleaned) is not None
        or spoken_power_request(cleaned) is not None
    )


def complex_arithmetic(cleaned: str, lower: str) -> bool:
    """``(2 + 3i)(1 - i)``: numbers, operators, brackets and i, nothing else."""
    return bool(_COMPLEX_ARITHMETIC.fullmatch(lower) and _IMAGINARY_UNIT.search(lower))


def make_subject(cleaned: str, lower: str) -> bool:
    """``make r the subject of A = pi r^2``."""
    return _MAKE_SUBJECT.search(cleaned) is not None


def coordinate_vector(cleaned: str, lower: str) -> bool:
    """``magnitude of the vector (3, 4)``, ``dot product of (1, 2, 3) and (4, 5, 6)``."""
    return is_closed_coordinate_vector_request(cleaned)


def graph_request(cleaned: str, lower: str) -> bool:
    """A point, a curve or a vertical line to plot."""
    return (
        bare_coord(cleaned) is not None
        or plot_point(cleaned) is not None
        or graph_expr(cleaned) is not None
        or vertical_line_x(cleaned) is not None
    )


def inequality(cleaned: str, lower: str) -> bool:
    """A one-variable inequality for a number line: ``x > 4``, ``1 < x < 5``.

    The gate used to require a maths keyword, so bare "X>4" never reached the
    extractor and the model emitted "Could not render that diagram."
    """
    return inequality_signal(cleaned)


def calculus(cleaned: str, lower: str) -> bool:
    """A calculus verb with something to act on, a limit or a series.

    The verb alone is English too: "differentiate between weather and
    climate", "integrate Slack with Notion", "simplify it".
    """
    if calc_op(cleaned) is not None and calc_object(cleaned):
        return True
    return parse_limit(cleaned) is not None or parse_series(cleaned) is not None


def numerical_method(cleaned: str, lower: str) -> bool:
    """Newton's method or a numerical root, with numbers."""
    return has_digit(cleaned) and (
        word_index(lower, "newton") != -1
        or word_index(lower, "numerically") != -1
        or word_index(lower, "root of") != -1
    )


def solve_request(cleaned: str, lower: str) -> bool:
    """Solve, find, roots or evaluate, with the maths to act on.

    "find x when 2x = 10" is a solve ask like "solve ...". An equation is
    required so prose "find the right moment" is not pulled into SymPy. "roots
    of the tree" and "zeros of the array" have no digit; the extractor rewrites
    "roots of x^2 - 4" to "solve x^2 - 4 = 0".
    """
    if ("solve" in lower or "find" in lower) and has_equation(cleaned):
        return True
    if not has_digit(cleaned):
        return False
    if "roots of" in lower or "zeros of" in lower:
        return True
    return "evaluate" in lower and any(op in cleaned for op in ("+", "-", "*", "/", "^", "("))


def discrete(cleaned: str, lower: str) -> bool:
    """Statistics, counting, number theory or a matrix, with the data."""
    return (
        stats_signal(cleaned) is not None
        or bivariate_stats_signal(cleaned) is not None
        or combinatorics_signal(cleaned) is not None
        or number_theory_signal(cleaned) is not None
        or gcd_lcm_list_signal(cleaned) is not None
        or matrix_signal(cleaned) is not None
    )
