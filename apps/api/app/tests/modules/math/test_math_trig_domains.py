"""Unsupported trig domains must not receive a certified all-real answer."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.schemas import MathImageExtract, MathIntent
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.parametrize(
    "query",
    [
        "Solve sin(x)=1/2 on [0,2*pi]",
        "Solve sin(x)=1/2 for x in (0,pi)",
        "Solve sin(x)=1/2 between 0 and pi",
        "Solve sin(x)=1/2 from 0 to pi",
        "Solve sin(x)=1/2 from -pi/2 to pi/2",
        "Solve sin(x)=1/2 between -2*pi and 2*pi",
        "Solve sin(x)=2 over the complex numbers",
        "Solve cos(x)=2 in C",
        r"Solve sin(x)=2 for x \in \mathbb{C}",
        "Solve sin(x)=1/2 for positive real x",
        "Solve tan(x)=1 over the integers",
        "Solve sin(x)=1/2 in degrees",
    ],
)
@pytest.mark.asyncio
async def test_explicit_unsupported_domain_uses_model_without_wrong_certification(
    query: str,
) -> None:
    assert extract_math_intent(query) is None
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None
    assert maybe_direct_math_reply(verified, query) is None


def test_explicit_chained_radian_domain_is_verified_without_losing_bounds() -> None:
    query = "Solve sin(x)=1/2 for 0<=x<=2*pi"
    intent = extract_math_intent(query)
    assert isinstance(intent, MathIntent)
    assert intent.school_op == "bounded_radian_equation"


@pytest.mark.parametrize(
    "query",
    [
        "Solve sin(x)=1/2",
        "Solve sin(x)=1/2 over the real numbers",
        "Find all real solutions of sin(x)=1/2",
        "Solve sin(x)=1/2 from scratch",
        "Solve sin(x)=1/2 within a few steps",
    ],
)
@pytest.mark.asyncio
async def test_all_real_trig_requests_keep_complete_periodic_solution(query: str) -> None:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_answer is not None
    assert verified.canonical_answer.count(r"2 \pi k") == 2
    assert r"k \in \mathbb{Z}" in verified.canonical_answer


@pytest.mark.parametrize("caption", ["Solve for 0<=x<=2*pi", "Solve over the complex numbers"])
@pytest.mark.asyncio
async def test_camera_trig_equation_preserves_domain_requested_in_caption(caption: str) -> None:
    _, verified = await build_math_augmentation(
        caption,
        Settings(math_tools_enabled=True),
        has_image_attachment=True,
        image_math_extract=MathImageExtract(kind="equation", lhs="sin(x)", rhs="2"),
    )
    assert verified is None
