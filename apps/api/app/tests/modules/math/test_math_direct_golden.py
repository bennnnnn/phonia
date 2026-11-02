"""Golden direct replies: each geometry working and each literal plot, byte for byte.

``golden/`` holds the exact reply for realistic prompts: at least one for every
(kind, quantity) the geometry working lays out, and the literal point and
vertical-line plots (with requests that must keep the model). A deliberate
layout change regenerates them:

    uv run python -m app.tests.modules.math.test_math_direct_golden
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.direct_geometry_working import _WORKINGS
from app.modules.math.tools.extract import extract_math_intent

GOLDEN = Path(__file__).with_name("golden")
GEOMETRY_FIXTURE = GOLDEN / "direct_geometry_working.json"
PLOT_FIXTURE = GOLDEN / "direct_plots.json"

# (kind, quantity) -> prompts a student would type. An inverse rectangle is an
# area question asking for a side.
GEOMETRY_PROMPTS: dict[tuple[str, str], tuple[str, ...]] = {
    ("rectangle", "area"): (
        "Find the area of a rectangle 4 by 5",
        "What is the area of a rectangle 8 by 5 cm?",
        "a rectangle area with sides 4.04, 5",
        "What is the area of a rectangle with width 3 and length 4?",
        "A rectangle is 3 units wide and 4 units long. Find its area.",
        "A rectangle has a length of 3 m and a width of 7 m. What is the area?",
        "A rectangle has area 12 square units and width 3 units. Find the length.",
        "Find the width of a rectangle with area 12 and length 4.",
        "A rectangle has area 0.00012 and width 0.01. Find the length.",
    ),
    ("rectangle", "perimeter"): (
        "Find the perimeter of a rectangle 4 by 5",
        "calculate the perimeter of a rectangle 9 by 2 m",
        "A rectangle has length 6 cm and width 2 cm. Find the perimeter.",
    ),
    ("rectangle", "diagonal"): (
        "Find the diagonal of a rectangle 3 by 4",
        "A rectangle has length 8 and width 6. Find the diagonal.",
    ),
    ("rectangle", "area_and_perimeter"): (
        "A rectangle has length 5 m and width 3 m. Find its area and perimeter.",
    ),
    ("square", "area"): (
        "Find the area of a square side 4",
        "what is the area of a square side 2.5 cm",
    ),
    ("square", "perimeter"): ("Find the perimeter of a square side 4",),
    ("square", "diagonal"): ("Find the diagonal of a square side 4",),
    ("triangle", "area"): (
        "Find the area of a triangle base 6 height 5",
        "What is the area of a triangle with base 10 cm and height 4 cm?",
    ),
    ("right_triangle", "area"): ("Find the area of a right triangle legs 3 and 4",),
    ("right_triangle", "hypotenuse"): (
        "Find the hypotenuse of a right triangle legs 3 and 4",
        "a right triangle has legs 5 and 12, find the hypotenuse",
    ),
    ("right_triangle", "perimeter"): ("Find the perimeter of a right triangle legs 3 and 4",),
    ("triangle_sides", "area"): (
        "Find the area of a triangle with sides 3,4,5",
        "What is the area of a triangle with sides 5, 6 and 7 cm?",
    ),
    ("triangle_sides", "perimeter"): ("Find the perimeter of a triangle with sides 3,4,5",),
    ("parallelogram", "area"): ("Find the area of a parallelogram base 8 height 4 side 5",),
    ("parallelogram", "perimeter"): (
        "Find the perimeter of a parallelogram base 8 cm height 4 cm side 5 cm",
    ),
    ("trapezoid", "area"): (
        "Find the area of a trapezoid top 4 bottom 8 height 5",
        "find the area of a trapezium with bases 6 and 10 and height 4 cm",
    ),
    ("circle", "area"): (
        "Find the area of a circle radius 3",
        "What is the area of a circle with diameter 10 cm?",
    ),
    ("circle", "circumference"): (
        "Find the circumference of a circle radius 3",
        "find the circumference of a circle diameter 7 m",
    ),
    ("circle", "diameter"): ("Find the diameter of a circle radius 3",),
    ("sector", "area"): ("Find the area of a sector with radius 4 cm and angle 90 degrees",),
    ("sector", "arc_length"): (
        "Find the arc length of a sector with radius 4 cm and angle 90 degrees",
        "arc length of a circle sector radius 6 angle 60",
    ),
    ("cube", "volume"): ("Find the volume of a cube side 3 cm",),
    ("cube", "surface_area"): ("what is the surface area of a cube with side 2.5 m",),
    ("rectangular_prism", "volume"): ("Find the volume of a rectangular prism 2 by 3 by 4 cm",),
    ("rectangular_prism", "surface_area"): (
        "Find the total surface area of a cuboid 2 by 3 by 4 m",
    ),
    ("cylinder", "volume"): ("Find the volume of a cylinder radius 3 height 5 cm",),
    ("cylinder", "surface_area"): (
        "Find the surface area of a cylinder with radius 2 and height 7 cm",
    ),
    ("cone", "volume"): ("Find the volume of a cone radius 3 height 4 cm",),
    ("cone", "surface_area"): ("Find the surface area of a cone radius 5 height 12 m",),
    ("sphere", "volume"): ("Find the volume of a sphere radius 3 cm",),
    ("sphere", "surface_area"): ("calculate the surface area of a sphere with radius 1.5 m",),
    ("pyramid", "volume"): ("Find the volume of a square pyramid side 6 height 4 cm",),
    ("pyramid", "surface_area"): (
        "Find the surface area of a square pyramid with side 10 and height 12 cm",
    ),
}

PLOT_PROMPTS: tuple[str, ...] = (
    "Plot the point (2,3)",
    "Mark point (-2,3.5)",
    "Please graph the point (0,0).",
    "Show the point (1.5, -4)",
    "plot point 2, 3",
    "Plot the point ( 2 , 3 )?",
    "Plot the point (2.0, 3)",
    "Plot x=4",
    "Graph x=-3",
    "Graph the line x=0",
    "plot the vertical line x = 2.5",
    # Each of these keeps the model: more than the literal plot was asked.
    "Plot the point (2,3) and explain the coordinates",
    "Plot the point (2.3)",
    "Plot the point $(2,3)$",
    "Plot the point (2,3). Use a grid.",
    "Plot x=4 and explain why it is vertical",
)


def _reply(prompt: str) -> str | None:
    intent = extract_math_intent(prompt)
    if intent is None:
        return None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    return None if verified is None else maybe_direct_math_reply(verified, prompt)


def _golden(path: Path) -> dict[str, str | None]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["prompt"]: row["reply"] for row in rows}


@pytest.mark.parametrize(
    "kind,quantity,prompt",
    [(*pair, prompt) for pair, prompts in GEOMETRY_PROMPTS.items() for prompt in prompts],
)
def test_direct_geometry_working_matches_golden(kind: str, quantity: str, prompt: str) -> None:
    reply = _reply(prompt)
    assert reply is not None and "**Substitution**" in reply, (kind, quantity)
    assert reply == _golden(GEOMETRY_FIXTURE)[prompt]


@pytest.mark.parametrize("prompt", PLOT_PROMPTS)
def test_direct_plot_matches_golden(prompt: str) -> None:
    assert _reply(prompt) == _golden(PLOT_FIXTURE)[prompt]


def test_every_working_in_the_table_has_a_golden_prompt() -> None:
    assert set(GEOMETRY_PROMPTS) == set(_WORKINGS)


def test_golden_fixtures_hold_exactly_these_prompts() -> None:
    geometry = {prompt for prompts in GEOMETRY_PROMPTS.values() for prompt in prompts}
    assert set(_golden(GEOMETRY_FIXTURE)) == geometry
    assert set(_golden(PLOT_FIXTURE)) == set(PLOT_PROMPTS)


def _regenerate() -> None:
    geometry = [
        {"kind": kind, "quantity": quantity, "prompt": prompt, "reply": _reply(prompt)}
        for (kind, quantity), prompts in GEOMETRY_PROMPTS.items()
        for prompt in prompts
    ]
    plots = [{"prompt": prompt, "reply": _reply(prompt)} for prompt in PLOT_PROMPTS]
    for path, rows in ((GEOMETRY_FIXTURE, geometry), (PLOT_FIXTURE, plots)):
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    _regenerate()
