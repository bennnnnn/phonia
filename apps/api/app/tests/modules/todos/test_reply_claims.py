"""A reply above an untapped card never says the reminder already exists."""

from __future__ import annotations

import pytest

from app.modules.todos.reply_claims import is_claim, without_claims


@pytest.mark.parametrize(
    "sentence",
    [
        "Done!",
        "All set ✅",
        "Okay, reminder set.",
        "I've set a reminder to call the dentist tomorrow at 9 AM.",
        "I set up a daily reminder for your vitamins.",
        "I'll remind you tomorrow at 9 am.",
        "I will make sure to remind you on Friday.",
        "I'll set a reminder for that.",
        "Your reminder is set for tomorrow at 3 PM.",
        "Reminder set for tomorrow at 9 AM to call the dentist.",
        "I've added 'Call the dentist' to your reminders for tomorrow.",
        "Added it to your to-do list.",
        "You'll get a reminder tomorrow at 9 AM.",
        "You'll be reminded at 6 PM.",
        "It's on your list for Friday.",
        "I've set it for 9 AM tomorrow.",
        "It's set for 6:30 PM.",
        "I've marked call mom as done.",
        "Deleted the gym reminder.",
        "Moved gym to Sunday.",
        "Scheduled for tomorrow at 9.",
        "Set: call mom — Thursday, Oct 15, 6:00 PM.",
        "**Done** — call the dentist, tomorrow at 9 AM.",
        # Live 2026-10-25: above an untapped card, and after a "yes" that saved nothing.
        "Got it set for tomorrow evening! 📅",
        "Got it, set for tomorrow at 7 PM.",
        "All set for tomorrow at 7!",
        "Got it all set for Monday.",
        "Setting that reminder for you now! ⏰",
        "I'm setting that reminder for you now.",
        "Sure, adding that reminder now.",
        "Okay, setting it for 7 PM tomorrow.",
        "I'm setting that up for tomorrow at 9.",
        "OK, adding milk to your list.",
        "Sure thing! I'll set that for you.",
        "I'll set it for you now!",
    ],
)
def test_is_claim_reads_a_completed_reminder_change(sentence: str) -> None:
    assert is_claim(sentence, ["call mom", "gym"])


@pytest.mark.parametrize(
    "sentence",
    [
        "Every morning I set aside time to write before work.",
        "The meeting is set for Friday, so Thursday evening is a good time to prep.",
        "It's set to 180°C for the whole bake.",
        "Water boils at 100 °C (212 °F) at sea level.",
        "Want me to set a reminder for that too?",
        "Here's the reminder I can add:",
        "Don't forget your passport.",
        "I made a cake for her birthday.",
        "Let me know if you want another one.",
        "The alarm in the story is set for dawn.",
        "Set the oven to 180°C.",
        "I'm setting aside time to write.",
        "You're all set for baking!",
        "Got it! Water boils at 100 °C.",
        "Setting goals is important.",
        "I'm adding the eggs now.",
        "Got it, the answer is 12.",
        "Setting up a reminder system takes practice.",
        "Okay, setting the oven to 200.",
        "Setting it to medium heat for 10 minutes.",
        # Advice in a plan is no claim (review of the first draft).
        "Set a wind-down reminder for 10:30 PM.",
        "Set your alarm for 6 AM tomorrow.",
        "Set a reminder for 12:30 PM so you actually stop for lunch.",
        "Setting a reminder for your snack is a good idea too.",
        "Adding a reminder the night before helps.",
        "You're all set for Friday's interview!",
        "I'll set that up for you below: here is the config.",
        "Setting it to 350°F for 20 minutes tonight works best.",
        "Setting this up takes 5 minutes each morning.",
    ],
)
def test_is_claim_leaves_ordinary_sentences(sentence: str) -> None:
    assert not is_claim(sentence, ["call the dentist"])


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        ("Done! I've set a reminder to call the dentist tomorrow at 9 AM.", ""),
        ("Sure! I'll remind you tomorrow at 9 am.", ""),
        (
            "Water boils at **100 °C** at sea level.\n\nI'll remind you tomorrow at 9 am.",
            "Water boils at **100 °C** at sea level.",
        ),
        (
            "Water boils at 100 °C, and I've set a reminder to buy milk tomorrow.",
            "Water boils at 100 °C.",
        ),
        (
            "Good luck with the visit! Your reminder is set for 9 AM.",
            "Good luck with the visit!",
        ),
        (
            "- Done! Reminder set for 9 AM.\n- Bring your insurance card.",
            "- Bring your insurance card.",
        ),
        (
            "The meeting is set for Friday. I'll remind you Thursday at 5 PM to prep the slides.",
            "The meeting is set for Friday.",
        ),
        (
            "Every morning I set aside time to write. It's set for 6 AM.",
            "Every morning I set aside time to write.",
        ),
        (
            "```python\nprint('Reminder set for 9 AM')\n```",
            "```python\nprint('Reminder set for 9 AM')\n```",
        ),
    ],
)
def test_without_claims_keeps_everything_but_the_claim(reply: str, kept: str) -> None:
    assert without_claims(reply, ["call the dentist", "buy milk"]) == kept
