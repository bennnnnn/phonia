"""School homework helpers (complex, units, trig) — not geometry/calc I."""

from __future__ import annotations

from app.modules.math import school as math_school
from app.modules.math.ode import solve_ode


def test_imaginary_unit_mapping_skips_sin_and_pi() -> None:
    assert math_school._imaginary_unit_to_sympy("3+4i") == "3+4I"
    assert math_school._imaginary_unit_to_sympy("3+4j") == "3+4I"
    assert math_school._imaginary_unit_to_sympy("2+3i*sin(30)") == "2+3I*sin(30)"
    assert math_school._imaginary_unit_to_sympy("sin(pi)+i") == "sin(pi)+I"


def test_evaluate_complex_plain() -> None:
    assert math_school.evaluate_complex("3+4i") == "3 + 4 i"
    assert math_school.evaluate_complex("3+4j") == "3 + 4 i"


def test_evaluate_complex_keeps_sin() -> None:
    """Regression: naive ``i``→``I`` replace turned ``sin`` into ``sIn``."""
    out = math_school.evaluate_complex("2+3i*sin(30)")
    assert "sIn" not in out
    assert r"\sin" in out
    assert "i" in out


def test_evaluate_complex_keeps_pi() -> None:
    out = math_school.evaluate_complex("2+3i*sin(pi/6)")
    assert "pI" not in out


def test_solve_ode_builds_eq_not_parse_string() -> None:
    out = solve_ode("dy/dx = y")
    assert out.solved
    low = out.latex.lower()
    assert "e" in low or "exp" in low


def test_solve_ode_yprime() -> None:
    out = solve_ode("y' = -2*y")
    assert out.solved
    assert "2" in out.latex or "e" in out.latex.lower()


def test_percent_change_and_percent_is() -> None:
    assert math_school.percent_increase(200, 12) == "224"
    assert math_school.percent_decrease(200, 12) == "176"
    assert math_school.percent_is(12, 50) == "24"


def test_split_ratio_two_and_three_parts() -> None:
    assert math_school.split_ratio(120, [2, 3]) == "48:72"
    assert math_school.split_ratio(100, [2, 3, 5]) == "20:30:50"


def test_sequence_ap_gp_and_mixed_refused() -> None:
    assert math_school.sequence_nth([3, 7, 11, 15], 10) == "39"
    assert math_school.sequence_sum([3, 7, 11, 15], 10) == "210"
    assert math_school.sequence_nth([2, 4, 8, 16], 5) == "32"
    assert math_school.sequence_sum([2, 4], 20) == "420"
    assert math_school.is_ap_or_gp([1, 2, 4, 7]) is False


def test_interest_and_set_helpers() -> None:
    assert math_school.simple_interest(1000, 5, 3) == "150"
    assert math_school.compound_interest(1000, 5, 3) == "157.625"
    assert math_school.compound_amount(1000, 5, 3) == "1157.625"
    assert math_school.set_union([1, 2, 3], [3, 4]) == "{1, 2, 3, 4}"
    assert math_school.set_intersection([1, 2, 3], [3, 4]) == "{3}"
    assert math_school.set_difference([1, 2, 3], [3, 4]) == "{1, 2}"


def test_critical_points_cubic() -> None:
    out = math_school.critical_points("x**3 - 3*x")
    assert out.solved
    assert "1" in out.latex
    assert "-1" in out.latex


def test_formula_helpers():
    from app.modules.math import formulas as math_formulas

    assert math_formulas.sale_price(80, 20) == "64"
    assert math_formulas.percent_change_from(50, 80) == "60"
    assert math_formulas.direct_proportion(3, 12, 5) == "20"
    assert math_formulas.inverse_proportion(6, 4, 8) == "3"
    assert math_formulas.round_decimal_places(3.14159, 3) == "3.142"
    assert math_formulas.infinite_geometric_sum([8, 4, 2]) == "16"
    assert math_formulas.present_value(1157.625, 5, 3) == "1000"
    assert math_formulas.line_through(1, 2, 3, 6) == "y = 2 x"
    assert math_formulas.vector_unit([3, 4]) == "<0.6, 0.8>"
    assert math_formulas.vector_angle_degrees([1, 0], [0, 1]) == "90"
    assert math_formulas.complex_modulus("3+4i") == "5"
    assert math_formulas.geometric_pmf(2, 0.5) == "0.25"
    assert math_formulas.complement_probability(0.3) == "0.7"
    assert math_formulas.modular_inverse(3, 11) == "4"
    assert math_formulas.euler_totient(10) == "4"
    assert math_formulas.chinese_remainder(2, 3, 3, 5) == "8"
    assert math_formulas.sas_triangle_area(5, 6, 90) == "15"
    assert math_school.work_together(6, 3) == "2"
    assert math_school.mixture_percent(3, 10, 5, 20) == "16.25"
    assert math_school.twice_as_many(30) == "10 and 20"
    assert math_school.analyze_identity("sin(x)**2+cos(x)**2", "1")[0] is True
    assert math_school.analyze_identity("(x+1)**2", "x**2+2*x+1")[0] is True
