"""A generic closing line comes off a finished reply; everything else stays (Q8)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.chat.generic_closer import drop_generic_closer, strip_generic_closer

ANSWER = "Water boils at **100 °C** at sea level."


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        (f"{ANSWER}\n\nLet me know if you have any other questions!", ANSWER),
        (f"{ANSWER}\n\nHope this helps! 😊", ANSWER),
        (f"{ANSWER} I hope this helps.", ANSWER),
        (f"{ANSWER}\n\n*Feel free to ask if you have any more questions.*", ANSWER),
        (f"{ANSWER}\n\nIf you have any questions, feel free to ask.", ANSWER),
        (f"{ANSWER}\n\nIs there anything else I can help you with?", ANSWER),
        (f"{ANSWER}\n\nLet me know if there’s anything else I can help with.", ANSWER),
        (f"{ANSWER}\n\nLet me know if you need anything else.", ANSWER),
        (f"{ANSWER}\n\n---\n\nHope this helps!", ANSWER),
        (f"{ANSWER}\n\nHope this helps! Let me know if you have any other questions.", ANSWER),
        (
            "```python\nprint(1)\n```\n\nLet me know if you have any questions or need "
            "further clarification.",
            "```python\nprint(1)\n```",
        ),
        (f"{ANSWER}\n\nAnything else I can help with?", ANSWER),
        # The user wrote emoji, so the reply did: the flag stays with its own sentence.
        (
            f"{ANSWER}\n\nHappy cooking! 🇳🇬 Let me know if you have any other questions! 😊",
            f"{ANSWER}\n\nHappy cooking! 🇳🇬",
        ),
        (f"{ANSWER} 👨‍👩‍👧 Hope this helps!", f"{ANSWER} 👨‍👩‍👧"),
        (f"{ANSWER}\n\n😊 Hope this helps!", ANSWER),
    ],
)
def test_a_generic_closer_on_the_last_line_comes_off(reply: str, kept: str) -> None:
    assert drop_generic_closer(reply) == kept


@pytest.mark.parametrize(
    "reply",
    [
        # A concrete next step is allowed (FORMAT_CONTRACT, Ending).
        f"{ANSWER}\n\nLet me know if you want it in Fahrenheit too.",
        f"{ANSWER}\n\nWant the boiling point at altitude as well?",
        # Not the last line.
        f"Hope this helps!\n\n{ANSWER}",
        # The whole reply.
        "Hope this helps!",
        # Inside a fence, a quote, a list or a table.
        "```text\nLet me know if you have any other questions.\n```",
        "```email\nHi Sam,\n\nLet me know if you have any questions.",
        f"{ANSWER}\n\n> Let me know if you have any other questions.",
        f"{ANSWER}\n\n- Let me know if you have any other questions.",
        f"{ANSWER}\n\n1. Hope this helps.",
        f"{ANSWER}\n\n| Hope this helps |",
        f"{ANSWER}\n\n    Hope this helps!",
        # Part of a longer sentence.
        f"{ANSWER}\n\nHope this helps with your exam tomorrow, good luck!",
        "",
    ],
)
def test_everything_else_stays_exactly(reply: str) -> None:
    assert drop_generic_closer(reply) == reply


def _state(text: str, query: str, *, cancelled: bool = False, instant: bool = False, prior=()):
    messages = [*({"role": r, "content": c} for r, c in prior), {"role": "user", "content": query}]
    return SimpleNamespace(
        text=text,
        was_cancelled=cancelled,
        server_text=instant,
        ctx=SimpleNamespace(user_message_content=query, prompt_messages=messages),
    )


CLOSED = f"{ANSWER}\n\nLet me know if you have any other questions."


def test_the_pass_strips_a_model_reply() -> None:
    assert strip_generic_closer(_state(CLOSED, "what is the boiling point of water?")) == ANSWER


@pytest.mark.parametrize(
    "query",
    [
        # Drafts, rewrites and translations end the way the user's text does.
        "write an email to my landlord about the broken heater",
        "rewrite this to sound friendlier: Send the report now.",
        "translate 'let me know if you have any other questions' into Spanish",
        # The user asked about the phrase itself.
        "is 'hope this helps' too informal for a work email?",
    ],
)
def test_the_pass_leaves_text_the_user_shaped(query: str) -> None:
    assert strip_generic_closer(_state(CLOSED, query)) == CLOSED


def test_the_pass_leaves_a_draft_follow_up() -> None:
    prior = (
        ("user", "write a message to my landlord saying the heater is broken"),
        ("assistant", "```message\nHi Sam, the heater is broken.\n```"),
    )
    state = _state(CLOSED, "make it more polite", prior=prior)
    assert strip_generic_closer(state) == CLOSED


@pytest.mark.parametrize(("cancelled", "instant"), [(True, False), (False, True)])
def test_the_pass_leaves_a_stopped_or_server_reply(cancelled: bool, instant: bool) -> None:
    state = _state(CLOSED, "what is the boiling point?", cancelled=cancelled, instant=instant)
    assert strip_generic_closer(state) == CLOSED
