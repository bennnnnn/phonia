"""Quiz me, flashcards and true/false get one ```quiz card per question."""

from __future__ import annotations

import pytest

from app.modules.turn_reading.practice import is_practice_request


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Quiz me on the planets of the solar system", True),
        ("Make flashcards for 5 common Spanish verbs", True),
        ("flashcards for the French revolution", True),
        ("Give me 5 true/false questions about World War II", True),
        ("Write 10 multiple choice questions on photosynthesis", True),
        ("give me a quick quiz on capitals", True),
        ("test me on python basics", True),
        ("can you do a pop quiz on the periodic table", True),
        ("Make Spanish verb flashcards", True),
        ("give me a 10-question geography quiz", True),
        # Look-alikes: a quiz mentioned, asked how, an answer key, or an app.
        ("I have a quiz tomorrow on cell biology, can you explain mitosis?", False),
        ("how do I make flashcards in Anki?", False),
        ("my teacher gave us a true or false test and I got 6/10, is that bad?", False),
        ("write 10 multiple choice questions on photosynthesis with the answers", False),
        ("make a quiz with an answer key for my class", False),
        ("is it true or false that goldfish have a 3-second memory?", False),
        ("test my code: def add(a, b): return a - b", False),
        ("what is a good app for making flashcards?", False),
        ("create a quiz app in React", False),
        ("make a test plan for the login page", False),
        ("give me a checklist to study for my quiz", False),
        ("give me tips for my quiz tomorrow", False),
        ("make sure I pass my quiz", False),
        ("help me prepare for my true or false test", False),
        ("do my multiple choice homework", False),
        ("write an essay about my pop quiz disaster", False),
        ("", False),
    ],
)
def test_is_practice_request(text: str, expected: bool) -> None:
    assert is_practice_request(text) is expected
