"""Literal unit conversions retain units and reject extra request fragments."""

from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.direct_units import unit_direct_request
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,answer",
    [
        ("Convert 2 hours to minutes", r"120\ \mathrm{minutes}"),
        ("Convert 8 m to cm", r"800\ \mathrm{cm}"),
        ("Convert 1 kg to g", r"1000\ \mathrm{g}"),
        ("Convert 0 C to F", r"32\ \mathrm{°F}"),
        ("Convert -40 C to F", r"-40\ \mathrm{°F}"),
        ("Please convert .5 m to cm.", r"50\ \mathrm{cm}"),
        ("Convert 1 m to cm please", r"100\ \mathrm{cm}"),
    ],
)
async def test_closed_conversion_returns_one_verified_quantity(query: str, answer: str):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_answer == answer
    assert unit_direct_request(query) is True
    assert maybe_direct_math_reply(verified, query) == f"```answer\n{answer}\n```\n"


@pytest.mark.parametrize(
    "query",
    [
        "Explain how to convert 2 hours to minutes",
        "Convert 2 hours to minutes with steps",
        "Convert 2 hours to minutes, hint only",
        "Convert 2 hours to minutes and explain why",
        "Convert 2 hours to minutes and 1 kg to g",
        "Convert 2 hours to minutes then convert 1 kg to g",
        "Convert 2 hours to minutes and 2+2",
        "Convert 2 and 3 hours to minutes",
        "Convert 2 hours to minutes rounded to nearest 10",
        "First find 2+2 then convert 2 hours to minutes",
        "Convert - .5 m to cm",
        "Convert 1e2 m to cm",
        "Convert 1/2 m to cm",
        "Convert 2.5.3 hours to minutes",
        "Convert (2) hours to minutes",
        "Convert 2 hours to minutes!",
        "Convert 2 hours to minutes..",
        "Convert 2 hours to minutes please please",
        "Convert 2 hours to minutes; tell a joke",
    ],
)
def test_extra_or_malformed_conversion_keeps_model_path(query: str):
    verified = VerifiedMathBlock(
        text="verified",
        canonical_answer="120",
        canonical_fence={"type": "answer", "content": "120"},
    )
    assert unit_direct_request(query) is False
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.asyncio
async def test_conversion_still_requires_verified_answer_and_keeps_camera_path():
    query = "Convert 2 hours to minutes"
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    assert maybe_direct_math_reply(verified, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(verified, allow_direct=False), query) is None
    assert maybe_direct_math_reply(None, query) is None
    assert (
        maybe_direct_math_reply(
            replace(verified, canonical_fences=[{"type": "answer", "content": "another"}]), query
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["Convert 2 hours to kg", "Convert 1 parsecwrong to m"])
async def test_unsupported_conversion_has_no_direct_reply(query: str):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None
    assert maybe_direct_math_reply(verified, query) is None
