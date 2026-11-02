"""A learner stuck on a topic gets the walkthrough lesson; a person or the last reply does not."""

from __future__ import annotations

import pytest

from app.modules.turn_reading.teaching import is_walkthrough_request


@pytest.mark.parametrize(
    "text",
    [
        "I don't understand recursion",
        "I don’t understand recursion",  # the iPhone keyboard's apostrophe
        "i dont understand recursion",
        "I still don't understand pointers in C",
        "I don't get recursion",
        "I don't understand the chain rule",
        "I'm confused about recursion",
        "I’m so confused by big O notation",
        "I'm lost with derivatives",
        "I can't wrap my head around recursion",
        "recursion makes no sense to me",
        "pointers confuse me",
        "the chain rule is so confusing",
    ],
)
def test_stuck_on_a_topic_gets_the_lesson(text: str) -> None:
    assert is_walkthrough_request(text)


@pytest.mark.parametrize(
    "text",
    [
        # A person, a feeling or a question word is not a topic.
        "I don't understand why she left",
        "I don't understand her",
        "I don't understand what you mean",
        "I don't get it",
        "life makes no sense",
        "I'm confused about my feelings",
        # Something in the last reply: a follow-up, not a new lesson.
        "I don't understand step 3",
        "I don't understand the second example",
        "your answer makes no sense",
        "I'm confused by your reply",
        "this makes no sense",
        # Not about understanding at all.
        "I'm lost in Addis",
        "I'm stuck on the highway",
        "I'm struggling with grief",
        "I don't understand how to install docker",
    ],
)
def test_not_a_topic_gets_no_lesson(text: str) -> None:
    assert not is_walkthrough_request(text)
