"""A question in parts: each solve part of the turn's plan is solved on its own.

"A ball is dropped from 20 m. What is its speed after 1 s? How long does it take to reach
the ground?" is two questions about one problem (``turn_prep.intents``). Read whole, physics
verified neither; each part, with the setup it carries, verifies, and the reply lays them out
lettered (``services.subjects.dispatch.build_subject_augmentation``'s ``parts``).
"""

from __future__ import annotations

import re

from app.core.config import Settings
from app.services.subjects.dispatch import _in_parts, build_subject_augmentation

_SETTINGS = Settings.model_validate({})
_SETUP = "A ball is dropped from 20 m."
_PARTS = (
    f"{_SETUP} What is its speed after 1 s?",
    f"{_SETUP} How long does it take to reach the ground?",
)


def test_the_parts_are_lettered_under_their_own_questions() -> None:
    text = _in_parts(_PARTS, ["**Answer**\n\n9.81 m/s", "**Answer**\n\n2.02 s"])

    assert text.startswith("**(a) What is its speed after 1 s?**")
    assert "**(b) How long does it take to reach the ground?**" in text
    assert re.findall(r"\*\*Answer \(([ab])\)\*\*", text) == ["a", "b"]
    assert _SETUP not in text


async def test_every_part_of_a_question_in_parts_is_worked() -> None:
    whole = " ".join([_SETUP, "What is its speed after 1 s?", _PARTS[1].removeprefix(_SETUP)])

    found = await build_subject_augmentation(whole, _SETTINGS, parts=_PARTS, parts_answer_all=True)

    assert found.verified is not None and found.verified.subject == "physics"
    assert found.direct_text is not None
    assert "**Answer (a)**" in found.direct_text and "**Answer (b)**" in found.direct_text
    assert "9.81" in found.direct_text and "2.02" in found.direct_text


async def test_a_part_beside_another_request_keeps_its_card() -> None:
    whole = f"{_PARTS[0]} {_PARTS[1].removeprefix(_SETUP).strip()} What's the weather today?"

    found = await build_subject_augmentation(whole, _SETTINGS, parts=_PARTS, parts_answer_all=False)

    # The weather is the model's: no reply is written here, but a part's card stands.
    assert found.direct_text is None
    assert found.verified is not None and found.verified.subject == "physics"
