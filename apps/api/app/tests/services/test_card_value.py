"""An answer card holds the final answer; the calculation before it is working."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.answer_fence import verified_answer_body, verified_answer_fence
from app.services.card_value import final_answer_only, split_working

# The phone reads cards with the same rule (lib/answerNotation.ts).
_CASES: list[dict[str, Any]] = json.loads(
    (
        Path(__file__).resolve().parents[5] / "docs" / "fixtures" / "answer_card_cases.json"
    ).read_text()
)


@pytest.mark.parametrize("case", _CASES, ids=[case["name"] for case in _CASES])
def test_split_working_keeps_the_final_answer(case: dict[str, Any]) -> None:
    assert split_working(case["value"]) == (case["working"], case["answer"])
    assert final_answer_only(case["value"]) == case["answer"]


def test_a_verified_card_holds_the_final_answer_alone() -> None:
    assert verified_answer_fence("4 × 4 = 16") == "```answer\nverified: true\n16\n```"
    # Its header lines stay, and marking it again changes nothing.
    body = verified_answer_body("notation: chemistry\n2 × 0.5 = 1")
    assert body == "verified: true\nnotation: chemistry\n1"
    assert verified_answer_body(body) == body
