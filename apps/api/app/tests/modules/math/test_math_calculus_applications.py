"""Area between curves, arc length, volume of revolution, and even/odd.

This replaces the blanket refusal added in #1344, which was itself a response to
"area between y=x and y=x^2 from 0 to 1" being answered with the *intersection
points* of its two curves. The refusal stopped the wrong answer; this answers
the question.

Two things here are worth more than the formulas.

**Signed cancellation.** The area between sin(x) and 0 over a full period is 4,
not 0. Integrating the signed difference would let the half below the axis
cancel the half above it, and the answer would be exactly zero — a number that
looks like a result. The integral is split at every crossing instead.

**Partial bound matches.** "from 0 to 2*pi" originally matched just the `2`,
silently answering on [0, 2]. That is the same failure the whole refusal existed
to prevent, reintroduced through the bounds rather than the curves, so the bound
pattern is ordered longest-first and closed with a lookahead.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import _build_verified_block, extract_math_intent


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_math_intent(text)
    if intent is None:
        return None
    block = _build_verified_block(intent, _settings())
    return None if block is None else block.canonical_answer


def _intent(text: str):
    intent = extract_math_intent(text)
    assert intent is not None, f"no intent for {text!r}"
    return intent


# (question, expected school_op, expected answer)
VERIFIED: list[tuple[str, str, str]] = [
    # --- area between curves -------------------------------------------
    ("area between y=x and y=x^2 from 0 to 1", "area_between_curves", "\\frac{1}{6}"),
    (
        "find the area between the curves y=x and y=x^2 from 0 to 1",
        "area_between_curves",
        "\\frac{1}{6}",
    ),
    ("area between y=cos(x) and y=0 from 0 to pi/2", "area_between_curves", "1"),
    ("area between y=x and y=0 on [0, 2]", "area_between_curves", "2"),
    # --- arc length -----------------------------------------------------
    (
        "arc length of y=x^(3/2) from 0 to 1",
        "arc_length",
        "\\frac{13 \\sqrt{13}}{27} - \\frac{8}{27}",
    ),
    # --- volume of revolution -------------------------------------------
    (
        "volume of revolution of y=x from 0 to 1 about the x-axis",
        "volume_revolution_x",
        "\\frac{\\pi}{3}",
    ),
    (
        "volume of revolution of y=x^2 from 0 to 1 about the x-axis",
        "volume_revolution_x",
        "\\frac{\\pi}{5}",
    ),
    # --- even / odd ------------------------------------------------------
    ("is f(x)=x^3 even or odd", "function_symmetry", "odd"),
    ("is f(x)=x^2 even or odd", "function_symmetry", "even"),
    ("is f(x)=x^2+x even or odd", "function_symmetry", "neither"),
    ("is f(x)=cos(x) even or odd", "function_symmetry", "even"),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_calculus_applications_answer(text: str, op: str, answer: str) -> None:
    assert _intent(text).school_op == op
    assert _verified_answer(text) == answer


# ---------------------------------------------------------------------------
# The two defects found while building this, pinned by value.
# ---------------------------------------------------------------------------


def test_a_region_below_the_axis_does_not_cancel_one_above_it() -> None:
    """sin(x) against 0 over a full period is 4, and signed integration gives 0.

    Zero is the dangerous answer here: it is not an error, it is a number, and
    a verified block would ship it.
    """
    assert (
        _verified_answer("find the area between the curves y=sin(x) and y=0 from 0 to 2*pi") == "4"
    )
    # Half the period is 2, so the full period cannot be 0 *or* 2.
    assert _verified_answer("area between y=sin(x) and y=0 from 0 to pi") == "2"


def test_a_bound_is_matched_whole_or_not_at_all() -> None:
    """ "from 0 to 2*pi" once matched just the 2, answering on [0, 2]."""
    intent = _intent("area between y=sin(x) and y=0 from 0 to 2*pi")
    assert intent.integral_upper == "2*pi"

    for text, upper in [
        ("area between y=x and y=0 from 0 to pi/2", "pi/2"),
        ("area between y=x and y=0 from 0 to 1/2", "1/2"),
        ("area between y=x and y=0 from 0 to 2*pi", "2*pi"),
    ]:
        assert _intent(text).integral_upper == upper


@pytest.mark.parametrize(
    "text,shown,typed",
    [
        ("area under sin(x) from 0 to 2*pi", r"2 \pi", "2*pi"),
        ("area between y=cos(x) and y=0 from 0 to pi/2", r"\frac{\pi}{2}", "pi/2"),
        ("arc length of y = 2x from 0 to pi", r"\pi", "pi"),
        ("volume of y = sqrt(x) from 0 to pi revolved about the x-axis", r"\pi", "pi"),
        ("volume of y = x from 0 to pi revolved about the y-axis", r"\pi", "pi"),
    ],
)
def test_the_working_prints_its_bounds_in_tex(text: str, shown: str, typed: str) -> None:
    """``0 \\le x \\le 2*pi`` and ``\\int_{0}^{2*pi}``: the bound as typed, not as maths."""
    intent = _intent(text)
    block = _build_verified_block(intent, _settings())
    assert block is not None and block.direct_reply is not None
    working = block.direct_reply
    assert rf"0 \le x \le {shown}$" in working
    assert rf"\int_{{0}}^{{{shown}}}" in working
    # Every place a bound is printed: the interval, integral limits, [F]_a^b.
    for written in (rf"\le {typed}$", f"^{{{typed}}}", f"[0, {typed}]"):
        assert written not in working


def test_the_area_answer_is_not_the_intersection_points() -> None:
    """The original defect, still pinned now that the question is answered."""
    answer = _verified_answer("area between y=x and y=x^2 from 0 to 1")
    assert answer == "\\frac{1}{6}"
    assert answer != "x = 0, y = 0; x = 1, y = 1"


# ---------------------------------------------------------------------------
# Refusals. Everything the codebase still cannot close.
# ---------------------------------------------------------------------------

REFUSED = [
    # No closed form for the arc length integral.
    "arc length of sin(x) from 0 to 1",
    # The axis decides the formula — disks about x, shells about y — so an
    # unnamed axis is not assumed.
    "volume of revolution of y=x from 0 to 1",
    # No interval to integrate over, and no single enclosed region.
    "area between y=sin(x) and y=cos(x)",
    "arc length of y=x^2",
    "area under y=x^2",
    # Still unimplemented shapes, still refused rather than answered sideways.
    "volume of the region bounded by y=x and y=0",
    # A shell volume straddling its own axis is not a volume.
    "volume of revolution of y=1 from -1 to 1 about the y-axis",
]


@pytest.mark.parametrize("text", REFUSED)
def test_unclosable_regions_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


NOT_THESE = [
    # A genuine simultaneous system, on the very curves the area question uses.
    ("solve y = x and y = x^2", "x = 0, y = 0; x = 1, y = 1"),
    ("solve 2x + y = 5 and x - y = 1", "x = 2, y = 1"),
    # Geometry areas and volumes name no region between curves.
    ("what is the area of a rectangle 3 by 4", "12"),
    ("what is the area of a circle with radius 5", "78.54"),
    # The definite integral path is untouched.
    ("integrate x^2 from 0 to 1", "\\frac{1}{3}"),
]


@pytest.mark.parametrize("text,answer", NOT_THESE, ids=[row[0][:40] for row in NOT_THESE])
def test_neighbouring_kinds_are_untouched(text: str, answer: str) -> None:
    assert _verified_answer(text) == answer


PROSE = [
    "what is the area between the two teams in the league",
    "the volume of support has been rotating between 3 people",
    "we need more coverage between 2 and 4 pm",
    "is the release even or odd numbered",
]


@pytest.mark.parametrize("text", PROSE)
def test_prose_does_not_reach_the_verified_path(text: str) -> None:
    assert _verified_answer(text) is None
