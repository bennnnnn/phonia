"""Every verified geometry family uses the same readable worked hierarchy."""

import pytest

from app.core.config import Settings
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent
from app.services.workout import as_formula_heading


def _reply(query: str) -> str:
    intent = extract_math_intent(query)
    assert intent is not None
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    return reply


@pytest.mark.parametrize(
    "query,formula,substitution",
    [
        (
            "Find the area of a rectangle 4 by 5",
            r"$A = l \times w$",
            r"$A = 5 \times 4 = 20$",
        ),
        (
            "Find the perimeter of a rectangle 4 by 5",
            r"$P = 2(l + w)$",
            r"$P = 2(5 + 4) = 18$",
        ),
        (
            "Find the diagonal of a rectangle 3 by 4",
            r"$d^2 = l^2 + w^2$",
            r"$d = \sqrt{4^2 + 3^2} = \sqrt{16 + 9} = \sqrt{25} = 5$",
        ),
        ("Find the area of a square side 4", r"$A = s^2$", r"$A = 4^2 = 16$"),
        ("Find the perimeter of a square side 4", r"$P = 4s$", r"$P = 4 \times 4 = 16$"),
        (
            "Find the diagonal of a square side 4",
            r"$d = s\sqrt{2}$",
            r"$d = 4\sqrt{2} \approx 5.6569$",
        ),
        (
            "Find the area of a triangle base 6 height 5",
            r"$A = \frac{1}{2}bh$",
            r"$A = \frac{1}{2} \times 6 \times 5 = 15$",
        ),
        (
            "Find the hypotenuse of a right triangle legs 3 and 4",
            r"$c^2 = a^2 + b^2$",
            r"$c = \sqrt{3^2 + 4^2} = \sqrt{9 + 16} = \sqrt{25} = 5$",
        ),
        (
            "Find the perimeter of a right triangle legs 3 and 4",
            r"$P = a + b + c$",
            r"$P = 3 + 4 + 5 = 12$",
        ),
        (
            "Find the area of a triangle with sides 3,4,5",
            r"$A = \sqrt{s(s-a)(s-b)(s-c)}$",
            r"$s = \frac{3+4+5}{2} = 6$",
        ),
        (
            "Find the perimeter of a triangle with sides 3,4,5",
            r"$P = a + b + c$",
            r"$P = 3 + 4 + 5 = 12$",
        ),
        (
            "Find the area of a parallelogram base 8 height 4 side 5",
            r"$A = bh$",
            r"$A = 8 \times 4 = 32$",
        ),
        (
            "Find the perimeter of a parallelogram base 8 height 4 side 5",
            r"$P = 2(b+s)$",
            r"$P = 2(8 + 5) = 26$",
        ),
        (
            "Find the area of a trapezoid top 4 bottom 8 height 5",
            r"$A = \frac{1}{2}(a+b)h$",
            r"$A = \frac{1}{2}(4+8) \times 5 = 30$",
        ),
        (
            "Find the area of a circle radius 3",
            r"$A = \pi r^2$",
            r"$A = \pi(3)^2 = 9\pi \approx 28.27$",
        ),
        (
            "Find the circumference of a circle radius 3",
            r"$C = 2\pi r$",
            r"$C = 2\pi(3) = 6\pi \approx 18.85$",
        ),
        (
            "Find the diameter of a circle radius 3",
            r"$d = 2r$",
            r"$d = 2 \times 3 = 6$",
        ),
        (
            "Find the area of a sector with radius 4 cm and angle 90 degrees",
            r"$A = \frac{\theta}{360^\circ}\pi r^2$",
            r"$A = \frac{90^\circ}{360^\circ}\pi(4)^2 \approx 12.5664$",
        ),
        (
            "Find the arc length of a sector with radius 4 cm and angle 90 degrees",
            r"$L = \frac{\theta}{360^\circ}(2\pi r)$",
            r"$L = \frac{90^\circ}{360^\circ}(2\pi \times 4) \approx 6.28$",
        ),
    ],
)
def test_geometry_formula_and_substitution_are_separate_verified_lines(
    query: str, formula: str, substitution: str
) -> None:
    reply = _reply(query)
    headings = ["**Given**", "**Required**", "**Solution**", "**Formula**", "**Substitution**"]
    read = as_formula_heading(reply)
    positions = [read.index(heading) for heading in [*headings, "**Answer**"]]
    assert positions == sorted(positions)
    assert formula in reply
    assert substitution in reply
    assert "```geometry" in reply
    assert reply.count("```answer") == 1
    assert reply.count("```geometry") == 1


def test_natural_rectangle_wording_draws_exact_sides_and_trims_decimal_zeroes() -> None:
    reply = _reply("a rectangle area with sides 4.04, 5")
    assert "$w = 4.04" in reply and "— width" in reply
    assert "$l = 5" in reply and "— length" in reply
    assert r"$A = 5 \times 4.04 = 20.2$" in reply
    assert "20.20" not in reply
    assert '"width":4.04' in reply and '"height":5.0' in reply


@pytest.mark.parametrize(
    "query",
    [
        "A rectangle has a length of 4 units and a width of 3 units. What is the area?",
        "What is the area of a rectangle with width 3 and length 4?",
        "A rectangle is 3 units wide and 4 units long. Find its area.",
    ],
)
def test_natural_named_rectangle_uses_compact_verified_working(query: str) -> None:
    reply = _reply(query)
    assert "$l = 4" in reply and "— length" in reply
    assert "$w = 3" in reply and "— width" in reply
    assert r"$A = l \times w$" in reply
    assert r"$A = 4 \times 3 = 12$" in reply
    assert r"```answer" + "\n" + r"12\ \mathrm{units}^{2}" + "\n```" in reply
    assert "**Given**  \n$l = " in reply
    assert "— length  \n$w = " in reply


@pytest.mark.parametrize(
    "query,target,symbol",
    [
        (
            "A rectangle has area 12 square units and width 3 units. Find the length.",
            "$l$ — length",
            "l",
        ),
        (
            "Find the width of a rectangle with area 12 and length 4.",
            "$w$ — width",
            "w",
        ),
    ],
)
def test_rectangle_area_and_one_side_finds_the_other_side(
    query: str, target: str, symbol: str
) -> None:
    reply = _reply(query)
    assert target in reply
    assert r"$A = l \times w$" in reply
    assert rf"${symbol} = \frac{{A}}" in reply
    assert "```answer\n" in reply
    assert reply.count("```answer") == 1


@pytest.mark.parametrize(
    "query",
    [
        "Find the area of a triangle with sides 3,4,5",
        # The shape first, then the question: the battery's wording.
        "a triangle has sides 3, 4 and 5. what is its area?",
    ],
)
def test_heron_shows_every_row_down_to_the_area(query: str) -> None:
    """The working stopped at the root of the differences and jumped to 6."""
    reply = _reply(query)
    assert (
        r"$A = \sqrt{6(6-3)(6-4)(6-5)} = \sqrt{6 \times 3 \times 2 \times 1} = \sqrt{36} = 6$"
        in reply
    )
