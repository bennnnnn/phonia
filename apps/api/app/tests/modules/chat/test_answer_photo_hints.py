"""Answers about something worth seeing open with a ```photo request for a real photo."""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants import ANSWER_PHOTO_HINT, WHERE_IS_PHOTO_HINT
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.chat.prompt_window import strip_prompt_owned_fences
from app.modules.turn_reading.visuals import where_is_place


@pytest.mark.parametrize(
    "text, place",
    [
        ("where is kenya", "kenya"),
        ("Where's Kenya?", "Kenya"),
        ("where’s kenya", "kenya"),
        ("wheres kenya", "kenya"),
        ("where is the eiffel tower", "the eiffel tower"),
        ("where is kenya located", "kenya"),
        ("where is mount kilimanjaro on the map", "mount kilimanjaro"),
        ("where exactly is Lesotho?", "Lesotho"),
        ("what country is timbuktu in", "timbuktu"),
        ("what continent is egypt in", "egypt"),
        ("show me where nepal is", "nepal"),
        ("can you tell me where Bhutan is", "Bhutan"),
        ("do you know where Addis Ababa is?", "Addis Ababa"),
        ("where in the world is Tuvalu", "Tuvalu"),
        ("where are the andes", "the andes"),
        ("where is somalia", "somalia"),
        ("where is the natural history museum", "the natural history museum"),
        ("where is the international date line", "the international date line"),
    ],
)
def test_where_is_place_finds_the_place(text: str, place: str) -> None:
    assert where_is_place(text) == place


@pytest.mark.parametrize(
    "text",
    [
        "where is my phone",
        "where are my keys",
        "where am I",
        "where are you",
        "where is it",
        "where is everyone",
        "where is everything",
        "where is someone when you need them",
        "where is home",
        "where is the error in my code",
        "where is the bug in this function",
        "where is the settings menu",
        "where is my order",
        "where is the nearest pharmacy",
        "where is the closest coffee shop",
        "where is the bathroom",
        "where was jesus born",
        "where do i start",
        "where can i buy a laptop",
        "where is the line between free speech and hate speech in law",
        "tell me about kenya",
    ],
)
def test_where_is_place_skips_things_not_on_a_map(text: str) -> None:
    assert where_is_place(text) is None


def _hints(text: str, *, photos: bool = True) -> list[str]:
    return _style_format_hints(
        query_text=text,
        is_day_plan=False,
        minimal_personal_context=False,
        image_search_enabled=photos,
    )


def test_where_is_question_asks_for_a_location_map() -> None:
    parts = _hints("where is kenya")
    assert ANSWER_PHOTO_HINT in parts
    assert WHERE_IS_PHOTO_HINT in parts
    assert "<place> location map" in WHERE_IS_PHOTO_HINT


def test_a_thing_worth_seeing_may_get_a_photo_but_only_where_is_asks_for_a_map() -> None:
    parts = _hints("what is a capybara")
    assert ANSWER_PHOTO_HINT in parts
    assert WHERE_IS_PHOTO_HINT not in parts


@pytest.mark.parametrize(
    "text",
    [
        "what is a capybara",
        "tell me about Lalibela",
        "who is Haile Gebrselassie",
        "tell me about Java island",
        "what does a ball python eat",
    ],
)
def test_photo_hint_stays_for_things_worth_seeing(text: str) -> None:
    assert ANSWER_PHOTO_HINT in _hints(text)


@pytest.mark.parametrize(
    "text",
    [
        # Code, said in words or pasted.
        "what is recursion",
        "write a python function to reverse a string",
        "Why does this code fail, and how would you fix it? numbers = [1, 2, 3] print(numbers[3])",
        # A subject problem.
        "solve 2x + 5 = 17",
        "a ball is dropped from 20 m. how long until it hits the ground?",
        "balance H2 + O2 -> H2O",
        # A lesson.
        "teach me american history",
        "help me understand two sum",
        "give me a 30 day plan to learn javascript",
        # A standing preference.
        "When teaching me, explain one concept at a time, use practical examples, and ask "
        "me to solve a short exercise before moving on.",
        # A draft, a requested chart, a pasted fragment.
        "write an email to my landlord about a broken heater",
        "make a bar chart of rainfall: Jan 5, Feb 3, Mar 7",
        "Is this sentence correct: me and him goes to the market",
        # Small talk that asks for nothing, and turns about the last reply itself.
        "good morning!",
        "hello there",
        "how are you?",
        "continue",
        "keep going",
        "fix that",
    ],
)
def test_photo_hint_stays_off_turns_that_are_not_about_one_thing(text: str) -> None:
    assert ANSWER_PHOTO_HINT not in _hints(text)


def test_photo_hint_stays_off_a_lesson_in_progress() -> None:
    parts = _style_format_hints(
        query_text="next",
        is_day_plan=False,
        minimal_personal_context=False,
        image_search_enabled=True,
        lesson=1,
    )
    assert ANSWER_PHOTO_HINT not in parts


def test_no_photo_hints_when_photo_lookup_is_off() -> None:
    parts = _hints("where is kenya", photos=False)
    assert ANSWER_PHOTO_HINT not in parts
    assert WHERE_IS_PHOTO_HINT not in parts


def test_photo_hint_keeps_abstract_topics_and_lessons_out() -> None:
    for word in ("abstract ideas", "code", "math", "lessons", "small talk"):
        assert word in ANSWER_PHOTO_HINT


def test_photo_fence_is_dropped_from_history_so_it_is_not_copied() -> None:
    reply = "```photo\nKenya location map\n```\n\nKenya is in East Africa."
    assert strip_prompt_owned_fences(reply).strip() == "Kenya is in East Africa."
