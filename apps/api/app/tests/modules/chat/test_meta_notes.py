"""An apology or a line about the reply is plain text, never a Note card."""

from __future__ import annotations

import pytest

from app.modules.chat.meta_notes import unwrap_meta_notes

ANSWER = "To add fractions with the same denominator, add the numerators."


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            "> Note: I apologize for the formatting glitch. Here is the plain-text "
            f"explanation.\n\n{ANSWER}",
            "I apologize for the formatting glitch. Here is the plain-text explanation."
            f"\n\n{ANSWER}",
        ),
        (f"> **Note:** Sorry about that!\n\n{ANSWER}", f"Sorry about that!\n\n{ANSWER}"),
        (f"> **Note**: My apologies.\n\n{ANSWER}", f"My apologies.\n\n{ANSWER}"),
        (
            f"> [!NOTE]\n> Here's a simpler version.\n> It skips the jargon.\n\n{ANSWER}",
            f"Here's a simpler version.\nIt skips the jargon.\n\n{ANSWER}",
        ),
        (
            f"> Note: I’m sorry for the confusion.\n\n{ANSWER}",
            f"I’m sorry for the confusion.\n\n{ANSWER}",
        ),
        (
            f"> Note: As requested, the short version.\n\n{ANSWER}",
            f"As requested, the short version.\n\n{ANSWER}",
        ),
        (
            f"> Note: Thank you for your patience.\n\n{ANSWER}",
            f"Thank you for your patience.\n\n{ANSWER}",
        ),
        # Inside a list item the lines keep the item's indent.
        (
            "1. Add the tops.\n   > Note: I apologize, I mixed up the steps.\n2. Keep the bottom.",
            "1. Add the tops.\n   I apologize, I mixed up the steps.\n2. Keep the bottom.",
        ),
    ],
)
def test_a_note_about_the_reply_becomes_plain_lines(reply: str, expected: str) -> None:
    assert unwrap_meta_notes(reply) == expected


@pytest.mark.parametrize(
    "reply",
    [
        # A real note stays a card.
        f"> Note: The denominator must not be zero.\n\n{ANSWER}",
        f"> **Note:** Sorrel is not the same as spinach.\n\n{ANSWER}",
        f"> [!NOTE]\n> Hereford cattle are a beef breed.\n\n{ANSWER}",
        # A Warning may rightly open with an apology: it corrects something.
        f"> Warning: Sorry, I gave the wrong dose earlier: it is 200 mg.\n\n{ANSWER}",
        # A quote is not a callout.
        "> I'm sorry, Dave. I'm afraid I can't do that.\n> — HAL 9000",
        # Inside a code fence nothing changes.
        "```markdown\n> Note: Sorry for the delay.\n```",
        ANSWER,
    ],
)
def test_other_quotes_and_notes_are_left_alone(reply: str) -> None:
    assert unwrap_meta_notes(reply) == reply


def test_only_the_note_about_the_reply_is_unwrapped() -> None:
    reply = (
        "> Note: Sorry, here is the corrected list.\n"
        "> Warning: Never mix bleach and ammonia.\n\n"
        "> Note: Keep the lid on."
    )
    assert unwrap_meta_notes(reply) == (
        "Sorry, here is the corrected list.\n"
        "> Warning: Never mix bleach and ammonia.\n\n"
        "> Note: Keep the lid on."
    )
