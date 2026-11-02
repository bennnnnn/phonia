"""Symbolic math via SymPy — server-side only."""

from __future__ import annotations

from app.modules.math.solve.calculus import (
    compute_limit,
    definite_integral,
    differentiate_at_point,
    differentiate_expression,
    evaluate_series_sum,
    integrate_definite,
    integrate_double,
    integrate_expression,
    integrate_triple,
)
from app.modules.math.solve.discrete import (
    compute_combinatorics,
    compute_matrix,
    compute_number_theory,
    compute_statistics,
    guess_variables,
)
from app.modules.math.solve.display import (
    format_verified_latex as format_verified_latex,
)
from app.modules.math.solve.equations import solve_equation
from app.modules.math.solve.expressions import (
    expand_expression,
    factor_expression,
    simplify_expression,
)
from app.modules.math.solve.extract_eq import (
    rejected_equality_chain,
    try_extract_compound_inequality_from_text,
    try_extract_equation_from_text,
    try_extract_equations_from_text,
    try_extract_inequality_from_text,
)
from app.modules.math.solve.geometry import (
    circle_geometry,
    format_geometry_decimal,
    parallelogram_geometry,
    rectangle_geometry,
    right_triangle_geometry,
    sector_geometry,
    sides_from_interior_angles,
    solid_geometry,
    square_geometry,
    trapezoid_geometry,
    triangle_geometry,
    triangle_sides_geometry,
)
from app.modules.math.solve.graph import (
    build_ellipse_graph_spec,
    number_line_spec_from_expr,
    sample_ellipse,
    sample_function,
    sample_parametric_curve,
    sample_polar_curve,
)
from app.modules.math.solve.inequalities import solve_compound_inequality, solve_inequality
from app.modules.math.solve.latex_normalize import (
    normalize_latex_to_sympy as normalize_latex_to_sympy,
)
from app.modules.math.solve.numeric import newton_method
from app.modules.math.solve.parse import (
    _SAFE_EXPR_CHARS as _SAFE_EXPR_CHARS,
)
from app.modules.math.solve.parse import (
    parse_expression as parse_expression,
)
from app.modules.math.solve.statistics import compute_bivariate_statistics
from app.modules.math.solve.systems import solve_system
from app.modules.math.solve.written_names import defined_variable
from app.services.solving import (
    SolveServiceError as SolveServiceError,
)

__all__ = [
    "_SAFE_EXPR_CHARS",
    "SolveServiceError",
    "build_ellipse_graph_spec",
    "circle_geometry",
    "compute_bivariate_statistics",
    "compute_combinatorics",
    "compute_limit",
    "compute_matrix",
    "compute_number_theory",
    "compute_statistics",
    "defined_variable",
    "definite_integral",
    "differentiate_at_point",
    "differentiate_expression",
    "evaluate_series_sum",
    "expand_expression",
    "factor_expression",
    "format_geometry_decimal",
    "format_verified_latex",
    "guess_variables",
    "integrate_definite",
    "integrate_double",
    "integrate_expression",
    "integrate_triple",
    "newton_method",
    "normalize_latex_to_sympy",
    "number_line_spec_from_expr",
    "parallelogram_geometry",
    "parse_expression",
    "rectangle_geometry",
    "rejected_equality_chain",
    "right_triangle_geometry",
    "sample_ellipse",
    "sample_function",
    "sample_parametric_curve",
    "sample_polar_curve",
    "sector_geometry",
    "sides_from_interior_angles",
    "simplify_expression",
    "solid_geometry",
    "solve_compound_inequality",
    "solve_equation",
    "solve_inequality",
    "solve_system",
    "square_geometry",
    "trapezoid_geometry",
    "triangle_geometry",
    "triangle_sides_geometry",
    "try_extract_compound_inequality_from_text",
    "try_extract_equation_from_text",
    "try_extract_equations_from_text",
    "try_extract_inequality_from_text",
]
