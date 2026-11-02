"""A tip, a tax or a service charge on a bill is verified in the bill's money."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.subjects.dispatch import build_subject_augmentation, maybe_direct_subject_reply


async def _verified(text: str) -> tuple[str | None, str | None]:
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    verified = (await build_subject_augmentation(text, settings)).verified
    answer = getattr(verified, "canonical_answer", None) if verified is not None else None
    return answer, maybe_direct_subject_reply(verified, text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer", "total"),
    [
        # Live: the model wrote `$48 \times 0.15 = 7.20$` and lost the dollar sign.
        ("btw whats a 15% tip on 48 dollars", r"\$7.20", "$55.20"),
        ("15% tip on $48", r"\$7.20", "$55.20"),
        ("what's a 20% tip on a $65.50 bill", r"\$13.10", "$78.60"),
        ("8% tax on $25", r"\$2.00", "$27.00"),
        ("what's a 15% gratuity on $80", r"\$12.00", "$92.00"),
        ("tip of 18% on 120 euros", "€21.60", "€141.60"),
        ("VAT of 20% on £50", "£10.00", "£60.00"),
        # No money named: the number, in cents.
        ("15% tip on 48", "7.20", "55.20"),
    ],
)
async def test_a_charge_on_a_bill_is_verified_with_the_total(
    text: str, answer: str, total: str
) -> None:
    canonical, reply = await _verified(text)
    assert canonical == answer
    assert reply is not None
    assert reply.startswith(f"```answer\n{answer}\n```")
    assert f"the total is **{total}**" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "any tips for a 15 minute talk on 48 slides",
        "15% tip",
        "is a 15% tip enough in New York?",
        "tip 20% or 15% for bad service?",
        "how much tax do I pay on 50000 a year",
    ],
)
async def test_talk_about_tips_and_tax_is_not_a_charge(text: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical is None
