"""Tests for SymPy math service."""

from __future__ import annotations

import math
import time

import pytest

from app.modules.math import solve as math_solve
from app.modules.math.schemas import (
    EquationInput,
    GraphBlockSpec,
    GraphSampleInput,
    NewtonMethodInput,
    NumberLineInterval,
    RectangleGeometryInput,
    SystemOfEquationsInput,
)
from app.modules.math.solve import SolveServiceError
from app.modules.math.solve.graph import parse_ellipse_relation


@pytest.mark.parametrize(
    "lhs, rhs, expected_count",
    [
        ("x**2 + 2", "6", 2),
        ("2*x + 4", "10", 1),
    ],
)
def test_solve_equation(lhs: str, rhs: str, expected_count: int) -> None:
    result = math_solve.solve_equation(EquationInput(lhs=lhs, rhs=rhs, variables=["x"]))
    assert len(result.solutions_latex) == expected_count
    assert "x" in result.solutions_latex[0]


def test_normalize_latex_frac_and_abs() -> None:
    assert math_solve.normalize_latex_to_sympy(r"\frac{1}{2}x") == "((1)/(2))x"
    assert math_solve.normalize_latex_to_sympy(r"\left|x-1\right|") == "Abs(x-1)"
    assert math_solve.normalize_latex_to_sympy(r"\frac{a}{b}+\frac{c}{d}") == "((a)/(b))+((c)/(d))"
    assert math_solve.normalize_latex_to_sympy("|x-2|") == "Abs(x-2)"
    assert math_solve.normalize_latex_to_sympy("|x-2|<5") == "Abs(x-2)<5"


@pytest.mark.wall_clock
@pytest.mark.parametrize("tail", ["x", r"\frac{1}{x}", "½x"])
def test_mixed_number_patterns_stay_linear_on_long_digit_runs(tail: str) -> None:
    """CodeQL: polynomial regex on uncontrolled data. A whole part of unbounded length
    retried the same run of digits from every position, quadratic in its length."""
    from app.modules.math.solve.latex_normalize import _MIXED_GLYPH_RE, _MIXED_LATEX_RE

    adversarial = "0" * 200_000 + tail
    started = time.perf_counter()
    _MIXED_LATEX_RE.sub("", adversarial)
    _MIXED_GLYPH_RE.sub("", adversarial)
    # A quadratic pattern takes minutes on 200k digits; a generous ceiling for slow CI.
    assert time.perf_counter() - started < 2.0
    assert math_solve.normalize_latex_to_sympy(r"2\frac{1}{2}") == "(2+(1)/(2))"


def test_normalize_latex_inline_math_and_braced_power() -> None:
    """Composer ``$x^{6}=1$`` used to fail the ASCII equation walker (``$``/``{}``)."""
    assert math_solve.normalize_latex_to_sympy("$x^{6}=1$") == "x^6=1"
    assert math_solve.normalize_latex_to_sympy(r"^{x}^{2}") == "x^2"
    assert math_solve.try_extract_equations_from_text("$x^{6}=1$") == [("x^6", "1")]


def test_normalize_unicode_ops_to_ascii() -> None:
    """OCR/homework glyphs must ascii-ize before the allowlist — not widen it."""
    mul = "2\u00d7x+3"
    assert math_solve.normalize_latex_to_sympy(mul) == "2*x+3"
    assert math_solve.normalize_latex_to_sympy("6\u00f72") == "6/2"
    assert math_solve.normalize_latex_to_sympy("2\u2212x") == "2-x"
    assert math_solve._SAFE_EXPR_CHARS.match("2\u00d73") is None
    result = math_solve.solve_equation(EquationInput(lhs=mul, rhs="7", variables=["x"]))
    assert len(result.solutions_latex) == 1
    assert "2" in result.solutions_latex[0]


def test_normalize_unicode_scripts_and_glyphs() -> None:
    """Superscript/subscript digits, √, π, vulgar fractions → ASCII/SymPy."""
    assert math_solve.normalize_latex_to_sympy("x\u00b2") == "x**2"
    assert math_solve.normalize_latex_to_sympy("a\u2081") == "a_1"
    assert math_solve.normalize_latex_to_sympy("x\u00b9\u2070") == "x**(10)"
    # Bracketed, so a letter beside π stays a factor: sin(πx) is sin(pi*x), not sin(pix).
    assert math_solve.normalize_latex_to_sympy("\u03c0") == "(pi)"
    assert str(math_solve.parse_expression("sin(\u03c0x)", ["x"])) == "sin(pi*x)"
    assert str(math_solve.parse_expression("\u03c0r^2", ["r"])) == "pi*r**2"
    assert math_solve.normalize_latex_to_sympy("\u221a(4)") == "sqrt(4)"
    assert math_solve.normalize_latex_to_sympy("\u221a9") == "sqrt(9)"
    assert math_solve.normalize_latex_to_sympy("\u221ax") == "sqrt(x)"
    assert math_solve.normalize_latex_to_sympy("\u00bd") == "(1)/(2)"
    assert math_solve.normalize_latex_to_sympy(r"6\sqrt{4}") == "6*sqrt(4)"
    assert math_solve.normalize_latex_to_sympy(r"\sqrt[6]{4}") == "(4)**(1/(6))"
    parsed = math_solve.parse_expression("x\u00b2 + 1", ["x"])
    assert parsed is not None


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("x^2 + y^2 = 1", (1.0, 1.0)),
        ("x**2+y**2=25", (5.0, 5.0)),
        ("x**2/9 + y**2/4 = 1", (3.0, 2.0)),
        ("(x/3)**2+(y/2)**2=1", (3.0, 2.0)),
        ("y**2 + x**2 = 1", (1.0, 1.0)),
        ("x**2", None),
        ("x**2 + y**2 = 0", None),
    ],
)
def test_parse_ellipse_relation(expr: str, expected: tuple[float, float] | None) -> None:
    got = parse_ellipse_relation(expr)
    if expected is None:
        assert got is None
    else:
        assert got is not None
        assert got[0] == pytest.approx(expected[0])
        assert got[1] == pytest.approx(expected[1])


def test_sample_ellipse_closes_the_polyline() -> None:
    sample = math_solve.sample_ellipse(1.0, 1.0, 48)
    assert len(sample.points) == 49  # 48 samples + close
    assert sample.points[0] == sample.points[-1]
    assert abs(sample.points[0][0] - 1.0) < 1e-3 or abs(sample.points[12][1] - 1.0) < 1e-3
    # Points lie on the unit circle.
    for x, y in sample.points:
        assert x * x + y * y == pytest.approx(1.0, abs=1e-3)


def test_extract_equation_from_latex_frac() -> None:
    """Pasted homework with \\frac used to fail the ASCII-only equation walker."""
    pairs = math_solve.try_extract_equations_from_text(r"solve \frac{1}{2}x = 3")
    assert pairs == [("((1)/(2))x", "3")]
    result = math_solve.solve_equation(EquationInput(lhs="(1)/(2)x", rhs="3", variables=["x"]))
    assert len(result.solutions_latex) == 1


@pytest.mark.parametrize(
    "lhs, rhs",
    [
        ("x", "x"),
        ("2*x + 4", "2*(x + 2)"),
    ],
)
def test_solve_equation_identifies_infinite_solutions(lhs: str, rhs: str) -> None:
    """BUG FIX: a tautology (true for every value of x) used to collapse
    into the same ambiguous "No solutions found (or infinite solution set)."
    string as a genuine contradiction."""
    result = math_solve.solve_equation(EquationInput(lhs=lhs, rhs=rhs, variables=["x"]))
    assert result.solutions_latex == []
    assert result.solution_kind == "infinite"
    assert any("infinitely many" in step.lower() for step in result.steps)


@pytest.mark.parametrize(
    "lhs, rhs",
    [
        ("x", "x + 1"),
        ("0", "1"),
    ],
)
def test_solve_equation_identifies_no_solution(lhs: str, rhs: str) -> None:
    """BUG FIX: a genuine contradiction used to collapse into the same
    ambiguous "No solutions found (or infinite solution set)." string as a
    tautology with infinitely many solutions."""
    result = math_solve.solve_equation(EquationInput(lhs=lhs, rhs=rhs, variables=["x"]))
    assert result.solutions_latex == []
    assert result.solution_kind == "none"
    assert any("contradiction" in step.lower() for step in result.steps)


def test_solve_equation_finite_solutions_kind() -> None:
    result = math_solve.solve_equation(EquationInput(lhs="2*x + 4", rhs="10", variables=["x"]))
    assert result.solution_kind == "finite"


def test_solve_x_squared_plus_two() -> None:
    result = math_solve.solve_equation(EquationInput(lhs="x**2 + 2", rhs="6", variables=["x"]))
    joined = " ".join(result.solutions_latex)
    assert "-2" in joined
    assert "2" in joined


def test_solve_quadratic_includes_worked_isolation_steps() -> None:
    """The user's x^2 + 2 = 6 case: SymPy must emit the verified intermediate
    steps (isolate x^2 = 4, take square root x = ±2) so the model copies them
    instead of inventing wrong steps like 'x^2 = 6 - 2x^2'."""
    result = math_solve.solve_equation(EquationInput(lhs="x**2 + 2", rhs="6", variables=["x"]))
    steps_text = "\n".join(result.steps)
    # Isolation step: x^2 = 4, then x = ±√4. Not √(x²) followed by |x|.
    assert "x^{2} = 4" in steps_text
    assert r"\sqrt{4}" in steps_text
    assert r"\pm" in steps_text
    assert "lvert" not in steps_text
    assert r"\sqrt{x" not in steps_text
    # No stray wrong terms the model was emitting.
    assert "2x" not in steps_text
    assert "\\sqrt{4x}" not in steps_text


def test_canonical_sixth_roots_group_conjugates() -> None:
    result = math_solve.solve_equation(
        EquationInput(lhs="x**6", rhs="1", variables=["x"], complex_roots=True)
    )
    assert len(result.solutions_latex) == 6
    assert len(result.canonical_solutions_latex) == 3
    joined = " ".join(result.canonical_solutions_latex)
    assert r"\pm 1" in joined
    assert r"\pm" in joined
    assert " i" in joined


@pytest.mark.parametrize(
    ("lhs", "rhs", "expected"),
    [
        ("x**6", "1", [r"x = -1", r"x = 1"]),
        ("x**3", "8", [r"x = 2"]),
        ("x**4", "16", [r"x = -2", r"x = 2"]),
        ("exp(2*x)", "5", [r"x = \frac{\ln 5}{2}"]),
    ],
)
def test_solve_equation_keeps_real_roots_when_one_exists(lhs, rhs, expected) -> None:
    result = math_solve.solve_equation(EquationInput(lhs=lhs, rhs=rhs, variables=["x"]))
    assert sorted(result.solutions_latex) == sorted(expected)


def test_solve_equation_keeps_complex_roots_when_no_real_root() -> None:
    result = math_solve.solve_equation(EquationInput(lhs="x**2 + 1", rhs="0", variables=["x"]))
    assert sorted(result.solutions_latex) == ["x = -i", "x = i"]


def test_solve_rejects_polynomial_above_degree_cap() -> None:
    with pytest.raises(SolveServiceError, match="degree"):
        math_solve.solve_equation(EquationInput(lhs="x**40", rhs="1", variables=["x"]))


def test_solve_quadratic_with_linear_term_emits_discriminant_steps() -> None:
    """BUG FIX regression: a general quadratic ax^2 + bx + c = 0 (b != 0) used
    to get NO worked steps (only the pure-quadratic b=0 case had them), so the
    model re-derived the discriminant/quadratic-formula algebra and could
    corrupt it. Now SymPy emits the discriminant + quadratic-formula steps."""
    result = math_solve.solve_equation(
        EquationInput(lhs="x**2 + 4*x + 1", rhs="0", variables=["x"])
    )
    steps_text = "\n".join(result.steps)
    assert "\\Delta" in steps_text  # discriminant step
    assert "Quadratic formula" in steps_text
    # Discriminant of x^2 + 4x + 1 is 16 - 4 = 12.
    assert "12" in steps_text
    assert "--" not in steps_text


def test_solve_quadratic_negative_b_parenthesizes_discriminant() -> None:
    """``x^2 - 2x - 1`` used to emit ``\\Delta = -2^{2}`` (false: -2^2 is -4)."""
    result = math_solve.solve_equation(
        EquationInput(lhs="x**2 - 2*x - 1", rhs="0", variables=["x"])
    )
    steps_text = "\n".join(result.steps)
    assert "\\Delta" in steps_text
    assert "(-2)^{2}" in steps_text or "\\left(-2\\right)^{2}" in steps_text
    assert "-2^{2}" not in steps_text.replace("(-2)^{2}", "")
    assert "--" not in steps_text
    assert "2(1)" not in steps_text


def test_solve_quadratic_negative_b_and_c_no_false_precedence() -> None:
    result = math_solve.solve_equation(
        EquationInput(lhs="2*x**2 - 4*x - 1", rhs="0", variables=["x"])
    )
    steps_text = "\n".join(result.steps)
    assert "--" not in steps_text
    assert "-4^{2}" not in steps_text
    assert "(-4)^{2}" in steps_text or "\\left(-4\\right)^{2}" in steps_text


def test_solve_quadratic_negative_linear_coeff_parenthesizes_b() -> None:
    result = math_solve.solve_equation(
        EquationInput(lhs="x**2 - 5*x - 1", rhs="0", variables=["x"])
    )
    steps_text = "\n".join(result.steps)
    assert "(-5)^{2}" in steps_text or "(-5)^{{2}}" in steps_text
    assert "-5^{2}" not in steps_text
    assert "\\frac{-(-5)" in steps_text or "\\frac{-(-5) " in steps_text


def test_solve_linear_includes_worked_isolation_steps() -> None:
    result = math_solve.solve_equation(EquationInput(lhs="2*x + 4", rhs="10", variables=["x"]))
    steps_text = "\n".join(result.steps)
    # 2*x = 6  →  x = 3
    assert "2" in steps_text
    assert "x = 3" in steps_text
    assert "4 - 4" in steps_text or "2 x + 4 - 4" in steps_text


def test_solve_linear_shows_subtract_on_both_sides() -> None:
    """F + 3 = 3 must show F + 3 - 3 = 3 - 3, not jump to F = 3 - 3."""
    result = math_solve.solve_equation(EquationInput(lhs="F + 3", rhs="3", variables=["F"]))
    steps_text = "\n".join(result.steps)
    assert "F + 3 - 3 = 3 - 3" in steps_text
    assert "F = 0" in steps_text


def test_solve_linear_multiplies_by_reciprocal_for_half_x() -> None:
    """x/2 + 1 = 4 should multiply by 2, not divide by 1/2."""
    result = math_solve.solve_equation(EquationInput(lhs="x/2 + 1", rhs="4", variables=["x"]))
    steps_text = "\n".join(result.steps)
    assert "Multiply" in steps_text
    assert "2" in steps_text
    assert "x = 6" in steps_text
    assert "Divide both sides by" not in steps_text
    assert r"\frac{\frac" not in steps_text


def test_worked_steps_empty_for_unrecognized_form() -> None:
    """A multi-variable or higher-degree form gets no worked steps (caller
    still has the equation + solutions)."""
    result = math_solve.solve_equation(EquationInput(lhs="x**3 + x", rhs="2", variables=["x"]))
    # Only the Equation: line + Solutions: line — no Isolate/Solve steps.
    assert not any(s.startswith("Isolate:") for s in result.steps)


def test_rectangle_geometry() -> None:
    result = math_solve.rectangle_geometry(RectangleGeometryInput(width=8, height=5))
    assert result.diagonal == pytest.approx(math.sqrt(89), rel=1e-3)
    assert result.angle_deg == pytest.approx(math.degrees(math.atan2(5, 8)), rel=1e-2)
    assert result.area == 40.0
    assert result.perimeter == 26.0
    assert "8" in result.labels["width"]


def test_square_geometry() -> None:
    from app.modules.math.schemas import SquareGeometryInput

    result = math_solve.square_geometry(SquareGeometryInput(side=5))
    assert result.area == 25.0
    assert result.perimeter == 20.0
    assert result.diagonal == pytest.approx(5 * math.sqrt(2), rel=1e-3)


def test_solid_geometry_cube_and_prism() -> None:
    from app.modules.math.schemas import SolidGeometryInput

    cube = math_solve.solid_geometry(SolidGeometryInput(shape="cube", side=5))
    assert cube.volume == 125.0
    assert cube.surface_area == 150.0

    prism = math_solve.solid_geometry(
        SolidGeometryInput(shape="rectangular_prism", width=3, depth=4, height=5)
    )
    assert prism.volume == 60.0
    assert prism.surface_area == 94.0


def test_solid_geometry_sphere() -> None:
    from app.modules.math.schemas import SolidGeometryInput

    sphere = math_solve.solid_geometry(SolidGeometryInput(shape="sphere", radius=3))
    assert sphere.volume == pytest.approx((4.0 / 3.0) * math.pi * 27, rel=1e-3)
    assert sphere.surface_area == pytest.approx(4 * math.pi * 9, rel=1e-3)


def test_triangle_geometry() -> None:
    from app.modules.math.schemas import TriangleGeometryInput

    result = math_solve.triangle_geometry(TriangleGeometryInput(base=8, height=5))
    assert result.area == 20.0


def test_right_triangle_geometry() -> None:
    from app.modules.math.schemas import RightTriangleGeometryInput

    result = math_solve.right_triangle_geometry(RightTriangleGeometryInput(base=6, height=4))
    assert result.hypotenuse == pytest.approx(7.2111, rel=1e-3)
    assert result.area == 12.0
    assert "7.21" in result.labels["hypotenuse"]
    assert result.labels["angle_at_base"].startswith("33.7")
    assert result.labels["angle_at_height"].startswith("56.3")


def test_circle_geometry() -> None:
    from app.modules.math.schemas import CircleGeometryInput

    result = math_solve.circle_geometry(CircleGeometryInput(radius=4))
    assert result.diameter == 8.0
    assert result.area == pytest.approx(math.pi * 16, rel=1e-4)
    assert result.circumference == pytest.approx(8 * math.pi, rel=1e-4)
    assert "4" in result.labels["radius"]


def test_sample_function_quadratic() -> None:
    result = math_solve.sample_function(
        GraphSampleInput(expr="x**2", variable="x", x_min=-2, x_max=2, n=10)
    )
    assert len(result.points) == 10
    assert result.points[0][0] == pytest.approx(-2.0)
    zeroish = min(result.points, key=lambda p: abs(p[1]))
    assert zeroish[1] == pytest.approx(0.0, abs=0.5)


def test_sample_function_draws_a_horizontal_line() -> None:
    """``y = 5`` evaluates to one number; it used to crash the sampler."""
    result = math_solve.sample_function(
        GraphSampleInput(expr="5", variable="x", x_min=-2, x_max=2, n=10)
    )
    assert len(result.points) == 10
    assert {point[1] for point in result.points} == {5.0}


def test_sample_function_rejects_relational_expr() -> None:
    with pytest.raises(math_solve.SolveServiceError, match="number lines"):
        math_solve.sample_function(
            GraphSampleInput(expr="x > 3", variable="x", x_min=-10, x_max=10, n=20)
        )


def test_sample_function_free_symbols_are_math_service_error() -> None:
    """Leftover letters (``Graph`` → G·a·h·p·r) used to TypeError at np.asarray
    and log as ``math_tools failed`` instead of a clean SolveServiceError skip."""
    with pytest.raises(math_solve.SolveServiceError, match="Could not sample"):
        math_solve.sample_function(
            GraphSampleInput(expr="x**2/(G*a*h*p*r)", variable="x", x_min=-2, x_max=2, n=10)
        )


def test_number_line_from_x_gt_3() -> None:
    spec = math_solve.number_line_spec_from_expr("x > 3")
    assert spec is not None
    assert spec.type == "number_line"
    assert len(spec.intervals) == 1
    iv = spec.intervals[0]
    assert iv.start == pytest.approx(3.0)
    assert iv.end is None
    assert iv.start_inclusive is False


def test_number_line_from_compound() -> None:
    spec = math_solve.number_line_spec_from_expr("1 < x < 5")
    assert spec is not None
    assert len(spec.intervals) == 1
    iv = spec.intervals[0]
    assert iv.start == pytest.approx(1.0)
    assert iv.end == pytest.approx(5.0)
    assert iv.start_inclusive is False
    assert iv.end_inclusive is False


def test_number_line_from_quadratic_split() -> None:
    spec = math_solve.number_line_spec_from_expr("x**2 - 1 > 0")
    assert spec is not None
    assert len(spec.intervals) == 2
    assert any(iv.start is None and iv.end == pytest.approx(-1.0) for iv in spec.intervals)
    assert any(iv.start == pytest.approx(1.0) and iv.end is None for iv in spec.intervals)


def test_number_line_skips_two_variable_half_plane() -> None:
    assert math_solve.number_line_spec_from_expr("y > 2*x") is None


def test_sample_function_splits_segments_at_a_vertical_asymptote() -> None:
    """BUG FIX (verified live): tan(x) over the default range drew a
    near-straight line across the pi/2 asymptote, since naively connecting
    every finite sample crosses straight through the discontinuity. There
    are 6 real tan(x) asymptotes in [-10, 10] (at (n + 0.5)*pi), so a
    correct split produces 7 pieces."""
    result = math_solve.sample_function(
        GraphSampleInput(expr="tan(x)", variable="x", x_min=-10, x_max=10, n=200)
    )
    assert len(result.segments) == 7
    # Every point must still be accounted for across the segments (nothing
    # dropped, nothing duplicated).
    assert sum(len(seg) for seg in result.segments) == len(result.points)


@pytest.mark.parametrize("expr", ["x**2", "sin(x)"])
def test_sample_function_does_not_split_a_smooth_function(expr: str) -> None:
    """A smooth function (even one that crosses zero, like sin(x)) must not
    be split — the heuristic only fires on a sign flip where BOTH sides are
    large in magnitude, which a zero-crossing never is."""
    result = math_solve.sample_function(
        GraphSampleInput(expr=expr, variable="x", x_min=-10, x_max=10, n=200)
    )
    assert len(result.segments) == 1


def test_sample_function_splits_even_order_pole_without_sign_flip() -> None:
    """1/x**2 diverges to +inf on BOTH sides of x=0 — no sign flip, so the
    numeric heuristic cannot see it. The symbolic pole split catches it."""
    result = math_solve.sample_function(
        GraphSampleInput(expr="1/x**2", variable="x", x_min=-10, x_max=10, n=200)
    )
    assert len(result.segments) == 2
    assert all(p[0] < 0 for p in result.segments[0])
    assert all(p[0] > 0 for p in result.segments[1])
    assert sum(len(seg) for seg in result.segments) == len(result.points)


def test_sample_function_splits_shifted_pole_at_the_true_x() -> None:
    result = math_solve.sample_function(
        GraphSampleInput(expr="1/(x - 2)", variable="x", x_min=-10, x_max=10, n=200)
    )
    assert len(result.segments) == 2
    assert max(p[0] for p in result.segments[0]) < 2
    assert min(p[0] for p in result.segments[1]) > 2


def test_sample_function_does_not_split_removable_singularity() -> None:
    """sin(x)/x is bounded near x=0 (y → 1): even if SymPy names 0 a
    singularity, the samples do not confirm divergence — no visual gap."""
    result = math_solve.sample_function(
        GraphSampleInput(expr="sin(x)/x", variable="x", x_min=-10, x_max=10, n=200)
    )
    assert len(result.segments) == 1


def test_sample_function_symbolic_pole_outside_window_is_ignored() -> None:
    """1/(x - 50)'s pole sits outside [-10, 10] — the curve is smooth in view."""
    result = math_solve.sample_function(
        GraphSampleInput(expr="1/(x - 50)", variable="x", x_min=-10, x_max=10, n=200)
    )
    assert len(result.segments) == 1


def test_sample_function_zooms_undersampled_sine() -> None:
    """sin(x) on [-1000, 1000] at 96 points aliases (~20 units/sample vs period 2π)."""
    result = math_solve.sample_function(
        GraphSampleInput(expr="sin(x)", variable="x", x_min=-1000, x_max=1000, n=96)
    )
    width = result.x_max - result.x_min
    assert width < 100
    assert result.x_min < 0 < result.x_max
    ys = [p[1] for p in result.points]
    assert max(ys) > 0.5
    assert min(ys) < -0.5


def test_sample_function_keeps_explicit_count_on_a_short_window() -> None:
    result = math_solve.sample_function(
        GraphSampleInput(expr="x**2", variable="x", x_min=-2, x_max=2, n=10)
    )
    assert len(result.points) == 10
    assert result.x_min == pytest.approx(-2.0)
    assert result.x_max == pytest.approx(2.0)


def test_simplify_expression() -> None:
    result = math_solve.simplify_expression("x + x", "x")
    assert result.result == "2*x"


def test_factor_expression() -> None:
    result = math_solve.factor_expression("x**2 - 1", "x")
    # SymPy factors x^2 - 1 into (x - 1)*(x + 1).
    assert result.result == "(x - 1)*(x + 1)"


def test_expand_expression() -> None:
    result = math_solve.expand_expression("(x - 1)*(x + 1)", "x")
    assert result.result == "x**2 - 1"


def test_integrate_definite_expression() -> None:
    # ∫₀¹ x² dx = 1/3.
    result = math_solve.integrate_definite("x**2", "x", "0", "1")
    assert result.solved is True
    assert result.result == "1/3"


def test_integrate_definite_infinity_aware() -> None:
    # ∫₀^∞ e^(-x) dx = 1 — bound "inf" maps to sympy.oo.
    result = math_solve.integrate_definite("exp(-x)", "x", "0", "inf")
    assert result.solved is True
    assert result.result == "1"


def test_solve_inequality_quadratic_split() -> None:
    # x^2 - 1 > 0  →  x < -1 or x > 1.
    result = math_solve.solve_inequality("x**2 - 1", "0", "x", ">")
    sol = "\n".join(result.steps)
    assert "Inequality" in sol
    # Solution set must reference the split points (-1 and 1).
    assert "1" in sol


def test_try_extract_inequality_from_text() -> None:
    assert math_solve.try_extract_inequality_from_text("solve x**2 - 1 > 0") == (
        "x**2 - 1",
        "0",
        ">",
    )
    # LaTeX \leq and Unicode ≤ canonicalize to "<=".
    leq = math_solve.try_extract_inequality_from_text("solve x \\leq 5")
    assert leq is not None and leq[2] == "<="
    le = math_solve.try_extract_inequality_from_text("solve x ≤ 5")
    assert le is not None and le[2] == "<="
    # \le must NOT match the \le inside \left(...\right).
    assert math_solve.try_extract_inequality_from_text("solve \\left(x + 1\\right) = 0") is None


def test_abs_inequality_extract_and_solve() -> None:
    ineq = math_solve.try_extract_inequality_from_text("solve |x-2| < 5")
    assert ineq == ("Abs(x-2)", "5", "<")
    result = math_solve.solve_inequality("Abs(x-2)", "5", "x", "<")
    assert result.solutions_latex
    joined = " ".join(result.solutions_latex)
    assert "3" in joined or "-3" in joined or "x" in joined


def test_abs_equation_extract_and_solve() -> None:
    pairs = math_solve.try_extract_equations_from_text("solve |x-2| = 5")
    assert pairs == [("Abs(x-2)", "5")]
    result = math_solve.solve_equation(EquationInput(lhs="Abs(x-2)", rhs="5", variables=["x"]))
    assert len(result.solutions_latex) == 2


def test_compound_inequality_extract_and_solve() -> None:
    compound = math_solve.try_extract_compound_inequality_from_text("solve 1 < x < 5")
    assert compound == ("1", "<", "x", "<", "5")
    closed = math_solve.try_extract_compound_inequality_from_text("solve 1 ≤ x ≤ 3")
    assert closed == ("1", "<=", "x", "<=", "3")
    result = math_solve.solve_compound_inequality("1", "<", "x", "<", "5", "x")
    assert result.solutions_latex
    assert "1" in result.solutions_latex[0] or "Interval" in result.steps[1]


def test_differentiate_expression() -> None:
    result = math_solve.differentiate_expression("x**2", "x")
    assert "2" in result.latex


def test_differentiate_expression_second_order() -> None:
    result = math_solve.differentiate_expression("x**4 - 3*x**2", "x", 2)
    # SymPy may leave 12x^{2}-6 or factor as 6(2x^{2}-1).
    assert "x^{3}" not in result.latex
    assert "2 x^{2}" in result.latex or "12" in result.latex
    assert r"\frac{d}{dx}" in result.steps[0]
    assert r"\frac{d^{2}}{dx^{2}}" in result.steps[1]
    assert "dy" not in result.steps[0]
    assert "d^{2}y" not in result.steps[1]


def test_integrate_expression_marks_closed_form_result_as_solved() -> None:
    result = math_solve.integrate_expression("2*x", "x")
    assert result.result == "x**2"
    assert result.solved is True


def test_integrate_expression_marks_unevaluated_integral_as_not_solved() -> None:
    """BUG FIX: integrate_expression can hand back a result that still
    contains a literal unevaluated Integral(...) instead of raising — that
    used to be indistinguishable from a real closed-form answer downstream,
    where it was asserted to the model as "verified, do NOT recompute"."""
    result = math_solve.integrate_expression("x**x", "x")
    assert result.solved is False
    assert "Integral" in result.result


@pytest.mark.parametrize(
    "expr, point, expected",
    [
        ("x**2", "3", "9"),
        ("sin(x)/x", "0", "1"),
        ("1/x", "oo", "0"),
        ("1/x", "infinity", "0"),
    ],
)
def test_compute_limit(expr: str, point: str, expected: str) -> None:
    result = math_solve.compute_limit(expr, "x", point)
    assert result.result == expected
    assert result.is_infinite is False


def test_compute_limit_marks_a_diverging_limit_as_infinite() -> None:
    result = math_solve.compute_limit("1/x", "x", "0")
    assert result.is_infinite is True
    # A two-sided limit at 0 doesn't exist as a finite value (the sides
    # disagree) — preserve SymPy's zoo status for the presentation layer.
    assert result.result == "zoo"
    assert "infty" in result.latex


def test_compute_limit_negative_infinity_point() -> None:
    result = math_solve.compute_limit("x", "x", "-infinity")
    assert result.is_infinite is True


@pytest.mark.parametrize(
    "expr, variable, point, direction",
    [
        # SymPy's accumulation bounds, <-1, 1>: they bound the values near the
        # point, and are no proof the limit is missing either.
        ("sin(1/x)", "x", "0", "+-"),
        ("cos(1/x)", "x", "0", "+-"),
        ("sin(1/x)", "x", "0", "+"),
        ("cos(x)", "x", "oo", "+-"),
        ("tan(1/x)", "x", "0", "+-"),
        # The identity is 1, but SymPy bounds each term apart: <0, 2>.
        ("sin(1/x)**2 + cos(1/x)**2", "x", "0", "+-"),
        # The bounds inside a larger expression: |<-1, 1>|, oo*sign(<-1, 1>).
        ("Abs(sin(1/x))", "x", "0", "+-"),
        ("x*sin(x)", "x", "oo", "+-"),
        ("sin(1/x)/x", "x", "0", "+"),
        # NaN.
        ("(-1)**n", "n", "oo", "+-"),
        # Limit(...) handed back unevaluated.
        ("sin(x)**x", "x", "oo", "+-"),
        # A complex value: a school limit is over the reals.
        ("sqrt(x)", "x", "-1", "+-"),
        ("log(x)", "x", "-1", "+-"),
        # Complex infinity where no two sides were compared: at infinity, or
        # where neither one-sided limit exists.
        ("(-2)**n", "n", "oo", "+-"),
        ("sin(1/x)/x", "x", "0", "+-"),
    ],
)
def test_compute_limit_refuses_a_value_sympy_did_not_establish(
    expr: str, variable: str, point: str, direction: str
) -> None:
    with pytest.raises(SolveServiceError):
        math_solve.compute_limit(expr, variable, point, direction)


@pytest.mark.parametrize(
    "expr, point, direction, expected",
    [
        ("1/x", "0", "+-", "zoo"),  # -oo from the left, oo from the right
        ("Abs(x)/x", "0", "+-", "zoo"),  # -1 and 1
        ("exp(1/x)", "0", "+-", "zoo"),  # 0 and oo
        ("1/x**2", "0", "+-", "oo"),
        ("-1/x**2", "0", "+-", "-oo"),
        ("1/x", "0", "+", "oo"),
        ("x*sin(1/x)", "0", "+-", "0"),
        ("sin(x)/x", "oo", "+-", "0"),
    ],
)
def test_compute_limit_keeps_disagreeing_sides_and_signed_infinities(
    expr: str, point: str, direction: str, expected: str
) -> None:
    assert math_solve.compute_limit(expr, "x", point, direction).result == expected


@pytest.mark.parametrize(
    "expr, start, end",
    [("1/n", "0", "5"), ("1/n", "0", "oo"), ("1/n**2", "0", "oo"), ("1/(n**2 - 1)", "1", "oo")],
)
def test_evaluate_series_sum_refuses_a_sum_with_an_undefined_term(
    expr: str, start: str, end: str
) -> None:
    """``1/n`` from ``n = 0``: SymPy sums to complex infinity, ``\\tilde{\\infty}``."""
    with pytest.raises(SolveServiceError):
        math_solve.evaluate_series_sum(expr, "n", start, end)


def test_evaluate_series_sum_convergent() -> None:
    result = math_solve.evaluate_series_sum("1/n**2", "n", "1", "infinity")
    assert result.is_convergent is True
    assert result.is_absolutely_convergent is True
    assert result.is_infinite is False
    assert "pi" in result.result.lower()


def test_evaluate_series_sum_divergent() -> None:
    """BUG FIX target: the harmonic series (sum 1/n) diverges — must be
    flagged as not convergent and as an infinite result, not silently
    presented as a finite value."""
    result = math_solve.evaluate_series_sum("1/n", "n", "1", "infinity")
    assert result.is_convergent is False
    assert result.is_infinite is True
    assert result.result == "oo"


def test_evaluate_series_sum_finite_bounds() -> None:
    result = math_solve.evaluate_series_sum("n", "n", "1", "10")
    assert result.result == "55"
    assert result.is_infinite is False


def test_try_extract_equation() -> None:
    eq = math_solve.try_extract_equation_from_text("Solve x^2 + 2 = 6")
    assert eq is not None
    assert eq.lhs.replace(" ", "") in {"x**2+2", "x^2+2"}


@pytest.mark.parametrize(
    "text, expected_lhs",
    [
        ("Solve x^2 + 2 = 6", "x^2 + 2"),
        ("solve x^2 + 2 = 6", "x^2 + 2"),
        ("what is x^2 + 2 = 6", "x^2 + 2"),
        ("can you solve x^2 + 2 = 6", "x^2 + 2"),
        ("please solve x^2 + 2 = 6", "x^2 + 2"),
        ("x^2 + 2 = 6", "x^2 + 2"),
    ],
)
def test_try_extract_equation_strips_leading_trigger_words(text: str, expected_lhs: str) -> None:
    """BUG FIX (was live): the equation-extraction regex's lhs capture is
    non-greedy, but re.search still tries the EARLIEST possible match start —
    so "Solve x^2 + 2 = 6" swept "Solve" into the extracted lhs. That
    corrupted both the parsed expression (undeclared letters silently became
    new multiplied symbols via SymPy's auto_symbol) and the guessed variable
    list, producing a confidently wrong "verified" answer. Confirmed live:
    'Solve x^2 + 2 = 6' used to solve for a garbage variable and return
    nonsense like "2.71828182845905 S l o v x^{2} + 2 = 6"."""
    eq = math_solve.try_extract_equation_from_text(text)
    assert eq is not None
    assert eq.lhs == expected_lhs
    assert eq.variables == ["x"]
    result = math_solve.solve_equation(eq)
    assert result.solutions_latex == ["x = -2", "x = 2"]
    assert result.canonical_solutions_latex == [r"x = \pm 2"]


def test_try_extract_equations_from_text_finds_every_clause() -> None:
    """BUG FIX (most severe correctness bug found in the audit): this used
    to be a single re.search, so only the FIRST equation was ever extracted
    — "solve x+y=5, x-y=1" silently discarded the second clause."""
    pairs = math_solve.try_extract_equations_from_text("solve x+y=5, x-y=1")
    assert pairs == [("x+y", "5"), ("x-y", "1")]


def test_try_extract_equations_from_text_strips_system_prefix() -> None:
    pairs = math_solve.try_extract_equations_from_text(
        "solve the system of equations x+2y=8, 3x-y=1"
    )
    assert pairs == [("x+2y", "8"), ("3x-y", "1")]


def test_try_extract_equations_keeps_x_in_spaced_system() -> None:
    """'the system x + y = 5' used to strip the first x as filler."""
    pairs = math_solve.try_extract_equations_from_text("Solve the system x + y = 5 and x - y = 1.")
    assert pairs == [("x + y", "5"), ("x - y", "1")]


def test_try_extract_equations_strips_trailing_sentence_period() -> None:
    pairs = math_solve.try_extract_equations_from_text("Solve 1/2 + 1/3 = x.")
    assert pairs == [("1/2 + 1/3", "x")]


def test_try_extract_equations_stops_at_a_sentence_period() -> None:
    pairs = math_solve.try_extract_equations_from_text(
        "Solve the math problem in this file.\n\n3x^2 + 4 = 4"
    )
    assert pairs == [("3x^2 + 4", "4")]


def test_try_extract_equations_from_text_single_equation_unaffected() -> None:
    assert math_solve.try_extract_equations_from_text("x + 4 = 10") == [("x + 4", "10")]


def test_try_extract_equations_rejects_chained_equals() -> None:
    """A chained equality must not silently drop its middle expression."""
    assert math_solve.try_extract_equations_from_text("Solve 2x + 3 = 3 = 7") == []
    assert math_solve.rejected_equality_chain("Solve 2x + 3 = 3 = 7") is True
    assert math_solve.rejected_equality_chain("solve x+y=5, x-y=1") is False
    assert math_solve.rejected_equality_chain("x + 4 = 10") is False


def test_try_extract_equations_strips_glued_english() -> None:
    assert math_solve.try_extract_equations_from_text("X=6graph") == [("X", "6")]
    assert math_solve.try_extract_equations_from_text("2x+3=7please") == [("2x+3", "7")]
    assert math_solve.try_extract_equations_from_text("velocity=12") == [("velocity", "12")]
    assert math_solve.try_extract_equations_from_text("E=mc^2") == [("E", "mc^2")]


def test_try_extract_equations_stops_at_homework_labels() -> None:
    """collapse_ws turns `=0\\nFactor it:` into `=0 Factor it` — do not glue
    the label onto the RHS (that used to make a fake multi-equation system)."""
    pairs = math_solve.try_extract_equations_from_text("2x^2-7x+3=0 Factor it: 2x-1=0 or x-3=0")
    assert ("2x^2-7x+3", "0") in pairs
    assert ("2x-1", "0") in pairs
    assert ("x-3", "0") in pairs
    assert all("Factor" not in lhs + rhs for lhs, rhs in pairs)
    assert all(" or " not in lhs and " or " not in rhs for lhs, rhs in pairs)


def test_guess_variables_does_not_split_unknown_letter_runs() -> None:
    eq = math_solve.try_extract_equation_from_text("X=6graph")
    assert eq is not None
    assert eq.lhs == "X"
    assert eq.rhs == "6"
    assert eq.variables == ["X"]
    assert math_solve.guess_variables("X=6graph") == ["X"]
    assert math_solve.guess_variables("6graph") == ["x"]


def test_try_extract_equations_from_text_no_equation() -> None:
    assert math_solve.try_extract_equations_from_text("what's the weather") == []


def test_solve_system_unique_solution() -> None:
    result = math_solve.solve_system(
        SystemOfEquationsInput(equations=[("x+y", "5"), ("x-y", "1")], variables=["x", "y"])
    )
    assert result.solution_kind == "finite"
    assert result.solutions == [{"x": "3", "y": "2"}]


def test_solve_system_no_solution() -> None:
    """BUG FIX target: two parallel-line equations (same slope, different
    intercept) have no solution — must not be silently reported as an empty
    solution set with no explanation."""
    result = math_solve.solve_system(
        SystemOfEquationsInput(equations=[("x+y", "5"), ("x+y", "10")], variables=["x", "y"])
    )
    assert result.solution_kind == "none"
    assert result.solutions == []


def test_solve_system_infinite_solutions_dependent_equations() -> None:
    """BUG FIX target: a dependent system (the second equation is just the
    first scaled by 2) has infinitely many solutions along a line — SymPy
    returns a non-empty but parametrized solution ({x: 5 - y}) rather than
    an empty list, which must not be mistaken for a single finite answer."""
    result = math_solve.solve_system(
        SystemOfEquationsInput(equations=[("x+y", "5"), ("2*x+2*y", "10")], variables=["x", "y"])
    )
    assert result.solution_kind == "infinite"
    assert result.solutions == [{"x": "5 - y"}]


def test_solve_system_infinite_solutions_independent_tautologies() -> None:
    result = math_solve.solve_system(
        SystemOfEquationsInput(equations=[("x", "x"), ("y", "y")], variables=["x", "y"])
    )
    assert result.solution_kind == "infinite"


def test_solve_system_three_by_three() -> None:
    result = math_solve.solve_system(
        SystemOfEquationsInput(
            equations=[("x+y+z", "6"), ("x-y+z", "2"), ("x+y-z", "0")],
            variables=["x", "y", "z"],
        )
    )
    assert result.solution_kind == "finite"
    assert result.solutions == [{"x": "1", "y": "2", "z": "3"}]


def test_newton_method_converges_to_known_root() -> None:
    # x^3 - 2x - 5 = 0 has a well-known real root near 2.0945514815.
    result = math_solve.newton_method(
        NewtonMethodInput(expr="x**3 - 2*x - 5", variable="x", initial_guess=2.0)
    )
    assert result.converged is True
    assert result.root == pytest.approx(2.0945514815, abs=1e-6)
    assert result.iterations_used == len(result.iterations)
    assert result.iterations[0].n == 0
    assert result.iterations[0].x_n == pytest.approx(2.0)


def test_newton_method_records_full_iteration_history() -> None:
    result = math_solve.newton_method(
        NewtonMethodInput(expr="x**2 - 2", variable="x", initial_guess=1.0)
    )
    assert result.converged is True
    assert result.root == pytest.approx(2**0.5, abs=1e-6)
    # Every f(x_n) should shrink in magnitude as the iteration converges.
    abs_f_values = [abs(step.f_x_n) for step in result.iterations]
    assert abs_f_values == sorted(abs_f_values, reverse=True)


def test_newton_method_stops_at_max_iterations_when_not_converged() -> None:
    """A tiny max_iterations with a tolerance the method can't reach in time
    must report converged=False rather than silently returning a root."""
    result = math_solve.newton_method(
        NewtonMethodInput(
            expr="x**3 - 2*x - 5",
            variable="x",
            initial_guess=2.0,
            tolerance=1e-15,
            max_iterations=1,
        )
    )
    assert result.converged is False
    assert result.root is None
    assert result.iterations_used == 1


def test_newton_method_transcendental_equation() -> None:
    # x = cos(x) — the "Dottie number," ~0.7390851332.
    result = math_solve.newton_method(
        NewtonMethodInput(expr="(x)-(cos(x))", variable="x", initial_guess=1.0)
    )
    assert result.converged is True
    assert result.root == pytest.approx(0.7390851332, abs=1e-6)


@pytest.mark.parametrize(
    "text, expected_variable",
    [
        ("cos(x) = 0", "x"),
        ("sin(t) = 0", "t"),
        ("log(n) = 1", "n"),
        # pi is a constant, not two variables p/i -- without the fix, the
        # per-letter scan guessed 'i' (alphabetically before 'x') and solved
        # for the wrong symbol.
        ("sin(pi*x) = 0", "x"),
        ("cos(pi*y) + 1 = 0", "y"),
        ("e^(pi*x) = 1", "x"),
    ],
)
def test_guess_variables_ignores_function_name_letters(text: str, expected_variable: str) -> None:
    """BUG FIX (found while testing Newton's method on "x = cos(x)"): a bare
    per-letter scan treated function-name letters as candidate variables —
    "cos(x) = 0" guessed 'c' (alphabetically first of c/o/s/x) instead of
    'x', silently building a verified block that solves for the wrong
    symbol. Also verifies pi is recognized as a constant (not split into
    p/i variables)."""
    eq = math_solve.try_extract_equation_from_text(text)
    assert eq is not None
    assert eq.variables[0] == expected_variable


def test_graph_block_spec_allows_a_single_point_but_rejects_empty() -> None:
    """BUG FIX regression: a single point is a legitimate way to mark one
    coordinate (e.g. "plot the point (2, 3)"), not just a degenerate
    function curve — requiring 2+ points made that a validation error,
    replaced with an "Invalid graph block" fallback instead of rendering."""
    GraphBlockSpec(expr="x", points=[[0.0, 0.0], [1.0, 1.0]])
    GraphBlockSpec(expr="(2, 3)", points=[[2.0, 3.0]])
    with pytest.raises(ValueError, match="at least one"):
        GraphBlockSpec(expr="x", points=[])


def test_graph_block_spec_number_line_does_not_need_points() -> None:
    spec = GraphBlockSpec(
        type="number_line",
        expr="x > 3",
        intervals=[
            NumberLineInterval(start=3, end=None, start_inclusive=False, end_inclusive=False)
        ],
    )
    assert spec.points == []
    assert spec.intervals[0].start == 3.0
    with pytest.raises(ValueError, match="expr"):
        GraphBlockSpec(type="number_line", expr="  ", intervals=[])


def test_graph_block_spec_rejects_more_points_than_the_backend_ever_samples() -> None:
    """BUG FIX regression: points had no upper bound, unlike every other
    field in this file — a model reproducing (or fabricating) a ```graph
    fence could claim an unbounded points array. Matches
    GraphSampleInput.n's own cap (le=500)."""
    GraphBlockSpec(expr="x", points=[[float(i), float(i)] for i in range(500)])
    with pytest.raises(ValueError, match="500"):
        GraphBlockSpec(expr="x", points=[[float(i), float(i)] for i in range(501)])


# ── security: parse_expr/eval is not a safe sandbox for untrusted input ──────
#
# BUG FIX (was a live RCE): parse_expr evaluates its input via Python's
# eval() internally. Restricting local_dict to declared variable names only
# stops bare names from resolving to something dangerous — it does nothing
# to stop attribute access on an already-resolved Symbol object. Any of
# these payloads walks the Python class hierarchy to reach something like
# subprocess.Popen and would execute it, reachable from a plain chat message
# via math/tools keyword-triggered intent extraction (no sanitization)
# and independently via the sympy MCP tool. This must stay blocked.
@pytest.mark.parametrize(
    "payload",
    [
        "x.__class__.__bases__[0].__subclasses__()[400]('id', shell=True, stdout=-1).communicate() x",
        "x.__class__",
        "x.__class__.__mro__[1]",
        "(1).__class__.__bases__[0]",
        "x[0]",
        "x[0:1]",
        "getattr(x, '__class__')",
        'x.__class__.__init__.__globals__["__builtins__"]',
        "x; import os",
        "__import__('os').system('id')",
    ],
)
def test_parse_expression_rejects_attribute_and_subscript_gadgets(payload: str) -> None:
    with pytest.raises(math_solve.SolveServiceError):
        math_solve.parse_expression(payload, ["x"])


@pytest.mark.parametrize(
    "expr, variables",
    [
        ("x**2 + 3*x - 5", ["x"]),
        ("sin(x) + cos(x)", ["x"]),
        ("3.14 * x", ["x"]),
        ("sqrt(x**2 + 1)", ["x"]),
        ("log(x, 10)", ["x"]),
        ("x_1 + x_2", ["x_1", "x_2"]),
        ("2*x + 4", ["x"]),
    ],
)
def test_parse_expression_still_accepts_ordinary_math(expr: str, variables: list[str]) -> None:
    """The RCE fix must not collateral-damage normal expressions."""
    math_solve.parse_expression(expr, variables)


@pytest.mark.parametrize(
    "text",
    ["Q", "CC", "QQ", "S", "N", "O", "Integral", "Sum", "limit", "ln", "sin", "True", "x == 1"],
)
def test_parse_expression_refuses_a_bare_sympy_name(monkeypatch, text: str) -> None:
    """A name SymPy defines parses to its object, ``x == 1`` to a bool (ES-39).

    The object reached the callers: ``O`` (the class ``Order``) raised a TypeError in
    ``reject_unwritten_symbols``, ``Q = m c T`` a SympifyError in ``solve_equation`` and
    ``x == 1`` an AttributeError in ``_require_unknown``; strict declines raised the ones a
    trace's handler took for declines. Each is now an unparsed expression.
    """
    from sympy import Symbol

    from app.modules.math.schemas import EquationInput
    from app.modules.math.solve.derivative_steps import derivative_trace
    from app.modules.math.solve.equations import solve_equation
    from app.modules.math.solve.integral_steps import integral_trace
    from app.modules.math.solve.work_lines import parse_line

    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1")
    with pytest.raises(SolveServiceError):
        math_solve.parse_expression(text, ["x"])
    with pytest.raises(SolveServiceError):
        solve_equation(EquationInput(lhs=text, rhs="2 x", variables=["x"]))
    assert integral_trace(text, "x") == ([], None, None)
    assert derivative_trace(text, "x") == ([], None)
    assert parse_line(f"{text} = 2", Symbol("x")) is None


def test_parse_expression_keeps_a_tuple_and_a_relation() -> None:
    from sympy import Symbol
    from sympy.core.relational import StrictLessThan

    x = Symbol("x")
    assert math_solve.parse_expression("2, 3") == (2, 3)
    assert isinstance(math_solve.parse_expression("x < 1", ["x"]), StrictLessThan)
    assert math_solve.parse_expression("Q x", ["Q", "x"]) == Symbol("Q") * x
