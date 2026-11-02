"""Turn classifiers that read how a message relates to the chat: openers, corrections,
continuing, and how long the user asked the reply to be."""

from __future__ import annotations

import pytest

from app.modules.chat.continuation_subject import (
    is_pure_continuation,
    is_resume_request,
    works_on_last_reply,
)
from app.modules.chat.prompt_constants import repeated_greeting_hint
from app.modules.turn_reading.conversation import greeting_run, is_correction, is_social_opener
from app.modules.turn_reading.length import is_detail_request, reply_length
from app.modules.turn_reading.routing import is_lightweight_chat_turn


@pytest.mark.parametrize(
    "text",
    [
        "good morning!",
        "Good morning 🌞",
        "hello there",
        "how are you?",
        "hey! 😊 how are you?",
        "hi, how's it going",
        "hey how r u",
        "Morning!",
        "good evening, Recall",
        "what’s up?",
        "how have you been?",
        "how was your weekend?",
        "nice to meet you",
    ],
)
def test_a_greeting_that_asks_for_nothing_is_a_social_opener(text: str) -> None:
    assert is_social_opener(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "good morning, what's the capital of Peru?",
        "how are you different from ChatGPT?",
        "how are you able to remember things?",
        "what's up with my code? it throws on line 3",
        "hello world in python",
        "how do you say good morning in French",
        "write a good morning message for my wife",
        "hey there, can you help me with my resume?",
        "how's the weather in Nairobi",
        "",
    ],
)
def test_a_greeting_with_a_request_is_not_a_social_opener(text: str) -> None:
    assert is_social_opener(text) is False


def test_the_lightweight_list_does_not_grow_with_openers() -> None:
    # routing.py: social openers get the compact prompt, not the lightweight path.
    assert is_lightweight_chat_turn("hi") is True
    assert is_lightweight_chat_turn("good morning!") is False
    assert is_lightweight_chat_turn("how are you?") is False


@pytest.mark.parametrize(
    "text",
    [
        "no, I said I'm vegetarian",
        "No I said vegetarian",
        "actually I meant Python 2, not 3",
        "I meant Python 2, not 3",
        "I said Tuesday not Thursday",
        "that's wrong, it's 2024 not 2023",
        "That’s wrong — it’s 2024, not 2023",
        "wait, I asked for the metric version",
        "sorry, I meant the second option",
        "oops, I typed 2023, I meant 2024",
        "that's not what I asked",
        "you misunderstood me, I want the cheaper one",
        "I didn't say that",
        "I already told you I'm allergic to nuts",
        "like I said, I don't eat meat",
        "correction: the meeting is on Friday",
        "no, I'm vegetarian",
        "no I'm a teacher, not a student",
        "actually, I meant 5 km not 5 miles — thanks",
    ],
)
def test_a_correction_is_detected(text: str) -> None:
    assert is_correction(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "no, I said it was fine — thanks",
        "no it's fine, thank you",
        "actually, can you also add error handling?",
        "actually that sounds great",
        "I said hello to my neighbour and she ignored me, what should I do?",
        "I said yes to the job offer but I'm not sure now",
        "I meant to call my mom yesterday, how do I apologize?",
        "I didn't say anything at the meeting, was that bad?",
        "no, I'm good thanks",
        "no I'm not sure",
        "no, I'm fine",
        "what's the difference between python 2 and 3?",
        "is it 2024 or 2023 in the Ethiopian calendar?",
        "that's wrong",
        "no",
        "I told you about my trip, right? what should I pack?",
        "",
    ],
)
def test_a_look_alike_is_not_a_correction(text: str) -> None:
    assert is_correction(text) is False


@pytest.mark.parametrize(
    "text", ["continue", "Continue.", "keep going", "go on please", "carry on", "keep writing"]
)
def test_continue_resumes_the_last_reply(text: str) -> None:
    assert is_resume_request(text) is True
    assert works_on_last_reply(text) is True


@pytest.mark.parametrize("text", ["another one", "why", "next", "explain", "show me"])
def test_a_new_ask_is_not_a_resume(text: str) -> None:
    assert is_pure_continuation(text) is True
    assert is_resume_request(text) is False


@pytest.mark.parametrize("text", ["fix that", "fix it", "Fix this please"])
def test_fix_that_works_on_the_last_reply_without_resuming_it(text: str) -> None:
    assert works_on_last_reply(text) is True
    assert is_resume_request(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "continue the story but make the dragon a villain",
        "fix that bug in my login form: the button does nothing",
        "how do I continue a for loop in python",
    ],
)
def test_a_longer_request_is_not_about_the_last_reply(text: str) -> None:
    assert works_on_last_reply(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "explain in detail how Raft handles split votes and partitions",
        "Explain TCP congestion control in depth",
        "give me an in-depth explanation of garbage collection",
        "do a deep dive into Postgres MVCC",
        "deep dive: kubernetes networking",
        "explain it thoroughly",
        "can you explain how DNS works fully?",
        "I want a detailed explanation of photosynthesis",
        "give me a comprehensive guide to sourdough",
        "tell me more details",
        "can you elaborate?",
        "elaborate on the second point",
        "go deeper on the trade-offs",
        "tell me everything about black holes",
    ],
)
def test_a_request_for_depth_is_detected(text: str) -> None:
    assert is_detail_request(text) is True
    assert reply_length(text) == "detailed"


@pytest.mark.parametrize(
    "text",
    [
        "what are the details of the iPhone 16 launch?",
        "the devil is in the details, right?",
        "how much does car detailing cost",
        "how do I thoroughly clean an oven",
        "what is comprehensive car insurance",
        "an elaborate birthday cake recipe",
        "elaborate cake ideas for a 5 year old",
        "what is a deep dive in scuba",
        "is the moon fully visible tonight",
        "what's the full form of NASA",
        "write an email asking for more details about the invoice",
    ],
)
def test_a_detail_look_alike_keeps_the_fitted_length(text: str) -> None:
    assert is_detail_request(text) is False
    assert reply_length(text) == "balanced"


def test_a_cap_on_one_part_and_depth_on_another_is_mixed() -> None:
    text = "in one sentence what is DNS? Also explain in detail how TLS handshakes work"
    assert reply_length(text) == "mixed"
    assert reply_length("summarize the french revolution in 3 sentences") == "brief"


@pytest.mark.parametrize(
    ("text", "prior", "again"),
    [
        # "Hi" after "Hi" got a fresh greeting each time, as if the chat had just begun.
        ("Hi", [("user", "Hi"), ("assistant", "Hey bini!")], True),
        ("hey!", [("user", "hello"), ("assistant", "Hi!")], True),
        (
            "hello again",
            [("user", "hi"), ("assistant", "Hey!"), ("user", "hi"), ("assistant", "Hi!")],
            True,
        ),
        ("good morning", [("user", "hi 👋"), ("assistant", "Hey!")], True),
        # A first greeting, one after a question or a request, or a greeting with a question.
        ("Hi", [], False),
        ("hi", [("user", "what's 2+2"), ("assistant", "4")], False),
        ("hey", [("user", "hey can you help me with my essay"), ("assistant", "Sure!")], False),
        ("hi, what's the weather?", [("user", "hi"), ("assistant", "Hey!")], False),
    ],
)
def test_a_greeting_after_a_greeting_greets_again(
    text: str, prior: list[tuple[str, str]], again: bool
) -> None:
    assert (greeting_run(text, prior) >= 2) is again


@pytest.mark.parametrize(
    ("prior", "run"),
    [
        ([], 1),
        ([("user", "Hi"), ("assistant", "Hey!")], 2),
        ([("user", "hi"), ("assistant", "Hey!"), ("user", "hello"), ("assistant", "Hi again!")], 3),
        # A question in between starts the count again.
        ([("user", "hi"), ("assistant", "Hey!"), ("user", "what's 2+2"), ("assistant", "4")], 1),
    ],
)
def test_a_greeting_run_counts_the_greetings_in_a_row(
    prior: list[tuple[str, str]], run: int
) -> None:
    assert greeting_run("Hi", prior) == run
    assert greeting_run("what's up with my order?", prior) == 0


def test_the_repeated_greeting_rule_names_the_count_and_the_last_reply() -> None:
    # Told only to notice it, a model said "Hey bini! What's up?" twice in a row.
    second = repeated_greeting_hint(2, "Hey bini! 👋 What's up?")
    assert "second greeting in a row" in second
    assert '"Hey bini! 👋 What\'s up?"' in second
    assert "count them" not in second
    third = repeated_greeting_hint(3, None)
    assert "third greeting in a row" in third
    assert "That's 3 now!" in third
    assert "Your last reply" not in third
    assert "number 7 greeting" in repeated_greeting_hint(7, None)
