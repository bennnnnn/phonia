"""Golden NL → verified-answer corpus.

One row per real user-style prompt, run through the full pre-stream pipeline
(``build_math_augmentation`` with real SymPy). This is the engine's contract:
if a row regresses, a user-visible answer regressed. ``expected`` is a
substring of the canonical answer (exact strings probed from the solver).
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import prompt as math_prompt

GOLDEN: list[tuple[str, str]] = [
    ("what is 8 - 8 * 2", "-8"),
    ("solve 2x + 3 = 7", "x = 2"),
    ("solve x+y=10, x-y=2", "x = 6, y = 4"),
    ("derivative of x^3", "3 x^{2}"),
    ("integrate x^2", "\\frac{x^{3}}{3} + C"),
    ("integrate x from 0 to 3", "\\frac{9}{2}"),
    ("limit sin(x)/x as x -> 0", "1"),
    ("mean of 2, 4, 6, 8", "5"),
    ("gcd of 12 and 18", "6"),
    ("what is 5 factorial", "120"),
    ("determinant of [[1,2],[3,4]]", "-2"),
    ("20% of 150", "30"),
    ("convert 0 celsius to fahrenheit", "32"),
    ("solve x^2 = 9", "x = \\pm 3"),
    ("solve x^2 - 4 > 0", "x < -2"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("prompt", "expected"), GOLDEN)
async def test_golden_nl_to_verified_answer(prompt: str, expected: str) -> None:
    _note, verified = await math_prompt.build_math_augmentation(
        prompt, Settings(math_tools_enabled=True)
    )
    assert verified is not None, prompt
    assert verified.canonical_answer is not None, prompt
    assert expected in verified.canonical_answer, (
        f"{prompt!r}: expected {expected!r} in {verified.canonical_answer!r}"
    )
