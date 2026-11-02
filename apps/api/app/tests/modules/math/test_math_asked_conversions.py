"""A conversion asked any way people ask it is verified, in the units people write."""

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
    ("text", "answer"),
    [
        # Live: these went to the model, which drew a chart the phone could not show.
        ("whats 72 fahrenheit in celsius", r"22.22\ \mathrm{°C}"),
        ("72 fahrenheit to celsius", r"22.22\ \mathrm{°C}"),
        ("what is 72°F in °C", r"22.22\ \mathrm{°C}"),
        # "convert" was read, but showed 22.22222222.
        ("convert 72 F to C", r"22.22\ \mathrm{°C}"),
        ("how much is 5 km in miles", r"3.107\ \mathrm{miles}"),
        # An exact factor stays exact; -40 is where the scales meet.
        ("1 mile in km", r"1.609344\ \mathrm{km}"),
        ("-40 c to f", r"-40\ \mathrm{°F}"),
        ("300 kelvin in celsius", r"26.85\ \mathrm{°C}"),
    ],
)
async def test_an_asked_conversion_is_verified_and_answered(text: str, answer: str) -> None:
    canonical, reply = await _verified(text)
    assert canonical == answer
    assert reply == f"```answer\n{answer}\n```\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "72 degrees in here",
        "3 apples in a box",
        "I'm 6 feet in height",
        "it's 5 to 7 in the morning",
    ],
)
async def test_a_number_beside_words_is_not_a_conversion(text: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Live, and its cousins: chat before the question kept it from the solver.
        ("lol got the second one wrong. random but whats 72 fahrenheit in celsius", r"22.22\ \mathrm{°C}"),
        ("ok cool. what is 2+2", "4"),
        ("random question but what is 2+2", "4"),
        # A given before the question is not chat: it is still read.
        ("x = 3. what is 2x + 1?", "7"),
    ],
)  # fmt: skip
async def test_a_question_after_chat_is_verified(text: str, answer: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        # A number before the question may be a given: nothing is dropped.
        "I had 5 apples. what is 2+2",
        "lol that was fun. tell me a joke",
        "ok thanks",
    ],
)
async def test_chat_with_no_closed_question_after_it_is_not_read(text: str) -> None:
    canonical, _reply = await _verified(text)
    assert canonical is None
