"""A checklist request gets the task-list layout; a checklist mentioned does not."""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants import CHECKLIST_FORMAT_HINT, HOWTO_FORMAT_HINT
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.turn_reading.checklist import is_checklist_request


@pytest.mark.parametrize(
    "text",
    [
        "Give me a packing checklist for a 3-day hiking trip, grouped by category",
        "Make me a checklist for moving house",
        "I need a wedding planning checklist",
        "checklist for a job interview",
        "Can you put this in a checklist?",
        "Turn that into a checklist",
        "packing checklist",
        "Moving house checklist?",
        "Write a pre-flight checklist",
        "Checklist before leaving for vacation",
        "a checklist of things to pack",
        "make a to-do list for my weekend",
        "write a task list for launching the website",
        "can you give that to me as a to-do list",
        "a step-by-step moving checklist",
    ],
)
def test_checklist_request_is_read(text: str) -> None:
    assert is_checklist_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "What is a checklist?",
        "what's a to-do list app you'd recommend",
        "Thanks for the checklist!",
        "Love this checklist",
        "Is the checklist ready?",
        "how do I make a checklist in Notion",
        "how do I add a task list in Google Docs",
        "make a to-do list in the Reminders app",
        "Write a checklist component in React",
        "my checklist app crashes on start",
        "share your thoughts on my checklist: passport, charger, tickets",
        "make sure everything on the checklist is done",
        "make sure the checklist covers fire exits",
        "send me my to-do list",
        "I need to update my checklist",
        "Did you check list prices on Amazon?",
        "How do I check list length in python?",
        "The Checklist Manifesto is a great book",
        "checklisted items were reviewed",
        "Give me 5 tips to sleep better",
        "",
    ],
)
def test_checklist_lookalike_is_not_read(text: str) -> None:
    assert not is_checklist_request(text)


def _layout(query: str) -> list[str]:
    return _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
    )


def test_checklist_request_gets_task_list_layout() -> None:
    hints = _layout("Give me a packing checklist for a 3-day hiking trip, grouped by category")
    assert CHECKLIST_FORMAT_HINT in hints


def test_checklist_wins_over_howto() -> None:
    hints = _layout("make a step by step checklist for moving house")
    assert CHECKLIST_FORMAT_HINT in hints
    assert HOWTO_FORMAT_HINT not in hints


def test_mentioned_checklist_gets_no_task_list_layout() -> None:
    assert CHECKLIST_FORMAT_HINT not in _layout("how do I make a checklist in Notion")
