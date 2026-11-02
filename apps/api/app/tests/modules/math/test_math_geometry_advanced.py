"""General triangle (SSS), trapezoid, parallelogram, and circle sector —
shape-library expansion beyond the original rectangle/square/triangle/
right-triangle/circle set."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math import match as math_match
from app.modules.math import solve as math_solve
from app.modules.math.schemas import (
    ParallelogramInput,
    SectorInput,
    TrapezoidInput,
    TriangleSidesInput,
)
from app.modules.math.solve.geometry import format_degree_label
from app.tests.modules.math.prompt_support import augment_prompt_messages


class TestTriangleSidesGeometry:
    def test_3_4_5_right_triangle(self):
        result = math_solve.triangle_sides_geometry(TriangleSidesInput(a=3, b=4, c=5))
        assert result.area == 6
        assert result.perimeter == 12
        assert result.angle_c_deg == pytest.approx(90, abs=0.01)

    def test_invalid_triangle_rejected(self):
        with pytest.raises(ValueError):
            TriangleSidesInput(a=1, b=1, c=10)

    def test_format_degree_label_rounds_near_integers(self):
        assert format_degree_label(119.9) == "120°"
        assert format_degree_label(90.0) == "90°"
        assert format_degree_label(36.87) == "36.9°"

    def test_sides_from_120_40_20_round_trip_angles(self):
        a, b, c = math_solve.sides_from_interior_angles(120, 40, 20)
        result = math_solve.triangle_sides_geometry(TriangleSidesInput(a=a, b=b, c=c, unit="units"))
        assert result.labels["angle_a"] == "120°"
        assert result.labels["angle_b"] == "40°"
        assert result.labels["angle_c"] == "20°"
        assert result.unit == "units"


class TestTrapezoidGeometry:
    def test_area(self):
        result = math_solve.trapezoid_geometry(TrapezoidInput(top=4, bottom=8, height=5))
        assert result.area == 30


class TestParallelogramGeometry:
    def test_area_and_perimeter(self):
        result = math_solve.parallelogram_geometry(ParallelogramInput(base=8, height=4, side=5))
        assert result.area == 32
        assert result.perimeter == 26

    def test_side_shorter_than_height_rejected(self):
        with pytest.raises(ValueError):
            ParallelogramInput(base=8, height=10, side=3)


class TestSectorGeometry:
    def test_quarter_circle(self):
        result = math_solve.sector_geometry(SectorInput(radius=4, angle_deg=90))
        # Quarter circle: area = pi * r^2 / 4, arc = 2*pi*r/4
        assert result.area == pytest.approx(12.566, abs=0.01)
        assert result.arc_length == pytest.approx(6.283, abs=0.01)


class TestNewShapeTextSignals:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("trapezoid top 3 bottom 5 height 4", (3.0, 5.0, 4.0)),
            ("trapezoid with bases 3 cm and 5 cm and height 4 cm", (3.0, 5.0, 4.0)),
            ("trapezoid height 4 with bases 3 and 5", (3.0, 5.0, 4.0)),
        ],
    )
    def test_trapezoid_dimension_phrasings(
        self, text: str, expected: tuple[float, float, float]
    ) -> None:
        assert math_match.trapezoid_dimensions(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "trapezoid with bases 3 and height 4",
            "trapezoid with bases 3 and 5",
            "what is a trapezoid?",
        ],
    )
    def test_incomplete_trapezoid_dimensions_are_not_invented(self, text: str) -> None:
        assert math_match.trapezoid_dimensions(text) is None

    def test_triangle_sides_signal(self):
        assert math_match.triangle_sides_signal("triangle with sides 3, 4, 5") == (
            3.0,
            4.0,
            5.0,
        )
        assert math_match.triangle_sides_signal("draw a triangle") is None

    def test_needs_symbolic_for_new_shapes(self):
        for text in (
            "draw a trapezoid",
            "parallelogram with base 8 and height 4",
            "sector of a circle with radius 5 and angle 90",
            "triangle with sides 3, 4, 5",
        ):
            assert math_match.needs_symbolic(text) is True
        # "sector" alone (no geometry context) must NOT false-positive on
        # the extremely common non-math usage ("the tech sector").
        assert math_match.needs_symbolic("the tech sector is booming") is False
        # Partial sector dims used to invent the missing angle as 90° —
        # do not enter the verified path without both radius and angle.
        assert math_match.needs_symbolic("sector of a circle with radius 5") is False


class TestAugmentPromptMessagesForNewShapes:
    @pytest.mark.asyncio
    async def test_sector_not_stolen_by_generic_circle_extractor(self):
        """Regression: _extract_circle_intent used to run before
        _extract_sector_intent, so "sector of a circle with radius 5 and
        angle 90" silently produced a plain circle fence instead of a
        sector — same bug shape as the multi-equation system bug fixed
        earlier in this file's siblings."""
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "sector of a circle with radius 5 and angle 90"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "sector"

    @pytest.mark.asyncio
    async def test_triangle_sides_not_stolen_by_generic_triangle_extractor(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "triangle with sides 3, 4, 5"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "triangle_sides"
        assert verified.canonical_fence["show_altitude"] is False
        assert verified.canonical_fence["show_ticks"] is True
        # Scalene — no extra interior cues unless the user asked for them.
        assert verified.canonical_fence["show_median"] is False

    @pytest.mark.asyncio
    async def test_angle_only_triangle_uses_relative_units_not_cm(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "A triangle with angles 120, 40, 20"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        out, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "triangle_sides"
        assert verified.canonical_fence["unit"] == "units"
        labels = verified.canonical_fence["labels"]
        assert labels["angle_a"] == "120°"
        assert labels["angle_b"] == "40°"
        assert labels["angle_c"] == "20°"
        injected = " ".join(m["content"] for m in out if m["role"] == "system")
        assert "centimetres" in injected.lower()
        assert verified.canonical_answer is not None
        assert "120°" in verified.canonical_answer

    @pytest.mark.asyncio
    async def test_isosceles_triangle_sides_enables_median_cue(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "triangle with sides 5, 5, 6"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        assert verified.canonical_fence is not None
        assert verified.canonical_fence["type"] == "triangle_sides"
        assert verified.canonical_fence["show_median"] is True

    @pytest.mark.asyncio
    async def test_plain_circle_still_works(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "circle with radius 4"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        assert verified.canonical_fence["type"] == "circle"
