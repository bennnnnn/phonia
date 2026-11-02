"""Whether a turn needs live results: the search gate production runs.

An LLM classifier used to sit behind this gate; production kept it off (it added a
model call before the first token), so these are the decisions users got.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.web_search import should_web_search

_ON = Settings(web_search_enabled=True)


@pytest.mark.parametrize(
    ("text", "prior", "expected"),
    [
        # Chit-chat never searches.
        ("how's your day", None, False),
        ("tell me a joke", None, False),
        ("that's funny", None, False),
        ("what do you think", None, False),
        ("how?", None, False),
        # Officeholders and the weather change after training: an instant yes.
        ("who is the ceo of openai", None, True),
        ("what's the weather", None, True),
        ("search the web for AI news", None, True),
        ("What is the latest price of Bitcoin?", None, True),
        # A reminder or a memory question after a search is not a search.
        (
            "Remind me to water the plant tomorrow at 8:00 AM.",
            ["What is the current price of Bitcoin in US dollars?"],
            False,
        ),
        ("What reminders do I have?", ["What is the current price of Bitcoin?"], False),
        (
            "What is my dog's name and what color is he?",
            [
                "What is the current price of Bitcoin in US dollars?",
                "Remember that my dog's name is Kofi and he is a brown terrier.",
            ],
            False,
        ),
        # Stable knowledge and the user's own life stay offline.
        ("Explain how recursion works in Python", None, False),
        ("I work at Uber but I want to change to Google", None, False),
        (
            "Where do I work right now, and which company am I considering for the future?",
            None,
            False,
        ),
    ],
)
def test_the_gate_decides_as_production_did(
    text: str, prior: list[str] | None, expected: bool
) -> None:
    assert should_web_search(text, _ON, prior_user_messages=prior) is expected


def test_search_off_never_searches() -> None:
    assert should_web_search("what's the weather", Settings(web_search_enabled=False)) is False
