"""Linear (non-regex / digit-only-regex) matchers for math intent heuristics.

Kept separate so CodeQL py/polynomial-redos cannot taint user chat text into
nested optional/``\\s`` regex pumps in ``math_tools``.
"""

from __future__ import annotations

from app.modules.math.match.arithmetic import bare_arithmetic_expr
from app.modules.math.match.bare_expression import bare_expression_reply
from app.modules.math.match.calculus import (
    calc_op,
    integral_bounds,
    parse_limit,
    parse_series,
)
from app.modules.math.match.dimensions import (
    first_dim_pair,
    first_dim_triple,
    geometry_dim_context,
    has_draw_shape,
    measure_after,
    number_after,
    two_numbers_after,
)
from app.modules.math.match.discrete import (
    combinatorics_signal,
    matrix_signal,
    number_theory_signal,
    stats_signal,
)
from app.modules.math.match.geometry import (
    classify_solid_shape,
    geometry_deferred_for_algebra,
    parse_solid,
    pi_form_or_value_set,
    pi_value_set,
    trapezoid_dimensions,
    triangle_angles_signal,
    triangle_sides_signal,
)
from app.modules.math.match.graph import (
    bare_coord,
    graph_domain,
    graph_expr,
    graph_expr_pair,
    plot_point,
    vertical_line_x,
)
from app.modules.math.match.letter_runs import looks_like_math_expr
from app.modules.math.match.needs import needs_symbolic
from app.modules.math.match.scan import has_equation, has_math_keyword, prepare
from app.modules.math.match.written import (
    division_answer_mode,
    spoken_power_request,
    written_addition_request,
    written_arithmetic_request,
)

__all__ = [
    "bare_arithmetic_expr",
    "bare_coord",
    "bare_expression_reply",
    "calc_op",
    "classify_solid_shape",
    "combinatorics_signal",
    "division_answer_mode",
    "first_dim_pair",
    "first_dim_triple",
    "geometry_deferred_for_algebra",
    "geometry_dim_context",
    "graph_domain",
    "graph_expr",
    "graph_expr_pair",
    "has_draw_shape",
    "has_equation",
    "has_math_keyword",
    "integral_bounds",
    "looks_like_math_expr",
    "matrix_signal",
    "measure_after",
    "needs_symbolic",
    "number_after",
    "number_theory_signal",
    "parse_limit",
    "parse_series",
    "parse_solid",
    "pi_form_or_value_set",
    "pi_value_set",
    "plot_point",
    "prepare",
    "spoken_power_request",
    "stats_signal",
    "trapezoid_dimensions",
    "triangle_angles_signal",
    "triangle_sides_signal",
    "two_numbers_after",
    "vertical_line_x",
    "written_addition_request",
    "written_arithmetic_request",
]
