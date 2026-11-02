"""Direct table-driven tests for the linear math matchers in math_match.

These matchers are the front door of intent detection — the place where
extractor precedence bugs (sector-before-circle, triangle-sides-before-
triangle, square-root exclusion) actually live. Each has a BUG FIX comment
in the implementation; these tests pin the precedence rules so a regression
is caught at the matcher layer rather than only indirectly through
math_tools intent extraction.
"""

from __future__ import annotations

import pytest

from app.modules.math import match as mtm


class TestNeedsSymbolic:
    @pytest.mark.parametrize(
        "text",
        [
            "solve x^2 + 2 = 6",
            "what is the derivative of x^2",
            "graph y = x^2",
            "X=6graph",
            "x=6graph",
            "draw a rectangle 8 by 5",
            "draw a circle radius 4",
            "find the mean of 1, 2, 3, 4",
            "volume of a cube with side 5",
            "5!",
            "is 17 prime?",
            "determinant of [[1,2],[3,4]]",
            "plot (2, 3)",
            # "find" + equation is a solve ask, not just "solve …".
            "find x if 2x + 3 = 7",
            "find the value of x in 2x = 10",
            # "roots of" / "zeros of" + a digit polynomial → solve.
            "roots of x^2 - 4",
            "find the roots of x^3 - 1",
            "zeros of x^2 - 9",
            # "evaluate" + arithmetic expression.
            "evaluate 2 + 3 * 4",
            "evaluate sin(pi/2)",
            # 1-variable inequality without a math keyword — the gate used
            # to require a keyword, so bare "X>4" never reached the
            # inequality extractor and shipped without a verified fence.
            "X>4",
            "x > 4",
            "1 < x < 5",
            "2x - 1 > 5",
            "Draw a right triangle with legs 3 and 4. Label the sides including the hypotenuse.",
            "area of a right triangle with legs 3 and 4",
            "8-8*2",
            "7*8",
            "what is 9/9",
            "10-3-2",
            "100/5/2",
            "y'' of y = x^3 - 3x",
            "f(x) = x^3 - 3x, find f''(x)",
            "show that sin(x)**2+cos(x)**2=1",
            "graph r=1+cos(theta)",
            "double integral of x*y from x=0 to 1 and y=0 to 1",
            "multiply [[1,2],[3,4]] and [[0,1],[1,0]]",
            "mix 3 liters of 10% with 5 liters of 20%",
        ],
    )
    def test_needs_symbolic_math_triggers(self, text):
        assert mtm.needs_symbolic(text)

    @pytest.mark.parametrize(
        "text",
        [
            "hello there",
            "write a paragraph about trees",
            "show me the weather",
            "what do you mean by that",
            "the tech sector is growing",  # "sector" alone is not geometry
            "what is a trapezoid",  # bare shape name, no measures/draw cue
            "what is a cylinder",
            "see you later",
            # "find" without an equation is plain prose.
            "find the right moment to ask",
            # "roots of" without a digit is English, not algebra.
            "roots of the tree are deep",
            # "evaluate" without an arithmetic operator is prose.
            "evaluate this option carefully",
            "evaluate the model on five examples",
            # Inequality signal rejects prose ("less than" — word, no symbol)
            # and trivial comparisons ("5 < 10" — no variable letter).
            "less than 5 minutes",
            "5 < 10",
            "see the file > readme",
            # Conceptual and unsupported physics stays on the normal chat path.
            "explain kinetic energy",
            "find the friction on a 5 kg block",
            "find the tension in a 10 kg rope",
            "tell me about y=x^2",
            "the answer key says x=5 but i got 6",
            "chart of rainfall",
            "9/9",
            "555-1234",
            "9/7/2026",
            "1-800-273-8255",
            "y'all coming to class",
            "Where is the teachers' lounge?",
            "Who was Newton",
            # Supported physics is deliberately detected by the peer physics
            # gate rather than being smuggled through the math matcher.
            "A ball is dropped from 20m. How long until it hits the ground?",
            "A projectile is launched at 20 m/s at 45 degrees. Find its range.",
            "What net force accelerates a 5 kg mass at 3 m/s^2?",
            "A 5 kg mass is accelerated at 2 m/s². What is the force.",
            "Calculate the kinetic energy of a 2 kg object moving at 10 m/s.",
        ],
    )
    def test_needs_symbolic_math_does_not_trigger(self, text):
        assert not mtm.needs_symbolic(text)

    def test_camera_prompt_triggers_only_with_image(self):
        prompt = "Solve the math problem in this image step by step."
        assert mtm.needs_symbolic(prompt, has_image_attachment=True)
        assert not mtm.needs_symbolic(prompt, has_image_attachment=False)


class TestPrepareSuperscripts:
    def test_unicode_and_latex_unit_powers(self):
        assert mtm.prepare("2 m/s²") == "2 m/s^2"
        assert mtm.prepare(r"2 m/s^{2}") == "2 m/s^2"
        assert mtm.prepare("x²") == "x^2"
        # Keyboard x² chain must stay a ^{a}^{b} pair for the graph peeler.
        assert mtm.prepare("$^{x}^{2}$") == "^{x}^{2}"
        mangled = r"A 5 kg mass is accelerated at 2 m/s$^2$$^2.$^2. What is the force."
        assert mtm.prepare(mangled) == ("A 5 kg mass is accelerated at 2 m/s^2. What is the force.")


class TestDrawShapeGate:
    """Bare shape words must NOT trigger verified geometry — only an explicit
    draw/show/sketch cue (or printed measures) does. Regression guard for the
    "what is a circle?" inventing-dimensions bug."""

    @pytest.mark.parametrize(
        "shape, text",
        [
            ("rectangle", "draw a rectangle"),
            ("square", "show a square"),
            ("circle", "sketch a circle"),
            ("triangle", "visualize a triangle"),
            ("trapezoid", "draw a trapezoid"),
        ],
    )
    def test_draw_shape_matches(self, shape, text):
        assert mtm.has_draw_shape(text.lower(), shape)

    @pytest.mark.parametrize(
        "shape, text",
        [
            ("circle", "what is a circle"),
            ("trapezoid", "define a trapezoid"),
            ("square", "a square is a rectangle"),
        ],
    )
    def test_bare_shape_word_does_not_match_draw(self, shape, text):
        assert not mtm.has_draw_shape(text.lower(), shape)


class TestGeometryDeferredForAlgebra:
    """`solve x^2+y^2=25 for the circle of radius 5` must defer geometry to
    the algebra path — unless the user also asked to draw it."""

    @pytest.mark.parametrize(
        "text",
        [
            "solve x^2+y^2=25 for the circle of radius 5",
            "factor the unit circle expression",
            "integrate over the circle",
        ],
    )
    def test_algebra_defers_geometry(self, text):
        assert mtm.geometry_deferred_for_algebra(text.lower())

    @pytest.mark.parametrize(
        "text",
        [
            "draw a circle radius 5",
            "show the circle of radius 5",
            "sketch the circle",
        ],
    )
    def test_draw_cue_keeps_geometry(self, text):
        assert not mtm.geometry_deferred_for_algebra(text.lower())


class TestFirstDimPair:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("8 by 5 cm", (8.0, 5.0, "cm")),
            ("8x5", (8.0, 5.0, "cm")),
            ("8 × 5 cm", (8.0, 5.0, "cm")),
            ("8 * 5 units", (8.0, 5.0, "units")),
            ("rectangle 4 by 3", (4.0, 3.0, "cm")),
            ("3,5 by 8", (3.5, 8.0, "cm")),
            ("3,5x4", (3.5, 4.0, "cm")),
            ("3.14 by 2", (3.14, 2.0, "cm")),
            ("8 by 5.", (8.0, 5.0, "cm")),
        ],
    )
    def test_first_dim_pair(self, text, expected):
        assert mtm.first_dim_pair(text) == expected

    def test_first_dim_pair_none_when_no_pair(self):
        assert mtm.first_dim_pair("just some text") is None

    def test_first_dim_pair_comma_decimal_is_not_two_ints(self):
        assert mtm.first_dim_pair("3,5") is None


class TestFirstDimTriple:
    def test_three_edges(self):
        assert mtm.first_dim_triple("3 by 4 by 5 cm") == (3.0, 4.0, 5.0, "cm")
        assert mtm.first_dim_triple("3x4x5") == (3.0, 4.0, 5.0, "cm")
        assert mtm.first_dim_triple("3 by 4 by 5.") == (3.0, 4.0, 5.0, "cm")

    def test_pair_is_not_a_triple(self):
        assert mtm.first_dim_triple("8 by 5 cm") is None


class TestParseSolid:
    def test_cube_volume(self):
        parsed = mtm.parse_solid("volume of a cube with side 5 cm")
        assert parsed is not None
        assert parsed.shape == "cube"
        assert parsed.side == 5.0
        assert parsed.wants_volume is True

    def test_prism_triple(self):
        parsed = mtm.parse_solid("volume of a rectangular prism 3 by 4 by 5")
        assert parsed is not None
        assert parsed.shape == "rectangular_prism"
        assert (parsed.width, parsed.depth, parsed.height) == (3.0, 4.0, 5.0)

    def test_bare_shape_without_measures(self):
        assert mtm.parse_solid("what is a cylinder") is None
        assert mtm.parse_solid("cube root of 8") is None

    def test_sphere_is_not_a_substring_of_atmosphere(self):
        assert mtm.classify_solid_shape("atmosphere") is None
        assert mtm.classify_solid_shape("hemisphere") is None
        assert mtm.classify_solid_shape("biosphere") is None
        assert mtm.classify_solid_shape("volume of a sphere radius 5") == "sphere"
        assert mtm.classify_solid_shape("volume of spheres with radius 3") == "sphere"
        assert mtm.classify_solid_shape("cylinders") == "cylinder"
        assert mtm.classify_solid_shape("cones") == "cone"
        assert mtm.classify_solid_shape("pyramids") == "pyramid"
        assert mtm.classify_solid_shape("cubes") == "cube"

    def test_cone_is_not_a_substring_of_silicone(self):
        assert mtm.classify_solid_shape("silicone") is None
        assert mtm.classify_solid_shape("volume of a cone radius 3 height 4") == "cone"


class TestNumberAfter:
    def test_number_after_label(self):
        assert mtm.number_after("circle radius 5", "radius") == 5.0
        assert mtm.number_after("radius 5", "radius") == 5.0

    def test_number_after_missing_label(self):
        assert mtm.number_after("circle diameter", "radius") is None


class TestTwoNumbersAfter:
    def test_legs_and(self):
        assert mtm.two_numbers_after("with legs 3 and 4", "legs") == (3.0, 4.0)

    def test_legs_comma(self):
        assert mtm.two_numbers_after("legs 3, 4", "legs") == (3.0, 4.0)

    def test_missing_second(self):
        assert mtm.two_numbers_after("legs 3", "legs") is None


class TestGraphExpr:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("graph x^2", "x^2"),
            ("plot y = x^2", "x^2"),
            ("graph y=x^2", "x^2"),
            # Composer leftover "Graph y =" + a second typed Graph prompt.
            ("Graph y =Graph y = x^2.", "x^2."),
            ("Graph y =Graph y = x².", "x²."),
            # Keypad wrapped $ around = : Graph y$= x^$$= x^2
            ("Graph y =Graph y= x^= x^2.", "x^2."),
            ("graph x=2y", "x=2y"),
            ("graph x=4", "x=4"),
            ("graph 2x+3=x^2", "2x+3=x^2"),
            # First capture is prose; last unprefixed graph/plot is the formula.
            ("graph this: graph y=x^2", "x^2"),
            ("graph theory then graph y=x^2", "x^2"),
            ("draw y=x^2", "x^2"),
            ("chart y=x^2", "x^2"),
            ("sketch y = x^2", "x^2"),
            ("visualize y=x^2", "x^2"),
            ("visualise y=x^2", "x^2"),
            ("what does y=x^2 look like", "x^2"),
            ("show the shape of y=x^2", "x^2"),
            ("show y=x^2", "x^2"),
            ("draw this: draw y=x^2", "x^2"),
        ],
    )
    def test_graph_expr(self, text, expected):
        assert mtm.graph_expr(text) == expected

    def test_graph_expr_keeps_first_when_core_is_math(self):
        """``graph y=x^2 then plot a table`` must not jump to the later ``plot``."""
        expr = mtm.graph_expr("graph y=x^2 then plot a table")
        assert expr is not None
        assert expr.lower().startswith("x^2")

    def test_graph_expr_none_without_trigger(self):
        assert mtm.graph_expr("x^2") is None
        assert mtm.graph_expr("write a paragraph about trees") is None

    @pytest.mark.parametrize(
        "text",
        [
            "Solve x^2 < 4. Just the answer; no graph and no steps.",
            "Solve x^2 < 4 without a plot.",
            "Do not graph x^2 < 4; solve it.",
            "Don't plot x^2 < 4; just answer.",
        ],
    )
    def test_graph_expr_ignores_negated_presentation_cues(self, text):
        assert mtm.graph_expr(text) is None

    def test_soft_plot_prefix_skips_geometry_and_vega(self):
        assert mtm.graph_expr("draw a triangle") is None
        assert mtm.graph_expr("chart of rainfall") is None
        assert mtm.graph_expr("make a bar chart of monthly rainfall") is None
        assert mtm.graph_expr("show me how to solve") is None
        assert mtm.graph_expr("show me the weather") is None

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("y=3x+4", "3x+4"),
            ("y = 3x+4", "3x+4"),
            ("$y=3x+4$", "3x+4"),
            ("y=x^2", "x^2"),
            ("y=4", "4"),
        ],
    )
    def test_graph_expr_bare_y_equals(self, text, expected):
        """A message that's just y=f(x) is a graph request — the model emits
        ```graph for slope-intercept even without 'graph'/'plot'."""
        assert mtm.graph_expr(text) == expected

    def test_graph_expr_bare_y_equals_skips_solve(self):
        assert mtm.graph_expr("solve y=3x+4") is None
        assert mtm.graph_expr("y=3x+4, x+y=10") is None


class TestGraphExprPair:
    """`graph y=x^2 and y=2x` must split into two candidates — checked
    BEFORE the single-expression graph_expr so it isn't garbled into one
    unparseable expr. But `plot sin(x) and explain it` must NOT treat
    "explain it" as a second function."""

    def test_pair_splits_two_functions(self):
        assert mtm.graph_expr_pair("graph y=x^2 and y=2x") == ("x^2", "2x")

    def test_pair_rejects_prose_second_clause(self):
        # "explain it" is in the prose denylist → falls through to single expr.
        assert mtm.graph_expr_pair("plot sin(x) and explain it") is None

    def test_pair_none_without_and(self):
        assert mtm.graph_expr_pair("graph x^2") is None


class TestVerticalLine:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("graph x=4", 4.0),
            ("plot x = 7", 7.0),
            ("draw vertical x=3", 3.0),
            ("X=6graph", 6.0),
            ("x=6graph", 6.0),
            ("graphx=4", 4.0),
            ("X=$6$graph", 6.0),
            ("graph x=$6$", 6.0),
            (r"graph \(x=6\)", 6.0),
            ("graph y=x**2 and also solve 3x=9", None),
            ("graph 3x=9", None),
        ],
    )
    def test_vertical_line_x(self, text, expected):
        assert mtm.vertical_line_x(text) == expected

    def test_vertical_line_none_without_cue(self):
        # Bare "x=4" with no graph/plot/draw/show cue is not a vertical-line ask.
        assert mtm.vertical_line_x("x=4") is None

    def test_vertical_line_not_function_of_y(self):
        assert mtm.vertical_line_x("graph x=2y") is None
        assert mtm.vertical_line_x("x=2ygraph") is None

    def test_glued_english_without_viz_is_not_vertical(self):
        assert mtm.vertical_line_x("X=6please") is None


class TestGluedVizCommands:
    """Unknown 3+ letter tokens are commands or noise, never g*r*a*p*h."""

    def test_paragraph_is_not_a_graph_keyword(self):
        assert not mtm.has_math_keyword("write a paragraph about trees")

    def test_show_me_is_not_a_math_keyword(self):
        assert not mtm.has_math_keyword("show me the weather")

    def test_glued_graph_is_a_math_keyword(self):
        assert mtm.has_math_keyword("x=6graph")

    def test_command_words_are_whole_words(self):
        assert not mtm.has_math_keyword("i resolved x=1")
        assert not mtm.has_math_keyword("factorial of 5")
        assert mtm.has_math_keyword("solve x=1")
        assert mtm.has_math_keyword("i solved 2x+3=7")
        assert mtm.has_math_keyword("pythagorean theorem")

    def test_has_viz_command_whole_run_not_substring(self):
        from app.modules.math.match.letter_runs import has_viz_command, peel_edge_english

        assert has_viz_command("X=6graph")
        assert has_viz_command("graphx=4")
        assert not has_viz_command("paragraph")
        assert not has_viz_command("photograph")
        assert peel_edge_english("6graph") == "6"
        assert peel_edge_english("6please") == "6"
        assert peel_edge_english("velocity") == "velocity"
        assert peel_edge_english("mc^2") == "mc^2"


class TestTriangleSidesSignal:
    """`triangle with sides 3, 4, 5` must be detected as SSS — and requires
    both "triangle" AND a "sides" cue, so a bare "triangle" doesn't match."""

    def test_triangle_sides_signal(self):
        assert mtm.triangle_sides_signal("triangle with sides 3, 4, 5") == (3.0, 4.0, 5.0)

    def test_triangle_sides_signal_requires_sides_cue(self):
        assert mtm.triangle_sides_signal("triangle 3 4 5") is None

    def test_triangle_sides_signal_requires_triangle_word(self):
        assert mtm.triangle_sides_signal("sides 3, 4, 5") is None

    def test_triangle_angles_signal_aaa(self):
        assert mtm.triangle_angles_signal("A triangle with angles 120, 40, 20") == (
            120.0,
            40.0,
            20.0,
        )
        assert mtm.triangle_angles_signal("A triangle with 120°, 40°, 20°") == (
            120.0,
            40.0,
            20.0,
        )
        assert mtm.triangle_angles_signal("triangle with 120, 40 and 20 degrees") == (
            120.0,
            40.0,
            20.0,
        )
        assert mtm.triangle_angles_signal("A triangle with 120, 40, 20") is None
        assert mtm.triangle_angles_signal("triangle with sides 3, 4, 5") is None
        assert mtm.triangle_angles_signal("triangle base 8 height 5") is None

    def test_needs_symbolic_angle_only_triangle(self):
        assert mtm.needs_symbolic("A triangle with angles 120, 40, 20")
        assert not mtm.needs_symbolic("A triangle with 120, 40, 20")


class TestStatsSignal:
    def test_stats_signal_mean(self):
        op, numbers = mtm.stats_signal("mean of 1, 2, 3, 4")
        assert op == "mean"
        assert numbers == [1.0, 2.0, 3.0, 4.0]

    def test_stats_signal_standard_deviation(self):
        op, _ = mtm.stats_signal("standard deviation of 10, 20, 30")
        assert op == "stdev"

    def test_stats_signal_sample_standard_deviation(self):
        op, _ = mtm.stats_signal("sample standard deviation of 10, 20, 30")
        assert op == "sample_stdev"

    def test_stats_signal_population_standard_deviation(self):
        op, _ = mtm.stats_signal("population standard deviation of 10, 20, 30")
        assert op == "stdev"

    def test_stats_signal_sample_variance(self):
        op, _ = mtm.stats_signal("sample variance of 10, 20, 30")
        assert op == "sample_variance"

    def test_stats_signal_requires_two_plus_numbers(self):
        # "what do you mean by X" — no data list → no match.
        assert mtm.stats_signal("what do you mean by that") is None

    def test_stats_signal_mode_is_not_model(self):
        assert mtm.stats_signal("evaluate the model on 1, 2, 3, 4") is None
        op, numbers = mtm.stats_signal("mode of 1, 2, 3, 4")
        assert op == "mode"
        assert numbers == [1.0, 2.0, 3.0, 4.0]


class TestCombinatoricsSignal:
    @pytest.mark.parametrize(
        "text, expected_op",
        [
            ("5!", "factorial"),
            ("factorial of 6", "factorial"),
            ("5 choose 2", "combinations"),
            ("C(5,2)", "combinations"),
            ("5C2", "combinations"),
            ("P(5,2)", "permutations"),
            ("5P2", "permutations"),
            ("5 permute 2", "permutations"),
            ("5 permutation 2", "permutations"),
        ],
    )
    def test_combinatorics_signal(self, text, expected_op):
        op, _n, _k = mtm.combinatorics_signal(text)
        assert op == expected_op

    def test_combinatorics_factorial_k_is_none(self):
        op, _n, k = mtm.combinatorics_signal("5!")
        assert op == "factorial"
        assert k is None


class TestNumberTheorySignal:
    @pytest.mark.parametrize(
        "text, expected_op, expected_a, expected_b",
        [
            ("gcd of 12 and 18", "gcd", 12, 18),
            ("lcm of 4 and 6", "lcm", 4, 6),
            ("prime factorization of 60", "factorize", 60, None),
            ("is 17 prime", "is_prime", 17, None),
            ("is 91 a prime number", "is_prime", 91, None),
            ("10 mod 3", "mod", 10, 3),
            ("modular inverse of 3 mod 11", "mod_inverse", 3, 11),
            ("totient of 10", "totient", 10, None),
        ],
    )
    def test_number_theory_signal(self, text, expected_op, expected_a, expected_b):
        op, a, b = mtm.number_theory_signal(text)
        assert op == expected_op
        assert a == expected_a
        assert b == expected_b


class TestMatrixSignal:
    def test_matrix_signal_determinant(self):
        op, rows = mtm.matrix_signal("determinant of [[1,2],[3,4]]")
        assert op == "determinant"
        assert rows == [[1.0, 2.0], [3.0, 4.0]]

    def test_matrix_signal_inverse(self):
        op, _rows = mtm.matrix_signal("inverse of [[2,0],[1,3]]")
        assert op == "inverse"

    def test_matrix_signal_requires_bracket_notation(self):
        assert mtm.matrix_signal("determinant of 1 2 3 4") is None

    def test_matrix_signal_rejects_non_square(self):
        assert mtm.matrix_signal("determinant of [[1,2,3],[4,5,6]]") is None

    def test_matrix_signal_multiply_and_rref(self):
        op, rows = mtm.matrix_signal("multiply [[1,2],[3,4]] and [[0,1],[1,0]]")
        assert op == "multiply"
        assert rows == [[1.0, 2.0], [3.0, 4.0]]
        op, rows = mtm.matrix_signal("rref [[1,2,3],[4,5,6]]")
        assert op == "rref"
        assert rows == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        op, rows = mtm.matrix_signal("eigenvalues of [[2,0],[0,3]]")
        assert op == "eigenvalues"
        op, rows = mtm.matrix_signal("add [[1,2],[3,4]] and [[0,1],[1,0]]")
        assert op == "add"
        op, rows = mtm.matrix_signal("transpose [[1,2],[3,4]]")
        assert op == "transpose"


class TestParseLimit:
    def test_compact_limit(self):
        hit = mtm.parse_limit("lim x->0 sin(x)/x")
        assert hit is not None
        assert hit.var == "x"
        assert hit.point == "0"
        assert "sin(x)/x" in hit.expr

    def test_latex_limit(self):
        hit = mtm.parse_limit("\\lim_{x \\to 0} sin(x)/x")
        assert hit is not None
        assert hit.var == "x"
        assert hit.point == "0"

    def test_prose_limit_as_approaches(self):
        hit = mtm.parse_limit("find the limit of sin(x)/x as x approaches 0")
        assert hit is not None
        assert hit.var == "x"
        assert hit.point == "0"

    def test_infinity_limit(self):
        hit = mtm.parse_limit("lim x->infinity 1/x")
        assert hit is not None
        assert hit.point in ("infinity", "oo")

    def test_parse_limit_none(self):
        assert mtm.parse_limit("hello there") is None


class TestParseSeries:
    def test_prose_series(self):
        hit = mtm.parse_series("sum of x from n=1 to 10")
        assert hit is not None
        assert hit.var == "n"
        assert hit.start == "1"
        assert hit.end == "10"

    def test_latex_series(self):
        hit = mtm.parse_series("\\sum_{n=1}^{\\infty} 1/n**2")
        assert hit is not None
        assert hit.var == "n"
        assert hit.start == "1"
        assert hit.end in ("\\infty", "infinity")

    def test_parse_series_requires_keyword(self):
        assert mtm.parse_series("1 + 2 + 3") is None


class TestHasEquation:
    @pytest.mark.parametrize(
        "text",
        [
            "x + 2 = 5",
            "2*x + 3 = 7",
            "y = x^2",
        ],
    )
    def test_has_equation(self, text):
        assert mtm.has_equation(text)

    @pytest.mark.parametrize(
        "text",
        [
            "no equals here",
            "= 5",
            "x =",
            "== comparison",
        ],
    )
    def test_no_equation(self, text):
        assert not mtm.has_equation(text)


class TestLooksLikeMathExpr:
    @pytest.mark.parametrize(
        "text",
        ["x**2 + 3x", "x^2 - 4", "sin(x)/x", "1/n**2"],
    )
    def test_math(self, text: str) -> None:
        assert mtm.looks_like_math_expr(text)

    @pytest.mark.parametrize(
        "text",
        [
            "x squared plus 3x",
            "my hair are 2 inches long",
            "the tree are deep",
        ],
    )
    def test_english(self, text: str) -> None:
        assert not mtm.looks_like_math_expr(text)


class TestBareArithmetic:
    """Gate and extractor share ``bare_arithmetic_expr`` so dim-pair false
    matches (``8*2`` inside ``8-8*2``) cannot stamp Couldn't verify."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("8-8*2", "8-8*2"),
            ("7*8", "7*8"),
            ("8 × 5", "8 * 5"),
            ("8÷2", "8/2"),
            ("2^3", "2^3"),
            ("1+2+3", "1+2+3"),
            ("(8-8)*2", "(8-8)*2"),
            ("what is 7*8", "7*8"),
            ("what is the result of 7 + 9?", "7 + 9"),
            ("What is the sum of 3 + 5?", "3 + 5"),
            ("what is 9/9", "9/9"),
            ("what is 10-3", "10-3"),
            ("10-3", "10-3"),
            ("calculate 1+1", "1+1"),
            ("How would you calculate 1 + 1 + 1 + 1?", "1 + 1 + 1 + 1"),
            ("how do you calculate 2+2+2", "2+2+2"),
            ("10-3-2", "10-3-2"),
            ("100/5/2", "100/5/2"),
            ("-3+5", "-3+5"),
        ],
    )
    def test_accepts(self, text: str, expected: str) -> None:
        assert mtm.bare_arithmetic_expr(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "9/9",
            "555-1234",
            "9/11",
            "1+1",
            "8x5",
            "8 by 5",
            "hello",
            "what is a trapezoid",
            "9/7/2026",
            "1-800-273-8255",
        ],
    )
    def test_rejects(self, text: str) -> None:
        assert mtm.bare_arithmetic_expr(text) is None

    def test_dim_pair_still_sees_multiply_inside_arithmetic(self) -> None:
        # The matcher is unchanged — the gate must not use it alone.
        assert mtm.first_dim_pair("8-8*2") == (8.0, 2.0, "cm")
        assert mtm.geometry_dim_context("8-8*2") is False
        assert mtm.geometry_dim_context("a rectangle is 8×5 cm") is True


class TestLagrangePrimes:
    @pytest.mark.parametrize(
        "text",
        [
            "y'' of y = x^3 - 3x",
            "f(x) = x^3 - 3x, find f''(x)",
        ],
    )
    def test_calc_op_is_derivative(self, text: str) -> None:
        assert mtm.calc_op(text) == "derivative"

    def test_ode_assignment_is_not_a_derivative_op(self) -> None:
        assert mtm.calc_op("y' = 2x") is None

    def test_yall_is_not_a_derivative_op(self) -> None:
        assert mtm.calc_op("y'all coming to class") is None

    def test_plural_possessive_is_not_a_derivative_op(self) -> None:
        assert mtm.calc_op("Where is the teachers' lounge?") is None
        assert mtm.calc_op("the students' essays") is None

    def test_function_name_prime_is_still_a_derivative(self) -> None:
        assert mtm.calc_op("sin'(x)") == "derivative"
