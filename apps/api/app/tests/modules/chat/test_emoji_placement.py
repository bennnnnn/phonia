"""Emoji follow the user's setting, whatever the model wrote (Settings → Emoji)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.chat.emoji_placement import join_split_emoji, place_emoji, place_reply_emoji
from app.modules.turn_reading.routing import EMOJI

# "What are the benefits of drinking water" at "A few", as the model wrote it.
_LIVE = (
    "Here are the main perks:\n\n"
    "*   **Temperature control** — water is the fuel for that system 🌡️\n"
    "*   **🧠 Brain power** — Even mild dehydration hurts focus\n"
    "*   **Kidney cleanup** — Water helps your kidneys filter waste 🚽 and flush it out.\n"
    "    - nested **Detail 🔬** point\n\n"
    "Want me to look up how much you should drink? 💧"
)


def test_a_few_moves_each_emoji_to_the_front_of_its_label() -> None:
    assert place_emoji(_LIVE, "some", user_wrote_emoji=False) == (
        "Here are the main perks:\n\n"
        "*   🌡️ **Temperature control** — water is the fuel for that system\n"
        "*   🧠 **Brain power** — Even mild dehydration hurts focus\n"
        "*   🚽 **Kidney cleanup** — Water helps your kidneys filter waste and flush it out.\n"
        "    - 🔬 nested **Detail** point\n\n"
        "Want me to look up how much you should drink?"
    )


def test_none_removes_every_emoji_and_keeps_the_layout() -> None:
    assert place_emoji(_LIVE, "off", user_wrote_emoji=False) == (
        "Here are the main perks:\n\n"
        "*   **Temperature control** — water is the fuel for that system\n"
        "*   **Brain power** — Even mild dehydration hurts focus\n"
        "*   **Kidney cleanup** — Water helps your kidneys filter waste and flush it out.\n"
        "    - nested **Detail** point\n\n"
        "Want me to look up how much you should drink?"
    )


def test_lots_keeps_them_and_none_mirrors_the_user() -> None:
    assert place_emoji(_LIVE, "more", user_wrote_emoji=False) == _LIVE
    assert place_emoji(_LIVE, "off", user_wrote_emoji=True) == _LIVE


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("🌊 Hydration matters.", "Hydration matters."),
        ("### Singapore 🇸🇬", "### 🇸🇬 Singapore"),
        ("**Low taxes 💰** — Singapore", "💰 **Low taxes** — Singapore"),
        ("> Note: drink up 💧", "> Note: drink up"),
        ("1. **Sleep** — rest well 😴.", "1. 😴 **Sleep** — rest well."),
        ("- 💧 **Water** — and more 🚰", "- 💧 **Water** — and more"),
    ],
)
def test_a_few_lines(line: str, kept: str) -> None:
    assert place_emoji(line, "some", user_wrote_emoji=False) == kept


@pytest.mark.parametrize(
    "text",
    [
        # Fences (the clarify card's options), inline code, table rows and lessons.
        '```clarify\n{"options": ["💰 Money", "🌿 Life"]}\n```',
        'Use `print("🐍")` to print it.',
        "| Country | Tax |\n|---|---|\n| UAE ✅ | 0% |",
        "### Lesson 1: Lists 🐍\n\nCorrect! 🎉 A list holds items.",
        "No emoji here.",
    ],
)
def test_what_a_few_leaves_alone(text: str) -> None:
    assert place_emoji(text, "some", user_wrote_emoji=False) == text


def _state(text: str, level: str | None, *, said: str = "hi", server: bool = False) -> Any:
    user = SimpleNamespace(emoji_use=level) if level else None
    ctx = SimpleNamespace(user=user, user_message_content=said)
    settings = SimpleNamespace(chemistry_enabled=True)
    return cast(Any, SimpleNamespace(text=text, ctx=ctx, server_text=server, settings=settings))


def test_the_pass_reads_the_users_setting_and_message() -> None:
    line = "🌊 Hydration matters."
    assert place_reply_emoji(_state(line, "some")) == "Hydration matters."
    assert place_reply_emoji(_state(line, "off", said="hey 👋")) == line
    # Server text, or no user to read a setting from, is left as it is.
    assert place_reply_emoji(_state(line, "off", server=True)) == line
    assert place_reply_emoji(_state(line, None)) == line


# A textbook's answers at "Lots" (2026-10-31): a whole message that is an exercise in a
# textbook's own form gets no emoji at any setting; everything else keeps the setting.
_EXERCISE = "Which of the following is a mixture?\nA. Water\nB. Salt\nC. Sugar\nD. Milk"
_BLANK = "The process by which plants make food is called ________."


@pytest.mark.parametrize(
    ("reply", "said", "kept"),
    [
        ("💧 **D. Milk** — a mixture of water and fats.", _EXERCISE,
         "**D. Milk** — a mixture of water and fats."),
        ("🌱 **Photosynthesis**", _BLANK, "**Photosynthesis**"),
        # The user wrote one: the reply may too.
        ("🍕 **Tip:** $16", "Calculate the tip on $80 at 20% 🍕", "🍕 **Tip:** $16"),
        ("💶 **About 92 EUR**", "Convert 100 USD to euros 💶", "💶 **About 92 EUR**"),
        # Everyday maths, a plan, a trip: not a textbook's form.
        ("🧮 **12**", "What's 15% of 80?", "🧮 **12**"),
        ("🚗 **About 4 hours**", "Estimate how long a road trip from LA to Vegas takes",
         "🚗 **About 4 hours**"),
        ("🌍 **Book early**", "any tips for my trip to Rome?", "🌍 **Book early**"),
        # A run of dots or underscores is punctuation, not a blank to fill.
        ("😅 **Fair enough**", "so......", "😅 **Fair enough**"),
        ("😂 **Got it**", "lol ok ___ whatever", "😂 **Got it**"),
        ("✈️ **Rome**", "Trip ideas.......... Paris or Rome?", "✈️ **Rome**"),
        # An exercise beside another request: the reply is not all homework.
        ("☀️ **Sunny**", _EXERCISE + "\n\nAlso, what's the weather in Paris today?",
         "☀️ **Sunny**"),
    ],
)  # fmt: skip
def test_only_a_whole_textbook_exercise_drops_emoji(reply: str, said: str, kept: str) -> None:
    assert place_reply_emoji(_state(reply, "more", said=said)) == kept


# Every case the phone's twin (features/chat/model/emojiPlacement.ts) reads too: the
# streaming draft is already the reply that will be saved.
_CASES = json.loads(
    (
        Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "emoji_placement_cases.json"
    ).read_text()
)


@pytest.mark.parametrize("case", _CASES, ids=[case["name"] for case in _CASES])
def test_the_shared_cases(case: dict[str, Any]) -> None:
    placed = place_emoji(case["text"], case["level"], user_wrote_emoji=case["user_wrote_emoji"])
    assert placed == case["expected"]


@pytest.mark.parametrize(
    ("written", "joined"),
    [
        # Live (2026-10-29): astronauts in a searched reply, written without the joiner.
        ("1. 👨🚀 **Reid Wiseman's new role**", "1. 👨‍🚀 **Reid Wiseman's new role**"),
        ("👩🍳 Method", "👩‍🍳 Method"),
        ("🧑🏽💻 code", "🧑🏽‍💻 code"),
        ("⚖️ 👩⚖️ judge", "⚖️ 👩‍⚖️ judge"),
    ],
)
def test_a_person_and_role_written_apart_are_one_emoji(written: str, joined: str) -> None:
    assert join_split_emoji(written) == joined


@pytest.mark.parametrize(
    "text",
    [
        "👩‍🚀 already joined",
        "👨 🚀 a space between them",
        "🚀 then 👨 alone",
        "👨🐶 a pair Unicode does not join",
        "no emoji at all",
    ],
)
def test_other_text_is_left_as_written(text: str) -> None:
    assert join_split_emoji(text) == text


def test_only_a_neutral_person_joins_a_tree() -> None:
    assert join_split_emoji("🧑🎄") == "🧑‍🎄"
    assert join_split_emoji("👩🎄") == "👩🎄"


def test_code_is_left_as_written() -> None:
    text = "```python\nprint('👨🚀')\n```"
    assert join_split_emoji(text) == text


# A worked solution has no emoji at any setting: at "Lots", "✅ **Answer**" was no Answer
# heading, and a Class 8 speed came back with no answer box (2026-10-30).
_WORKED = (
    "🚶 **Given**\n$d = 15\\ \\text{km}$\n\n🎯 **Find**\nAverage speed $v$.\n\n"
    "**Substitution**\n$v = \\frac{15}{3}$\n\n✅ **Answer**\nRaja's average speed is "
    "$5\\ \\text{km/h}$. 🎉"
)


@pytest.mark.parametrize("level", ["off", "some", "more"])
def test_a_worked_solution_has_no_emoji_at_any_setting(level: str) -> None:
    out = place_emoji(_WORKED, level, user_wrote_emoji=True)
    assert out == (
        "**Given**\n$d = 15\\ \\text{km}$\n\n**Find**\nAverage speed $v$.\n\n"
        "**Substitution**\n$v = \\frac{15}{3}$\n\n**Answer**\nRaja's average speed is "
        "$5\\ \\text{km/h}$."
    )


@pytest.mark.parametrize("heading", ["Required", "Find"])
def test_what_is_asked_is_a_section_under_either_name(heading: str) -> None:
    # Given alone is one section; with what is asked (Find: an older Required) it is worked.
    reply = f"🚶 **Given**\n$d = 15$\n\n🎯 **{heading}**\nAverage speed $v$."
    out = place_emoji(reply, "more", user_wrote_emoji=True)
    assert out == f"**Given**\n$d = 15$\n\n**{heading}**\nAverage speed $v$."
    assert not EMOJI.search(out)


def test_one_answer_heading_alone_is_not_a_worked_solution() -> None:
    reply = "### 🧠 Memory\nSleep helps it.\n\n✅ **Answer**\nSleep more."
    assert place_emoji(reply, "more", user_wrote_emoji=False) == reply


def test_answer_and_check_out_labels_are_no_worked_solution() -> None:
    reply = "🎯 **Answer:** Paris is the capital of France 🇫🇷.\n📌 **Check out** the Louvre."
    assert place_emoji(reply, "more", user_wrote_emoji=False) == reply


@pytest.mark.parametrize(
    ("text", "emoji"),
    [
        # 2026-10-31: "⏳" stayed in a homework reply the emoji rule had emptied.
        ("⏳", True),
        ("⌛", True),
        ("⌚", True),
        ("⏰", True),
        ("⏩", True),
        # Maths and chemistry symbols beside them are text.
        ("⌊x⌋ + ⌈x⌉", False),
        ("A → B", False),
        ("x ≤ 3", False),
    ],
)
def test_clock_and_media_emoji_are_emoji_and_brackets_are_not(text: str, emoji: bool) -> None:
    assert bool(EMOJI.search(text)) is emoji
