"""The one thing a turn asks about gets its own photo hint.

"What is a capybara", "tell me about Lalibela" and "who is Haile Gebrselassie" came
back without a photo: the general rule sat deep in the prompt and the small model
skipped it. "Where is kenya", with a hint of its own, always opened with one.
"""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants.answer_subject import subject_photo_hint
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.turn_reading.answer_subject import asked_about_subject


@pytest.mark.parametrize(
    "text, subject",
    [
        ("what is a capybara", "capybara"),
        ("What's an axolotl?", "axolotl"),
        ("what’s a quokka", "quokka"),
        ("tell me about Lalibela", "Lalibela"),
        ("can you tell me about the Eiffel Tower", "Eiffel Tower"),
        ("who is Haile Gebrselassie", "Haile Gebrselassie"),
        ("who was Albert Einstein?", "Albert Einstein"),
    ],
)
def test_asked_about_subject_reads_the_one_thing(text: str, subject: str) -> None:
    assert asked_about_subject(text) == subject


@pytest.mark.parametrize(
    "text",
    [
        "what is the capital of Kenya",
        "who is the president of Kenya",
        "what is a good name for my cat",
        "tell me about yourself",
        "who are you",
        "what is it",
        "what is 2+2",
        "who won the last world cup",
        "what are the benefits of drinking water and why do they matter so much",
        "",
    ],
)
def test_asked_about_subject_leaves_other_questions(text: str) -> None:
    assert asked_about_subject(text) is None


def test_subject_photo_hint_names_the_fence_and_the_no_photo_cases() -> None:
    hint = subject_photo_hint("capybara")
    assert '"capybara"' in hint
    assert "```photo\ncapybara\n```" in hint
    assert '"photosynthesis", "recursion", "inflation", "love"' in hint


def _hints(query: str) -> str:
    return "\n\n".join(
        _style_format_hints(
            query_text=query,
            is_day_plan=False,
            minimal_personal_context=False,
            image_search_enabled=True,
        )
    )


def test_the_subject_hint_follows_the_general_photo_rule() -> None:
    assert subject_photo_hint("capybara") in _hints("what is a capybara")


@pytest.mark.parametrize("query", ["what is recursion", "where is kenya", "hi"])
def test_no_subject_hint_for_code_a_place_ask_or_small_talk(query: str) -> None:
    assert "If that is something people would want to see" not in _hints(query)
