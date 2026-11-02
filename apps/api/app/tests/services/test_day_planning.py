"""Day-planning snapshot: detection and answer copy."""

import pytest

from app.modules.chat.prompt_constants import DAY_PLANNING_ANSWER_HINT
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.todos.prompt_context import should_inject_todos_prompt
from app.services.day_planning import (
    is_day_planning_question,
    is_day_reflection_question,
)

# Day-planning phrases a person can type, and whether each is end-of-day reflection.
_HOME_STARTERS: list[tuple[str, bool, bool]] = [
    ("Help me plan my day based on what you know about me.", True, False),
    ("What should I focus on today?", True, False),
    ("What am I trying to get done today?", True, False),
    ("What's still open for me to finish today?", True, False),
    ("How did my day go? Help me reflect and wrap up loose ends.", True, True),
    ("What's still open for me to finish tonight?", True, False),
    ("I'm still up — what should I tackle or wind down?", True, True),
    ("I have a quick thought I want to talk through.", False, False),
    ("I want to talk something through — ask me a good opening question.", False, False),
    ("What can you help me with? Give a few concrete examples.", False, False),
]


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "How's my day looking so far — anything you think I should prioritize?",
            True,
        ),
        ("Help me plan my day based on what you know about me.", True),
        ("What should I focus on today?", True),
        ("How did my day go? Help me reflect and wrap up loose ends.", True),
        ("What's still open for me to finish tonight?", True),
        ("What's on my calendar today?", False),
        ("check my email", False),
        ("Tell me a joke", False),
    ],
)
def test_is_day_planning_question(text, expected):
    assert is_day_planning_question(text) is expected


def test_reflection_is_still_day_planning():
    text = "How did my day go? Help me reflect and wrap up loose ends."
    assert is_day_planning_question(text)
    assert is_day_reflection_question(text)


def test_morning_planning_is_not_reflection():
    text = "How's my day looking so far — anything you think I should prioritize?"
    assert is_day_planning_question(text)
    assert not is_day_reflection_question(text)


@pytest.mark.parametrize("prompt,is_planning,is_reflection", _HOME_STARTERS)
def test_home_starter_day_planning_flags(prompt, is_planning, is_reflection):
    assert is_day_planning_question(prompt) is is_planning
    assert is_day_reflection_question(prompt) is is_reflection
    assert should_inject_todos_prompt([], query_text=prompt) is is_planning


def test_day_planning_answer_hint_uses_plain_markdown_not_callout_cards():
    assert "ordinary markdown prose" in DAY_PLANNING_ANSWER_HINT
    assert "Never a card" in DAY_PLANNING_ANSWER_HINT
    assert "A `>` line renders as a quote card." not in DAY_PLANNING_ANSWER_HINT
    assert "ordinary indented prose" in DAY_PLANNING_ANSWER_HINT
    assert "quote card only when the last line is `— Name`" in DAY_PLANNING_ANSWER_HINT
    assert "offer a setup walkthrough" in DAY_PLANNING_ANSWER_HINT
    assert "Reminders" in DAY_PLANNING_ANSWER_HINT
    assert "Today's learning progress" not in DAY_PLANNING_ANSWER_HINT
    assert "Surface this as `> Warning:" not in DAY_PLANNING_ANSWER_HINT
    assert "Surface this as `> Tip:" not in DAY_PLANNING_ANSWER_HINT


def test_day_planning_answer_hint_says_recall_has_no_calendar_or_inbox():
    assert (
        "does not connect to the user's calendar or email" in DAY_PLANNING_ANSWER_HINT
    )  # safety phrase
    assert "never invent meetings or mail" in DAY_PLANNING_ANSWER_HINT  # safety phrase
    assert "Settings →" not in DAY_PLANNING_ANSWER_HINT
    assert "Do not suggest connecting an account" in DAY_PLANNING_ANSWER_HINT  # safety phrase


def test_day_plan_style_hints_include_snapshot_and_override_format_contract_callouts():
    parts = _style_format_hints(
        query_text="What's still open for me to finish tonight?",
        is_day_plan=True,
        minimal_personal_context=False,
    )
    assert DAY_PLANNING_ANSWER_HINT in parts
    joined = "\n".join(parts)
    assert "a blockquote starting with Tip:" not in joined
    assert "A `>` quote card is only a cited quotation whose last line is " in joined
    assert "> Warning:" in joined
    assert DAY_PLANNING_ANSWER_HINT in joined
    assert "quote card" in joined


def test_reflection_style_hints_keep_reminders_and_loose_ends():
    parts = _style_format_hints(
        query_text="How did my day go? Help me reflect and wrap up loose ends.",
        is_day_plan=True,
        minimal_personal_context=False,
    )
    joined = "\n".join(parts)
    assert DAY_PLANNING_ANSWER_HINT in parts
    assert "end-of-day reflection" in joined
    assert "keep reminders, lists, and loose ends" in joined
