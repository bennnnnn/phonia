"""A clarify card in history, and the turn that answers it."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.chat.clarify_turn import (
    answers_card,
    card_as_line,
    card_in_reply,
    clarify_reply_hint,
)
from app.modules.chat.prompt_constants.clarify import CLARIFY_PICKS_HINT, CLARIFY_UNANSWERED_HINT
from app.modules.chat.prompt_window import PromptWindow, history_messages
from app.modules.chat.turn_prep.mode import classify_turn_mode

_QUESTION = "What is the best country"
_CARD: dict[str, object] = {
    "request": "Recommend the best country for me.",
    "questions": [
        {
            "id": "priority",
            "label": "Main priority",
            "question": "What matters most to you?",
            "options": ["💰 Making money", "🌿 Quality of life", "🛡️ Safety"],
        },
        {
            "id": "region",
            "label": "Geographic preference",
            "question": "Which region are you considering?",
            "options": ["🌍 Anywhere", "🇪🇺 Europe", "🌎 The Americas"],
        },
    ],
    "closing": "Compare the strongest options with practical pros and cons.",
    "submit": "Find my best country",
}


def _reply(card: dict[str, object] = _CARD, prose: str = "What do you mean by *best*?") -> str:
    return f"{prose}\n\n```clarify\n{json.dumps(card)}\n```"


def _prior(reply: str) -> list[tuple[str, str]]:
    return [("user", _QUESTION), ("assistant", reply)]


_PICKS = (
    "Recommend the best country for me. Main priority: Making money. Geographic preference: "
    "Anywhere. Compare the strongest options with practical pros and cons."
)


def test_card_in_reply_reads_the_card_a_reply_ended_on() -> None:
    card = card_in_reply(_reply())
    assert card is not None and [q.label for q in card.questions] == [
        "Main priority",
        "Geographic preference",
    ]
    assert card_in_reply("No card here.") is None
    assert card_in_reply(None) is None


def test_a_card_in_history_is_one_line_of_what_it_asked() -> None:
    assert card_as_line(json.dumps(_CARD)) == (
        "Asked: What matters most to you? [Making money / Quality of life / Safety]; "
        "Which region are you considering? [Anywhere / Europe / The Americas]\n"
    )
    assert card_as_line("{broken") == ""


def test_history_shows_the_model_the_line_not_the_json() -> None:
    rows = [
        SimpleNamespace(id=uuid4(), role="user", content=_QUESTION),
        SimpleNamespace(id=uuid4(), role="assistant", content=_reply()),
    ]
    window = PromptWindow(recent=rows, gap=[], exchange=rows)
    assistant = history_messages(window, math_followup=False)[1]["content"]
    assert "```clarify" not in assistant
    assert "Asked: What matters most to you?" in assistant


@pytest.mark.parametrize(
    ("message", "answered"),
    [
        (_PICKS, True),
        # Labels in any case, without the request and closing.
        ("main priority: Safety. GEOGRAPHIC PREFERENCE: Europe.", True),
        # The shape older phones send: one "Label: pick" line per question.
        ("Main priority: Safety\nGeographic preference: Europe", True),
        ("Main priority: Making money. Also, what about taxes?", False),
        ("Making money, anywhere", False),
        ("Main priority:\nGeographic preference:", False),
        ("Main priority:\nGeographic preference: Europe", False),
        ("Main priority: Safety. Region: Europe.", False),
        ("Submain priority: Safety. Geographic preference: Europe.", False),
        ("", False),
    ],
)
def test_answers_card_needs_every_label_with_a_pick(message: str, answered: bool) -> None:
    card = card_in_reply(_reply())
    assert card is not None and answers_card(message, card) is answered


@pytest.mark.parametrize(
    ("message", "hint"),
    [
        (_PICKS, CLARIFY_PICKS_HINT),
        # Anything typed instead of tapping, in any language.
        ("Just answer", CLARIFY_UNANSWERED_HINT),
        ("Responde sin más", CLARIFY_UNANSWERED_HINT),
        ("what about Canada?", CLARIFY_UNANSWERED_HINT),
    ],
)
def test_the_turn_after_a_card_gets_what_to_answer(message: str, hint: str) -> None:
    assert clarify_reply_hint(message, _prior(_reply())) == hint


def test_an_older_card_with_when_still_reads_its_picks() -> None:
    prior = _prior(_reply({**_CARD, "when": "after"}))
    assert clarify_reply_hint(_PICKS, prior) == CLARIFY_PICKS_HINT


@pytest.mark.parametrize(
    "prior",
    [
        [("user", _QUESTION), ("assistant", "An integral adds up slices.")],
        # The card was two replies ago: this turn no longer answers it.
        [*_prior(_reply()), ("user", "Just answer"), ("assistant", "Here is the idea.")],
        [],
    ],
)
def test_no_hint_without_a_card_in_the_last_reply(prior: list[tuple[str, str]]) -> None:
    assert clarify_reply_hint(_PICKS, prior) is None


def test_no_hint_for_an_empty_message() -> None:
    assert clarify_reply_hint("  ", _prior(_reply())) is None


@pytest.mark.parametrize("message", ["Just answer", "ok", _PICKS])
def test_the_message_after_a_card_is_a_full_turn(message: str) -> None:
    recent = [
        SimpleNamespace(role="user", content=_QUESTION),
        SimpleNamespace(role="assistant", content=_reply()),
    ]
    mode = classify_turn_mode(recent, message)
    assert mode.lightweight is False
    assert mode.rich_context is True
    # It answers the card, so finalize lets it hold no card of its own.
    assert mode.after_card is True


def test_ok_without_a_card_is_still_small_talk() -> None:
    recent = [
        SimpleNamespace(role="user", content="thanks"),
        SimpleNamespace(role="assistant", content="Anytime!"),
    ]
    assert classify_turn_mode(recent, "ok").lightweight is True
    assert classify_turn_mode(recent, "ok").after_card is False
