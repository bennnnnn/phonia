"""A preference an app setting decides is not memory.

"Reply in Spanish from now on" was saved as "User prefers replies in Spanish and without
emojis", and a lesson turn answered an English app in Spanish (2026-10-24). Reading facts
with patterns hid real ones ("User answers customer emails in Spanish at work"), so the
memory models are told instead, and the reply's language line ranks a saved memory last.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway, mock_llm
from app.modules.chat.message_notes import message_notes
from app.modules.chat.response_tone import _EMOJI_NEVER, EMOJI_HINTS, emoji_note
from app.modules.memory import llm as memory_llm
from app.modules.memory.llm import INSTRUCT_SETTING_RULE, SETTING_PREFERENCE_RULE


async def _system_prompt(monkeypatch: pytest.MonkeyPatch, call: Any) -> str:
    captured: dict[str, Any] = {}

    async def fake_complete_structured(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(mock_llm, "should_mock_llm", lambda _settings: False)
    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_complete_structured)
    await call()
    return str(captured["messages"][0]["content"])


@pytest.mark.asyncio
async def test_extraction_leaves_a_settings_preference_to_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = await _system_prompt(
        monkeypatch,
        lambda: memory_llm.revise_memory_facts(Settings(), "User: reply in Spanish from now on"),
    )
    assert SETTING_PREFERENCE_RULE in system


@pytest.mark.asyncio
async def test_the_memory_page_points_a_settings_preference_to_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = await _system_prompt(
        monkeypatch,
        lambda: memory_llm.instruct_memory(
            Settings(), "Always reply to me in Spanish", existing_facts=[], existing_areas=[]
        ),
    )
    assert INSTRUCT_SETTING_RULE in system


@pytest.mark.parametrize("level", list(EMOJI_HINTS))
def test_the_emoji_setting_outranks_a_saved_memory(level: str) -> None:
    assert EMOJI_HINTS[level].endswith("a saved memory never changes it.")


# At "Lots" a list of tips came back with no emoji in most replies (2026-10-29): the Emoji
# line at the top of the prompt lost to the rest, and a saved "no emojis" fact pulls the
# same way. The setting is said again beside the message.
_NO_EMOJI_FACT = "Known facts about the user:\n\n## Preferences\n- User prefers no emojis"
_OTHER_FACT = "Known facts about the user:\n\n## Profile\n- Name is Bini"


@pytest.mark.parametrize("memory_block", ["", _OTHER_FACT, _NO_EMOJI_FACT])
def test_lots_always_gets_the_setting_beside_the_message(memory_block: str) -> None:
    user = SimpleNamespace(locale="en", custom_instructions=None, emoji_use="more")
    note = emoji_note("more", memory_block)
    assert note is not None and note.startswith("Emoji in this reply: plenty,")
    assert ("out of date" in note) == (memory_block == _NO_EMOJI_FACT)
    assert note in message_notes("Give me tips to sleep better", [], user, memory_block)


@pytest.mark.parametrize(
    ("level", "memory_block", "noted"),
    [
        # "A few" (and an unknown level, read as the default) only when a memory competes.
        ("some", _NO_EMOJI_FACT, True),
        (None, _NO_EMOJI_FACT, True),
        ("some", _OTHER_FACT, False),
        ("some", "", False),
        # "off" is enforced after the reply (emoji_placement), so no note.
        ("off", _NO_EMOJI_FACT, False),
    ],
)
def test_a_few_and_off_get_a_note_only_when_it_helps(
    level: str | None, memory_block: str, noted: bool
) -> None:
    note = emoji_note(level, memory_block)
    assert (note is not None) == noted
    if noted:
        assert note is not None and note.startswith("Emoji in this reply: a few,")


def test_the_lots_note_carries_where_emoji_never_go() -> None:
    # Nearest the message, it would outrank the Emoji line's exceptions it only pointed at.
    note = emoji_note("more", "")
    assert note is not None
    assert _EMOJI_NEVER in note
    assert "A lesson keeps its own emoji rule." in note


def test_a_fact_that_only_names_emoji_is_not_called_out_of_date() -> None:
    project = "Known facts about the user:\n\n## Projects\n- Building an emoji picker app"
    note = emoji_note("more", project)
    assert note is not None and "out of date" not in note
    assert emoji_note("some", project) is None


def test_a_lesson_places_its_own_emoji() -> None:
    user = SimpleNamespace(locale="en", custom_instructions=None, emoji_use="more")
    taught = "### Lesson 1: Dictionaries\n\nA dict maps keys to values.\n\nWhat does d['a'] return?"
    lesson = [
        SimpleNamespace(role="user", content="Teach me dictionaries"),
        SimpleNamespace(role="assistant", content=taught),
    ]
    assert not any(n.startswith("Emoji in this reply") for n in message_notes("ok", lesson, user))
    # The first lesson too: "one fitting emoji in the opening line" is the lesson's rule.
    first = message_notes("Teach me Python dictionaries", [], user)
    assert not any(n.startswith("Emoji in this reply") for n in first)
