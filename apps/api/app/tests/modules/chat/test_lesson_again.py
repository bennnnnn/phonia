"""Asking for the lesson just taught gets a pointer to it, never the lesson again."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.chat.lesson_again import (
    asked_lesson,
    keep_to_lesson_again_pass,
    lesson_again,
    lesson_again_hint,
    pointer,
)

_QUIZ = (
    '```quiz\n{"label": "Exercise 1", "question": "What does it mean?", "options": ["a", "b"], '
    '"answer": 1, "explanation": "b."}\n```'
)
_LESSON_1 = f'### Lesson 1: "Break a leg"\n\nIt means good luck.\n\n{_QUIZ}'
_LESSON_2 = f'### Lesson 2: "Hit the sack"\n\nIt means go to bed.\n\n{_QUIZ}'


def _said(role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content)


_AFTER_LESSON_1 = [_said("user", "Teach me American sayings"), _said("assistant", _LESSON_1)]


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("Very interesting. Lets start with 1", 1),
        ("Let's start with 1", 1),
        ("Let\u2019s start with 1", 1),  # an iPhone's apostrophe
        ("That\u2019s interesting. Let\u2019s start with 1", 1),
        ("ok let's begin with lesson 1", 1),
        ("let's start with the first one", 1),
        ("Shall we start with lesson 1?", 1),
        ("start with lesson 1", 1),
        ("go back to lesson 2", 2),
        ("show me lesson 3 please", 3),
        ("lets start with number 2", 2),
    ],
)
def test_asking_to_start_or_go_to_a_lesson_is_read(text: str, number: int) -> None:
    assert asked_lesson(text) == number


@pytest.mark.parametrize(
    "text",
    [
        "1",  # an answer to the quiz
        "b",
        "next",
        "Lesson 1 was fun",
        "start with 1 cup of flour and 2 eggs",
        "I want to start a business with 1 friend",
        "let's start with 1 then do 2 and 3",
        "what's lesson 2 about?",
        "start the timer",
        # Answers to a quiz on where counting starts.
        "start at 1",
        "start with 1",
        "begin with one",
        "The answer is B. Let's start with 1",
        "I think it's 1. lets start with 1",
        # Confusion, which the lesson re-explains.
        "Can we start from the beginning?",
    ],
)
def test_other_lines_are_not_this_ask(text: str) -> None:
    assert asked_lesson(text) is None


def test_only_the_lesson_just_taught_counts() -> None:
    assert lesson_again("Lets start with 1", _AFTER_LESSON_1) == 1
    assert lesson_again("go to lesson 2", _AFTER_LESSON_1) is None
    assert lesson_again("Lets start with 1", [_said("assistant", "Here are five sayings.")]) is None
    assert lesson_again("Lets start with 1", None) is None


def test_the_hint_asks_for_a_pointer_only() -> None:
    hint = lesson_again_hint(1)
    assert "Lesson 1" in hint and "Lesson 2" in hint
    assert "no lesson" in hint and "no quiz" in hint


def _state(
    reply: str, message: str, recent: list[SimpleNamespace], regenerating: bool = False
) -> SimpleNamespace:
    ctx = SimpleNamespace(
        user_message_content=message,
        recent_messages=recent,
        instant_reply=None,
        regenerate_backup=object() if regenerating else None,
    )
    return SimpleNamespace(text=reply, ctx=ctx, server_text=False)


@pytest.mark.parametrize(
    "reply",
    [
        f"Starting from the beginning, here's Lesson 1 again.\n\n{_LESSON_1}",
        f"Correct! 🎉 That's right.\n\n{_LESSON_2}",
        f"Let's try another one.\n\n{_QUIZ}",
    ],
)
def test_a_reply_that_teaches_again_becomes_the_pointer(reply: str) -> None:
    state = _state(reply, "Very interesting. Lets start with 1", _AFTER_LESSON_1)

    assert keep_to_lesson_again_pass(state) == pointer(1)  # type: ignore[arg-type]


def test_a_pointer_reply_and_other_turns_stay() -> None:
    short = "You're on Lesson 1 already: try the practice question above, or say next."
    assert keep_to_lesson_again_pass(_state(short, "Lets start with 1", _AFTER_LESSON_1)) == short  # type: ignore[arg-type]
    # "next" after a lesson is the next lesson, as before.
    assert keep_to_lesson_again_pass(_state(_LESSON_2, "next", _AFTER_LESSON_1)) == _LESSON_2  # type: ignore[arg-type]


def test_a_regenerated_lesson_stays() -> None:
    # On regenerate the reply being redone is still the last one in the window.
    state = _state(_LESSON_1, "Let's start with 1", _AFTER_LESSON_1, regenerating=True)

    assert keep_to_lesson_again_pass(state) == _LESSON_1  # type: ignore[arg-type]


def test_a_teach_me_line_or_a_day_later_is_not_this_ask() -> None:
    assert lesson_again("teach me lesson 1", _AFTER_LESSON_1) is None
    old = [
        _said("user", "Teach me American sayings"),
        SimpleNamespace(
            role="assistant", content=_LESSON_1, created_at=datetime(2026, 1, 1, tzinfo=UTC)
        ),
    ]
    assert lesson_again("Let's start with 1", old) is None
