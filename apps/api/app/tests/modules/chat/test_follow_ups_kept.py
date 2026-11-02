"""Good follow-ups the filter dropped, and requests that got none (2026-10-29 probe).

Under "How do I change a flat tire?" the model wrote "How do I jack up the car?" and
"Do I need to torque the nuts?"; under "how tall is mount everest" it wrote "why does
everest grow taller". All were dropped, and with fewer than three kept, none showed.
"pros and cons of working remotely" and "Make me a weekly workout plan" never asked.
"""

from __future__ import annotations

import pytest

from app.modules.chat.related_questions import (
    accepted_questions,
    general_question,
    topic_anchors,
)

_TIRE = (
    "Here's how to change a flat safely, in order.\n\n"
    + "1. **Park and secure** — pull fully off the road onto flat ground, set the parking "
    "brake, and turn on your hazard lights. "
    * 3
    + "\n4. **Raise the car** — set the jack under the reinforced jack point nearest the flat.\n"
    "8. **Torque on the ground** — with the full weight on the tire, tighten each nut firmly "
    "in the star pattern again. If you have a torque wrench, use the figure in the manual."
)


def test_a_reply_word_past_its_opening_or_of_four_letters_keeps_a_follow_up() -> None:
    question = "How do I change a flat tire?"
    anchors = topic_anchors(question, _TIRE)
    kept = accepted_questions(
        question,
        [
            "How do I jack up the car?",
            "Do I need to torque the nuts?",
            "What is the capital of Peru?",
        ],
        anchors=anchors,
    )
    assert kept == ["How do I jack up the car?", "Do I need to torque the nuts?"]


@pytest.mark.parametrize(
    ("candidate", "kept"),
    [
        ("why does everest grow taller", "why does everest grow taller?"),
        ("How tall is Everest in miles.", "How tall is Everest in miles?"),
        # Not a question without its mark: a statement stays out.
        ("Everest grows a few millimetres a year", None),
    ],
)
def test_a_question_without_its_mark_is_kept_as_a_question(
    candidate: str, kept: str | None
) -> None:
    question = "how tall is mount everest"
    reply = "Mount Everest is 8,848.86 m tall, and it grows a few millimetres a year."
    result = accepted_questions(question, [candidate], anchors=topic_anchors(question, reply))
    assert result == ([kept] if kept else [])


_LONG_ANSWER = "A considered answer with several parts. " * 12


@pytest.mark.parametrize(
    ("request_text", "asks"),
    [
        ("pros and cons of working remotely", True),
        ("Make me a weekly workout plan, I can go 4 days a week", True),
        ("Plan a 3 day trip to Rome for me", True),
        ("Create a monthly budget for 4000 a month", True),
        # A draft is the user's to send: no follow-ups under it.
        ("Write a short email to my landlord about a leaking sink", False),
        ("make me a reminder to call mom at 5", False),
    ],
)
def test_a_request_to_know_gets_follow_ups(request_text: str, asks: bool) -> None:
    assert general_question(request_text, _LONG_ANSWER) is asks
