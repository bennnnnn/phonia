"""What a chat line tells memory to do: remember, mute, reset, correct (M10, M11, M9)."""

import pytest

from app.modules.memory.commands import (
    is_explicit_memory_command,
    is_explicit_mute_command,
    is_memory_correction,
    memory_reset_request,
    mute_requests,
    remember_requests,
)


@pytest.mark.parametrize(
    ("text", "remember"),
    [
        ("Remember I'm vegetarian", True),
        # A comma or colon after "remember" still asks; "I've" and "I'll" are the user.
        ("Remember, I'm allergic to peanuts.", True),
        ("remember: my wife's name is Sara", True),
        ("Remember I've got a gluten intolerance", True),
        ("Remember I'll need wheelchair access when I travel", True),
        # The words people use for a memory feature.
        ("Save to memory that I'm lactose intolerant", True),
        ("add this to your memory: I take insulin twice a day", True),
        ("Can you save that to your memory?", True),
        # Talk, a question, or the task in hand.
        ("Remember, the answer has to be in centimetres", False),
        ("Remember, remember the fifth of November: where is that from?", False),
        ("Remember when I asked you about Lisbon?", False),
        ("how do I save to memory instead of disk on an Arduino?", False),
        ("I can't remember the capital of Peru", False),
    ],
)
def test_remember_commands_are_read_however_they_are_punctuated(text, remember):
    assert is_explicit_memory_command(text) is remember


def test_remember_requests_name_the_fact():
    assert remember_requests("Remember I'm vegetarian") == ["I'm vegetarian"]
    assert remember_requests("Please remember my dog is called Max.") == ["my dog is called Max"]
    assert remember_requests("do you remember that song?") == []


@pytest.mark.parametrize(
    ("text", "mute"),
    [
        ("stop mentioning my job", True),
        ("Please stop bringing up my weight", True),
        ("don't bring up my divorce again", True),
        ("stop using my location in answers", True),
        ("never mention my ex again", True),
        ("From now on, don't mention my age", True),
        # The draft in hand, not memory.
        ("Don't mention my name in the email, just sign it from the team", False),
        ("don't mention my name", False),
        # Talk about muting, not an instruction.
        ("how do I stop mentioning my ex in every conversation?", False),
        ("My mom keeps telling me to stop bringing up politics at dinner", False),
        ("Write a scene where she says 'don't bring up my past again'", False),
        ("Never mention the war, Basil", False),
        ("stop using my phone before bed is hard, any tips?", False),
        ("Please don't bring up the budget in the meeting", False),
    ],
)
def test_mute_commands_are_lasting_instructions_about_the_user(text, mute):
    assert is_explicit_mute_command(text) is mute
    assert is_explicit_memory_command(text) is mute


def test_mute_requests_name_the_fact():
    assert mute_requests("stop mentioning my job") == ["my job"]
    assert mute_requests("stop using my location in answers") == ["my location in answers"]
    assert mute_requests("how do I stop mentioning my ex?") == []


@pytest.mark.parametrize(
    ("text", "reset"),
    [
        ("forget everything you know about me", "clear"),
        ("Please forget everything about me", "clear"),
        ("can you clear your memory of me?", "clear"),
        ("delete everything you know about me", "clear"),
        ("stop remembering things about me", "off"),
        ("don't remember anything about me", "off"),
        ("turn off memory", "off"),
        ("turn off memory please", "off"),
        # Not a reset: this conversation, a person's own past, a tool.
        ("forget everything I said, let's start over with the essay", None),
        ("I want to forget everything about my ex", None),
        ("how do I clear my memory cache in Chrome?", None),
        ("Clear my memory of that awful movie and recommend something better", None),
        ("turn off memory leak warnings in Xcode", None),
        ("Do you remember everything about me?", None),
        ("forget all the previous questions", None),
    ],
)
def test_reset_requests_need_the_users_memory(text, reset):
    assert memory_reset_request(text) == reset
    if reset:
        assert is_explicit_memory_command(text)


@pytest.mark.parametrize(
    ("text", "correction"),
    [
        ("that's wrong, I'm at Stripe now", True),
        ("Actually I switched from FastAPI to Django", True),
        ("I don't work at Uber anymore", True),
        ("I no longer live in Nairobi", True),
        ("I moved to Lisbon last month", True),
        ("what's the weather in Lisbon", False),
        ("I'm forever grateful", False),
    ],
)
def test_corrections_are_read_anywhere_in_the_line(text, correction):
    assert is_memory_correction(text) is correction
