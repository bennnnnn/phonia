"""A reply says nothing about the turn: no clock read back unasked, no "you accepted my offer"."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.chat.reply_meta import without_turn_meta

_CLOCK = "It's currently **Sunday, October 25, 2026, 6:15 PM EDT**."
_TODAY = date(2026, 10, 25)


@pytest.mark.parametrize(
    ("reply", "asked", "kept"),
    [
        # Live chat (2026-10-25): a short turn got the clock as filler.
        (f"Got it. {_CLOCK}\n\nWhich goal fits best?", "1", "Got it.\n\nWhich goal fits best?"),
        (
            "Got it, Dev. It's Sunday, October 25, 2026, 7:01 PM EDT.\n\nStart tonight.",
            "Okay.",
            "Got it, Dev.\n\nStart tonight.",
        ),
        (
            "Dev, you accepted my offer, so here is the 20% down payment comparison.",
            "Yes",
            "Here is the 20% down payment comparison.",
        ),
        (
            "You accepted my last offer again, so here is the 15-year comparison.",
            "yes",
            "Here is the 15-year comparison.",
        ),
        (
            "Got it. It's currently Sunday, October 25, 2026, 6:15 p.m. EDT. What next?",
            "1",
            "Got it. What next?",
        ),
        ("Great, you accepted my offer. iPhone tips below.", "yes", "iPhone tips below."),
        # Live chat (2026-10-26): "Oh really?" got the date and the clock, in another shape.
        (
            "Yes, today is Sunday, October 25, 2026, and it's 2:14 PM EDT. Your next item is "
            "the pharm study session on Wednesday, October 28, 2026, at 7:00 PM.",
            "Oh really?",
            "Your next item is the pharm study session on Wednesday, October 28, 2026, at 7:00 PM.",
        ),
        (
            "Today is Sunday, October 25, 2026. Here is the answer you wanted.",
            "Oh really?",
            "Here is the answer you wanted.",
        ),
    ],
)
def test_turn_meta_goes(reply: str, asked: str, kept: str) -> None:
    assert without_turn_meta(reply, asked, _TODAY) == kept


@pytest.mark.parametrize(
    ("reply", "asked"),
    [
        # The message is about the day or the time: the date is the answer.
        ("Today is Sunday, October 25, 2026, so tomorrow is Monday.", "It is monday"),
        (_CLOCK, "what time is it"),
        ("It's Sunday, October 25, 2026.", "what's today's date"),
        # A date inside a sentence, a plan or code is content.
        ("Read for 20 minutes each evening, starting tonight, Sunday, October 25, 2026.", "Yes"),
        ("```\nIt's Sunday, October 25, 2026\n```", "print the date line"),
        ("Your offer was accepted by the seller, so here are the next steps.", "yes"),
        # A reply that is only the clock keeps it rather than going empty.
        (_CLOCK, "ok"),
        # The date says something (review, 2026-10-25), or is not today.
        ("It's Sunday, October 25, 2026 — the deadline you set is today.", "when is it due"),
        (
            "It's Sunday, October 25, 2026, so the post office is closed.",
            "is the post office open?",
        ),
        ("It's Sunday, October 25, 2026, so you are 36.", "how old am I if I was born in 1990?"),
        ("It's Monday, November 2, 2026 when the package arrives.", "when will it arrive"),
        ("Got it. It's Monday, November 2, 2026.", "ok"),
        ("Your deadline? It's Sunday, October 25, 2026. Get it in tonight.", "when is it due?"),
        ("| Date | Plan |\n|---|---|\n| It's Monday, November 2, 2026 | Fly out |", "plan my trip"),
        # Only a timezone abbreviation ends the clock; a word after it is the sentence going on.
        ("Today is Sunday, October 25, 2026, and it's 2:14 PM sharp. Be ready.", "Oh really?"),
        ("Today is Sunday, October 25, 2026, and it's the deadline for your essay.", "Oh really?"),
    ],
)
def test_other_text_stays(reply: str, asked: str) -> None:
    assert without_turn_meta(reply, asked, _TODAY) == reply
