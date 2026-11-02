""" "What?" right after a reply means the user did not follow it.

After a Spanish reply in an English app, "What?" got "Gd: good, or something else?": the
model read it as a message it could not make out and copied the unclear-message example.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.chat.message_notes import message_notes
from app.modules.chat.prompt_constants.reply_missed import (
    REPLY_HOW_HINT,
    REPLY_MISSED_HINT,
    reply_how_hint,
    reply_missed_hint,
)
from app.modules.chat.prompt_constants.shared_numbers import SHARED_NUMBERS_HINT
from app.modules.chat.prompt_constants.unclear import UNCLEAR_MESSAGE_HINT

_AFTER_A_REPLY = [
    ("user", "Explícame la fotosíntesis en dos frases"),
    ("assistant", "La fotosíntesis es el proceso por el cual las plantas convierten la luz..."),
]
_IN_ENGLISH = "Write it in English, the language of their message."
_EN = SimpleNamespace(locale="en", custom_instructions=None, emoji_use="some")


@pytest.mark.parametrize(
    "query",
    [
        "What?",
        "what??",
        "what do you mean",
        "I don't get it",
        "I don’t get it",  # the iPhone's curly apostrophe
        "i  dont understand",
        "come again?",
        "Sorry?",
        "I’m lost",
        "that makes no sense",
    ],
)
def test_english_words_after_a_reply_ask_for_it_again_in_english(query: str) -> None:
    assert reply_missed_hint(query, _AFTER_A_REPLY) == f"{REPLY_MISSED_HINT} {_IN_ENGLISH}"


@pytest.mark.parametrize("query", ["huh?", "Eh?", "Hm?", "Pardon ?", "??"])
def test_words_of_many_languages_ask_for_it_again_in_its_language(query: str) -> None:
    assert reply_missed_hint(query, _AFTER_A_REPLY) == REPLY_MISSED_HINT


@pytest.mark.parametrize(
    "query",
    [
        # Surprise, an apology, thinking: not a reply they missed.
        "what!",
        "WHAT",
        "sorry",
        "Sorry!!",
        "hmm",
        "Hmm...",
        "eh",
        # Something in the reply or a photo sent with it, or a question of its own.
        "What's that?",
        "what does that mean?",
        "What time is it?",
        "what is photosynthesis",
        "huh, interesting",
        "sorry for the late reply",
        "what about the roots?",
        "I don't get why plants need light",
    ],
)
def test_other_messages_are_not_a_missed_reply(query: str) -> None:
    assert reply_missed_hint(query, _AFTER_A_REPLY) is None


def test_with_no_reply_before_there_is_nothing_to_follow() -> None:
    assert reply_missed_hint("What?", []) is None
    assert reply_missed_hint("What?", [("user", "hi")]) is None


def _exchange(*pairs: tuple[str, str]) -> list[SimpleNamespace]:
    return [SimpleNamespace(role=role, content=content) for role, content in pairs]


def test_the_notes_sit_in_order_and_only_when_they_apply() -> None:
    rain = "Monthly rainfall: Jan 15, Feb 30, Mar 60, Apr 85"
    assert message_notes("??", _exchange(*_AFTER_A_REPLY), _EN) == [REPLY_MISSED_HINT]
    assert message_notes(rain, [], _EN)[0].startswith(SHARED_NUMBERS_HINT)
    # The message's language comes last, nearest it.
    notes = message_notes("What?", _exchange(*_AFTER_A_REPLY), _EN)
    assert notes[0].startswith(REPLY_MISSED_HINT)
    assert notes[-1].startswith("Write this reply in English,")


@pytest.mark.parametrize(
    "reply",
    [
        # A lesson explains it again under its own title, with a fresh quiz.
        "### Lesson 2: Loops\n\nA loop repeats code.\n\n```quiz\n{}\n```",
        # A clarify card's turn answers the request now.
        'Which kind?\n\n```clarify\n{"question": "Which kind?", "options": ["a", "b"]}\n```',
    ],
)
def test_a_lesson_or_a_card_reads_what_its_own_way(reply: str) -> None:
    notes = message_notes(
        "I don't get it", _exchange(("user", "teach me"), ("assistant", reply)), _EN
    )
    assert not any(note.startswith(REPLY_MISSED_HINT) for note in notes)


def test_the_unclear_rule_gives_no_reply_to_copy() -> None:
    """Its examples were whole replies a small model sent as they were."""
    assert "Gd:" not in UNCLEAR_MESSAGE_HINT
    assert "Were you still typing?" not in UNCLEAR_MESSAGE_HINT


# Live (2026-10-29): after "Answer: 16.09344 km", "How" got "Did you mean how the
# conversion works, or were you still typing?".
_AFTER_AN_ANSWER = [
    ("user", "What if I convert 10 miles instead?"),
    ("assistant", "Answer: $16.09344\\ \\mathrm{km}$"),
]


@pytest.mark.parametrize(
    "query",
    [
        "How",
        "how?",
        "Why?",
        "how so",
        "How come?",
        "how did you get that?",
        "Explain",
        "show me how",
        "show your work",
    ],
)
def test_how_right_after_a_reply_asks_how_it_was_reached(query: str) -> None:
    assert reply_how_hint(query, _AFTER_AN_ANSWER) == REPLY_HOW_HINT
    exchange = [SimpleNamespace(role=role, content=text) for role, text in _AFTER_AN_ANSWER]
    assert REPLY_HOW_HINT in message_notes(query, exchange, _EN)
    assert reply_missed_hint(query, _AFTER_AN_ANSWER) is None


@pytest.mark.parametrize(
    "query",
    [
        "How are you?",
        "how do I bake bread",
        "Why not",
        "How much is 10 miles in feet?",
        "explain photosynthesis",
    ],
)
def test_a_question_of_its_own_is_not_how_at_the_last_reply(query: str) -> None:
    assert reply_how_hint(query, _AFTER_AN_ANSWER) is None


def test_how_with_no_reply_before_it_is_left_to_the_model() -> None:
    assert reply_how_hint("How", []) is None


@pytest.mark.parametrize(
    ("last_reply", "query"),
    [
        # A reply that ended on its own question: "Why" answers it.
        ("Should we use Redis?", "Why"),
        ("Hey! How are you?", "how"),
        # "show me" after an offer is a yes, not a how.
        ("Let's solve 5x^2 - 3 = -3. Want me to work it out?", "show me"),
        ("Answer: 4", "show me"),
    ],
)
def test_how_after_a_question_or_an_offer_is_not_about_an_answer(
    last_reply: str, query: str
) -> None:
    assert reply_how_hint(query, [("user", "hi"), ("assistant", last_reply)]) is None
