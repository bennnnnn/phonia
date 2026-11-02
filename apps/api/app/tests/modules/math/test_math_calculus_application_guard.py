"""The funnel guard for region questions the solvers decline.

History matters here, because this file has now been right twice for different
reasons.

"Area between y=x and y=x^2 from 0 to 1" was once answered
`x = 0, y = 0; x = 1, y = 1` — where the curves *cross*. The area is 1/6. The
simultaneous-equation extractor had claimed it and ignored both "area between"
and the bounds. #1344 refused every region question outright, and this file
asserted those refusals.

Those questions are answered properly now (see
`test_math_calculus_applications.py`), so the refusals moved rather than
vanished: the guard runs *after* the application extractors instead of before
them. What they claim is let through; what they decline is still refused.

That ordering is the whole point, and narrowing the guard to only the
unimplemented wordings reopened the original bug within minutes — "area between
y=x and y=x^2" with no stated interval is declined for a missing given, fell
through to the algebra side, and answered with the intersection points again.
Declining means a given is missing, not that another reading is available.
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


# Every one of these is declined by the application extractors — a missing
# interval, an unnamed axis, or a shape with no solver — and must therefore be
# refused outright rather than picked up by a neighbouring extractor.
DECLINED = [
    # No interval, and no single region: the curves cross infinitely often.
    "area between y=sin(x) and y=cos(x)",
    "area between y=sin(x) and y=0",
    "find the area between the curves y=x and y=2x",
    # Disks about x and shells about y are different formulas, so an unnamed
    # axis is not assumed.
    "volume of revolution of y=x from 0 to 1",
    # An area under a curve with no interval to integrate over.
    "area under y=x^2",
    # Shapes with no solver at all.
    "volume of the region bounded by y=x and y=0",
    "area bounded by y=x^2 and the x-axis",
]


@pytest.mark.parametrize("text", DECLINED)
def test_a_declined_region_question_is_refused_not_reinterpreted(text: str) -> None:
    assert _verified_answer(text) is None


def test_the_intersection_points_never_come_back(text: str = "area between y=x and y=x^2") -> None:
    """The original defect, pinned by value.

    `x = 0, y = 0; x = 1, y = 1` is a correct answer to "where do these curves
    meet". It was returned for "what is the area between them". With no
    interval stated, the area now runs between those meeting points.
    """
    assert _verified_answer(text) != "x = 0, y = 0; x = 1, y = 1"
    assert _verified_answer(text) == "\\frac{1}{6}"


def test_the_same_question_with_bounds_is_answered_not_refused() -> None:
    """The guard lets through what the application extractors claim.

    If this ever returns None again, the guard has gone back to running before
    the extractors instead of after them.
    """
    assert _verified_answer("area between y=x and y=x^2 from 0 to 1") == "\\frac{1}{6}"


# ---------------------------------------------------------------------------
# The guard is narrow enough not to reach its neighbours.
# ---------------------------------------------------------------------------

UNTOUCHED = [
    # A genuine simultaneous system, on the very curves the area question uses.
    ("solve y = x and y = x^2", "x = 0, y = 0; x = 1, y = 1"),
    ("solve 2x + y = 5 and x - y = 1", "x = 2, y = 1"),
    ("what is the area of a rectangle 3 by 4", "12"),
    ("what is the area of a circle with radius 5", "78.54"),
    ("integrate x^2 from 0 to 1", "\\frac{1}{3}"),
]


@pytest.mark.parametrize("text,answer", UNTOUCHED, ids=[row[0][:40] for row in UNTOUCHED])
def test_neighbouring_kinds_still_answer(text: str, answer: str) -> None:
    assert _verified_answer(text) == answer


def test_a_cylinder_volume_is_geometry_not_a_region() -> None:
    """ "volume" alone must not trip the guard — it needs a region word."""
    assert _verified_answer("what is the volume of a cylinder radius 2 height 5") is not None
