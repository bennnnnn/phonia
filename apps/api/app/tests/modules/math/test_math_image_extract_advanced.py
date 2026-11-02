"""Camera OCR beyond a single equation — systems and inequalities.

Before this, ANY photographed math problem that wasn't exactly one "lhs=rhs"
equation (a system of equations, a bare inequality) silently lost the
SymPy-verified path and fell back to the model's unverified free-text guess,
regardless of how well OCR itself extracted the text.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.schemas import MathImageExtract
from app.tests.modules.math.prompt_support import augment_prompt_messages


class TestMathImageExtractSchema:
    def test_defaults_to_equation_kind(self):
        parsed = MathImageExtract(lhs="2*x+3", rhs="7", variables=["x"])
        assert parsed.kind == "equation"

    def test_system_kind_with_full_equations(self):
        parsed = MathImageExtract(
            kind="system",
            lhs="x+y",
            rhs="5",
            equations=[("x+y", "5"), ("x-y", "1")],
            variables=["x", "y"],
        )
        assert parsed.kind == "system"
        assert len(parsed.equations) == 2

    def test_system_kind_degrades_to_equation_when_equations_incomplete(self):
        """Graceful degrade: a vision model that says kind="system" but
        only extracted one equation must not lose the whole extraction —
        fall back to treating lhs/rhs as a single equation instead of
        failing schema validation entirely."""
        parsed = MathImageExtract(
            kind="system", lhs="x+y", rhs="5", equations=[("x+y", "5")], variables=["x", "y"]
        )
        assert parsed.kind == "equation"

    def test_inequality_kind_with_valid_comparator(self):
        parsed = MathImageExtract(
            kind="inequality", lhs="x**2-1", rhs="0", comparator=">", variables=["x"]
        )
        assert parsed.kind == "inequality"

    def test_inequality_kind_degrades_to_equation_without_comparator(self):
        parsed = MathImageExtract(kind="inequality", lhs="x", rhs="0", variables=["x"])
        assert parsed.kind == "equation"

    def test_inequality_kind_degrades_to_equation_with_invalid_comparator(self):
        parsed = MathImageExtract(
            kind="inequality", lhs="x", rhs="0", comparator="!=", variables=["x"]
        )
        assert parsed.kind == "equation"

    def test_calculus_kind_requires_expr_and_operation(self):
        parsed = MathImageExtract(
            kind="calculus",
            operation="differentiate",
            expr="x**2",
            variables=["x"],
        )
        assert parsed.kind == "calculus"
        assert parsed.found is True

    def test_incomplete_calculus_marks_not_found(self):
        parsed = MathImageExtract(kind="calculus", expr="x**2", variables=["x"])
        assert parsed.found is False

    def test_incomplete_calculus_degrades_to_equation_when_sides_present(self):
        parsed = MathImageExtract(kind="calculus", lhs="2*x", rhs="4", variables=["x"])
        assert parsed.kind == "equation"
        assert parsed.found is True

    def test_limit_and_graph_and_geometry_kinds(self):
        limit = MathImageExtract(kind="limit", expr="sin(x)/x", limit_point="0", variables=["x"])
        assert limit.kind == "limit"
        graph = MathImageExtract(kind="graph", expr="x**2", variables=["x"])
        assert graph.kind == "graph"
        rect = MathImageExtract(kind="rectangle", width=8, height=5, unit="cm")
        assert rect.kind == "rectangle"
        circle = MathImageExtract(kind="circle", radius=3, unit="cm")
        assert circle.kind == "circle"

    def test_definite_integral_keeps_both_bounds(self):
        parsed = MathImageExtract(
            kind="calculus",
            operation="integrate",
            expr="x**2",
            integral_lower="0",
            integral_upper="1",
            variables=["x"],
        )
        assert parsed.kind == "calculus"
        assert parsed.integral_lower == "0"
        assert parsed.integral_upper == "1"

    def test_half_filled_integral_bounds_drop_to_indefinite(self):
        parsed = MathImageExtract(
            kind="calculus",
            operation="integrate",
            expr="x**2",
            integral_lower="0",
            variables=["x"],
        )
        assert parsed.kind == "calculus"
        assert parsed.integral_lower is None
        assert parsed.integral_upper is None

    def test_triangle_sides_and_statistics_kinds(self):
        tri = MathImageExtract(kind="triangle_sides", tri_a=3, tri_b=4, tri_c=5, unit="cm")
        assert tri.kind == "triangle_sides"
        stats = MathImageExtract(kind="statistics", stats_op="mean", stats_numbers=[1, 3, 5, 7])
        assert stats.kind == "statistics"
        assert stats.stats_op == "mean"

    def test_incomplete_triangle_sides_marks_not_found(self):
        parsed = MathImageExtract(kind="triangle_sides", tri_a=3, tri_b=4)
        assert parsed.found is False

    def test_incomplete_statistics_marks_not_found(self):
        parsed = MathImageExtract(kind="statistics", stats_op="mean", stats_numbers=[5])
        assert parsed.found is False


class TestAugmentPromptMessagesFromImageExtract:
    @pytest.mark.asyncio
    async def test_system_extract_solves_full_system(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(
            kind="system",
            lhs="x+y",
            rhs="5",
            equations=[("x+y", "5"), ("x-y", "1")],
            variables=["x", "y"],
        )
        text = "Solve the math problem in this image step by step."
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(
            messages, text, settings, has_image_attachment=True, image_math_extract=extract
        )
        assert verified is not None
        assert "x = 3" in verified.text
        assert "y = 2" in verified.text

    @pytest.mark.asyncio
    async def test_inequality_extract_solves_inequality(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(
            kind="inequality", lhs="x**2-1", rhs="0", comparator=">", variables=["x"]
        )
        text = "Solve the math problem in this image step by step."
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(
            messages, text, settings, has_image_attachment=True, image_math_extract=extract
        )
        assert verified is not None
        assert "Inequality" in verified.text

    @pytest.mark.asyncio
    async def test_plain_equation_extract_is_unaffected(self):
        """Backward compat: the original single-equation shape (no kind
        field set explicitly) still produces the same equation-solve path."""
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(lhs="2*x+3", rhs="7", variables=["x"])
        text = "Solve the math problem in this image step by step."
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(
            messages, text, settings, has_image_attachment=True, image_math_extract=extract
        )
        assert verified is not None
        assert "Solutions" in verified.text

    @pytest.mark.asyncio
    async def test_calculus_extract_differentiates(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(
            kind="calculus",
            operation="differentiate",
            expr="x**2",
            variables=["x"],
        )
        text = "Solve the math problem in this image step by step."
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(
            messages, text, settings, has_image_attachment=True, image_math_extract=extract
        )
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "answer"
        assert "2" in verified.canonical_fence["content"]

    @pytest.mark.asyncio
    async def test_limit_extract_evaluates(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(
            kind="limit",
            expr="x**2",
            limit_point="3",
            variables=["x"],
        )
        text = "Solve the math problem in this image step by step."
        _, verified = await augment_prompt_messages(
            [{"role": "user", "content": text}],
            text,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )
        assert verified is not None
        assert verified.canonical_fence == {"type": "answer", "content": "9"}

    @pytest.mark.asyncio
    async def test_unicode_equation_extract_solves(self):
        """OCR multiply-sign must ascii-ize through normalize so SymPy can verify."""
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(lhs="2\u00d7x+3", rhs="7", variables=["x"])
        text = "Solve the math problem in this image step by step."
        _, verified = await augment_prompt_messages(
            [{"role": "user", "content": text}],
            text,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )
        assert verified is not None
        assert "2" in verified.text
        assert verified.canonical_fence is not None

    @pytest.mark.asyncio
    async def test_rectangle_extract_builds_geometry_fence(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(kind="rectangle", width=8, height=5, unit="cm")
        text = "Solve the math problem in this image step by step."
        _, verified = await augment_prompt_messages(
            [{"role": "user", "content": text}],
            text,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "rectangle"

    @pytest.mark.asyncio
    async def test_definite_integral_extract_evaluates(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(
            kind="calculus",
            operation="integrate",
            expr="x**2",
            integral_lower="0",
            integral_upper="1",
            variables=["x"],
        )
        text = "Solve the math problem in this image step by step."
        _, verified = await augment_prompt_messages(
            [{"role": "user", "content": text}],
            text,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "answer"
        # definite integral of x^2 from 0 to 1 is 1/3
        content = verified.canonical_fence["content"]
        assert "1/3" in content or "\\frac{1}{3}" in content

    @pytest.mark.asyncio
    async def test_triangle_sides_extract_builds_geometry_fence(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(kind="triangle_sides", tri_a=3, tri_b=4, tri_c=5, unit="cm")
        text = "Solve the math problem in this image step by step."
        _, verified = await augment_prompt_messages(
            [{"role": "user", "content": text}],
            text,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "triangle_sides"

    @pytest.mark.asyncio
    async def test_statistics_extract_computes_mean(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        extract = MathImageExtract(kind="statistics", stats_op="mean", stats_numbers=[1, 3, 5, 7])
        text = "Solve the math problem in this image step by step."
        _, verified = await augment_prompt_messages(
            [{"role": "user", "content": text}],
            text,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )
        assert verified is not None
        assert verified.canonical_fence == {"type": "answer", "content": "4"}
