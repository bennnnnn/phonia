"""One claim grammar: every subject hears "I calculated …, is that ok?" as a claim.

Physics read the wide lead-ins and checks; maths knew "I got … is that right" only;
chemistry read none and declined the question (code-health audit DUP-08).
"""

from __future__ import annotations

import pytest

from app.modules.chemistry.context import _solve_locally
from app.modules.chemistry.direct import maybe_direct_chemistry_reply
from app.modules.chemistry.reading import chemistry_text_for_solve
from app.modules.math.followup import _claimed_values
from app.modules.math.tools.work_request import _ANSWER_CLAIM
from app.modules.physics.claims import read_claims

_LEADS = ["I got", "I calculated", "I worked out", "My answer is", "My teacher says"]
_CHECKS = ["is that right?", "is that ok?", "am I right?", "did I get it right?"]


@pytest.mark.parametrize("lead", _LEADS)
@pytest.mark.parametrize("check", _CHECKS)
def test_physics_hears_the_claim(lead: str, check: str) -> None:
    text = f"A 2 kg ball is dropped from 20 m. {lead} 19.8 m/s for its impact speed, {check}"
    assert [claim.value for claim in read_claims(text)] == [19.8]


@pytest.mark.parametrize("lead", _LEADS)
@pytest.mark.parametrize("check", _CHECKS)
def test_maths_hears_the_claim(lead: str, check: str) -> None:
    assert _claimed_values(f"{lead} x = 6, {check}") == ("x", ["6"])
    assert _ANSWER_CLAIM.search(f"{lead} x = 4 for 3x - 2 = 10") is not None


@pytest.mark.parametrize("lead", _LEADS)
@pytest.mark.parametrize("check", _CHECKS)
def test_chemistry_solves_the_question_and_leaves_the_verdict_to_the_model(
    lead: str, check: str
) -> None:
    text = f"How many grams are in 0.5 mol of NaCl? {lead} 29.2 g, {check}"
    _intent, solved, _context = _solve_locally(chemistry_text_for_solve(text))
    assert solved is not None
    assert maybe_direct_chemistry_reply(solved, has_image_attachment=False, user_text=text) is None


@pytest.mark.parametrize(
    "text",
    [
        "I have a 2 kg ball moving at 3 m/s. What is its momentum?",
        "I got a dog. A 2 kg ball moves at 3 m/s. What is its momentum?",
        "My teacher says hi. A 2 kg ball moves at 3 m/s. What is its momentum?",
    ],
)
def test_a_given_is_not_a_claim(text: str) -> None:
    assert read_claims(text) == []


def test_a_lab_reading_stays_a_given_for_chemistry() -> None:
    text = "I found 2.5 g of a white solid. What is its molar mass if it is 0.05 mol?"
    assert chemistry_text_for_solve(text) == text
