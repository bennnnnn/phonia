"""Before a percent: a question stem and at most one stated operation, or nothing.

Every probe of the review of PR #2172 (2026-10-31), through the real subject path
(build_subject_augmentation, no model call), with the card it must give or None for a
decline. "Is 15 less than 25% of 80?" and "halve 25% of 80" decline; "subtract 5 from 25% of 80" is 15.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.subjects.dispatch import build_subject_augmentation

PROBES: list[tuple[str, str | None]] = [
    ("subtract 5 from 25% of 80", "15"),
    ("subtract 25% of 80 from 5", None),
    ("subtract 25% of 80 from 100", None),
    ("5 less than 25% of 80", "15"),
    ("25% less than 80", None),
    ("what is 25% less than 80", None),
    ("increase 80 by 25% then subtract 5", None),
    ("what is 25% of 80 minus 5", "15"),
    ("subtract 5% from 80", None),
    ("what is 80 minus 5%", None),
    ("save 5 from my 25% discount on $80", None),
    ("Is 15 less than 25% of 80?", None),
    ("Is 5 more than 25% of 80?", None),
    ("is 30 more than 25% of 80", None),
    ("Which is larger, 15 or 5 less than 25% of 80?", None),
    ("deduct 5 from 25% of 80", None),
    ("remove 5 from 25% of 80", None),
    ("reduce 25% of 80 by 5", None),
    ("halve 25% of 80", None),
    ("square 25% of 80", None),
    ("what is the square root of 25% of 80", None),
    ("what is the square of 25% of 80", None),
    ("what is the reciprocal of 25% of 80", None),
    ("quadruple 25% of 80", None),
    ("what is 3 times 25% of 80", None),
    ("what is 25% of 80 subtracted from 100", None),
    ("what is 25% of 80 taken away from 100", None),
    ("what is 25% of 80 added to 10", None),
    ("what is 25% of 80 less 5", None),
    ("From 25% of 80, subtract 5", None),
    ("subtract 5 from 25% of 80 then multiply by 2", None),
    ("add 5 to 25% of 80 and double it", None),
    ("What is 5% more than 25% of 80?", None),
    ("What is 5 more than the 25% of 80?", "25"),
    ("subtract $5 from 25% of $80", "15"),
    ("take 5 from 25% of 80", "15"),
    ("In 5 more years, what is 25% of 80?", None),
    ("There are 5 more boys than girls. What is 25% of 80?", "20"),
    ("I have 5 more than my sister: what is 25% of 80?", "20"),
    ("add 5 to 25% of 80 and subtract 2", None),
    ("subtract 5 from 25 percent of 80", "15"),
    ("what is 5 less than 25 percent of 80", "15"),
    ("what is 0.5 less than 25% of 80", "19.5"),
    ("add 1,000 to 25% of 8,000", "3000"),
    ("subtract 5 from 25% of 80%", None),
    ("5 more than 25% of 80 is what number?", "25"),
    ("what number is 3 less than 50% of 30", "12"),
    ("subtract 10 from 20% of 50% of 400", "30"),
    ("what is 5 subtracted from 25% of 80", "15"),
    ("take away 5 from 25% of 80", "15"),
    ("subtracting 5 from 25% of 80 gives", "15"),
    ("what do you get when you add 5 to 25% of 80", "25"),
    ("What is 5 more than 25% of 80 minus 3?", None),
    ("what is 25% of 80 more than 5", None),
    ("subtract 5 from 25% off 80", None),
    ("add 5 to 25% off $80", None),
    ("subtract 5 from 80 increased by 25%", None),
    ("what is 10 less than 80 decreased by 25%", None),
    ("how much is 2 more than 10% of 50", "7"),
    ("x is 5 less than 25% of 80. find x", None),
    ("Is 25% of 80 more than 15?", None),
    ("If you subtract 5 from it, what is 25% of 80?", None),
    ("Is 30 more than 25% of 80", None),
    ("Is it true that 5 more than 25% of 80 is 25?", None),
    ("Is 5 less than 25% of 80 equal to 15?", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "answer"), PROBES, ids=[text[:60] for text, _ in PROBES])
async def test_a_percent_is_read_only_with_what_is_fully_read_before_it(
    thread_sympy_executor: None, text: str, answer: str | None
) -> None:
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    verified = (await build_subject_augmentation(text, settings)).verified
    assert getattr(verified, "canonical_answer", None) == answer
