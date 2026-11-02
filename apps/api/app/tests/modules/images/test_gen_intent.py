"""Tests for image-generation intent detection."""

import pytest

from app.modules.images.gen_intent import extract_image_gen_prompt
from app.modules.images.gen_intent_thread import (
    could_be_image_revision,
    could_be_image_thread_followup,
    extract_image_gen_prompt_from_thread,
    extract_image_revision_prompt,
    image_gen_revision_context,
    is_image_only_assistant_content,
)
from app.services.subject_scan import (
    BIOLOGY_CAMERA_PROMPT,
    MATH_CAMERA_PROMPT,
    PHYSICS_CAMERA_PROMPT,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Create a cat pic", "cat"),
        ("create a cat image", "cat"),
        ("draw me a dog", "dog"),
        ("draw a dog", "dog"),
        ("generate image of sunset over mountains", "sunset over mountains"),
        ("Generate image: milk", "milk"),
        ("make a red sports car photo", "red sports car"),
        ("draw a mermaid", "mermaid"),
        ("create a cat", "cat"),
        ("Create cat", "cat"),
        ("Create a car from the 1950s on NW road", "car from the 1950s on NW road"),
    ],
)
def test_extract_image_gen_prompt_matches(text: str, expected: str) -> None:
    assert extract_image_gen_prompt(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "explain quantum entanglement",
        "create a todo",
        "make a list",
        "create a reminder",
        "create an image compression script",
        "draw a conclusion from this",
        "make it blue",  # revision follow-up, not "create a picture of it blue"
        "create music",
        "create a song",
        "make a playlist",
        "Make money",
        "make some money",
        "make a lot of money",
        "make dinner",
        "make sense",
        "make your own example",
        "make an example",
        "create a math problem",
        "make a question",
        "draw me an example",
        "create an image of my tasks",
        "make a picture of my todo list",
        "show me a picture of ways to be smarter",
        "create an image of tips for studying",
        "Draw a mermaid flowchart for brewing coffee.",
        "draw a mermaid flowchart of making a cup of coffee",
        "draw a right triangle with legs 3 and 4",
        "Draw a right triangle with legs 3 and 4.",
        "draw the molecule caffeine",
        "a" * 501,
        "Image",
        "pic",
        MATH_CAMERA_PROMPT,
        PHYSICS_CAMERA_PROMPT,
        BIOLOGY_CAMERA_PROMPT,
        f"{MATH_CAMERA_PROMPT}\n\nI read this as: x=2",
    ],
)
def test_extract_image_gen_prompt_rejects(text: str) -> None:
    assert extract_image_gen_prompt(text) is None


def test_extract_image_gen_prompt_from_thread_dog_then_image() -> None:
    assert extract_image_gen_prompt_from_thread("Image", ["Dog"]) == "Dog"
    assert extract_image_gen_prompt_from_thread("a picture", ["Dog"]) == "Dog"
    assert extract_image_gen_prompt_from_thread("Image", []) is None
    assert extract_image_gen_prompt_from_thread("Image", ["explain gravity"]) is None
    assert extract_image_gen_prompt_from_thread("Image", ["create a todo"]) is None
    assert extract_image_gen_prompt_from_thread("Image", ["hi"]) is None


def test_extract_image_gen_prompt_from_thread_keeps_direct_asks() -> None:
    assert extract_image_gen_prompt_from_thread("create a cat pic", ["Dog"]) == "cat"


def test_picture_of_that_car_uses_the_earlier_subject() -> None:
    prior = "Create a car from the 1950s on NW road"
    assert extract_image_gen_prompt_from_thread("Create a picture of that car", [prior]) == (
        "car from the 1950s on NW road"
    )
    assert extract_image_gen_prompt_from_thread("Create a picture of that car", []) == "that car"


def test_extract_image_gen_prompt_from_thread_confirm_after_scene() -> None:
    priors = ["Dog", "Image", "U pick"]
    assert extract_image_gen_prompt_from_thread("That works", priors) == "Dog"
    assert extract_image_gen_prompt_from_thread("I said u do it!", priors) == "Dog"
    assert extract_image_gen_prompt_from_thread("that works", ["add milk"]) is None
    assert extract_image_gen_prompt_from_thread("do it", ["draw a dog"]) == "dog"


def test_extract_image_gen_prompt_from_thread_confirm_not_stale_image_ask() -> None:
    assert extract_image_gen_prompt_from_thread("do it", ["draw a dog", "Paris"]) is None


def test_could_be_image_thread_followup() -> None:
    assert could_be_image_thread_followup("Image") is True
    assert could_be_image_thread_followup("that works") is True
    assert could_be_image_thread_followup("hi") is False
    assert could_be_image_thread_followup("make it blue") is False


def test_extract_image_revision_prompt_white_case() -> None:
    """Mirror mobile: short color follow-up after image-only reply."""
    assert (
        extract_image_revision_prompt(
            "White",
            last_assistant_is_image_only=True,
            previous_subject="black cat",
        )
        == "black cat, White"
    )
    assert (
        extract_image_revision_prompt(
            "make it blue",
            last_assistant_is_image_only=True,
            previous_subject="black cat",
        )
        == "black cat, blue"
    )


def test_extract_image_revision_prompt_rejects_praise() -> None:
    assert (
        extract_image_revision_prompt(
            "Nice car.",
            last_assistant_is_image_only=True,
            previous_subject="that car",
        )
        is None
    )
    assert (
        extract_image_revision_prompt(
            "looks good",
            last_assistant_is_image_only=True,
            previous_subject="that car",
        )
        is None
    )
    assert (
        extract_image_revision_prompt(
            "make it nicer",
            last_assistant_is_image_only=True,
            previous_subject="that car",
        )
        == "that car, nicer"
    )
    assert could_be_image_revision("Nice car.") is False


def test_extract_image_revision_prompt_rejects_thanks_and_non_image() -> None:
    assert (
        extract_image_revision_prompt(
            "thanks",
            last_assistant_is_image_only=True,
            previous_subject="black cat",
        )
        is None
    )
    assert (
        extract_image_revision_prompt(
            "hi",
            last_assistant_is_image_only=True,
            previous_subject="black cat",
        )
        is None
    )
    assert (
        extract_image_revision_prompt(
            "Hi!",
            last_assistant_is_image_only=True,
            previous_subject="black cat",
        )
        is None
    )
    assert (
        extract_image_revision_prompt(
            "White",
            last_assistant_is_image_only=False,
            previous_subject="black cat",
        )
        is None
    )


@pytest.mark.parametrize(
    "text",
    ["hi", "Hi!", "hello", "hey", "thanks", "ok", "yo"],
)
def test_could_be_image_revision_rejects_greetings(text: str) -> None:
    assert could_be_image_revision(text) is False


def test_could_be_image_revision_accepts_color_follow_up() -> None:
    assert could_be_image_revision("make it blue") is True
    assert could_be_image_revision("White") is True


@pytest.mark.parametrize(
    "text",
    ["what's 2+2", "help me think", "how are you", "explain gravity"],
)
def test_could_be_image_revision_rejects_questions_and_chat(text: str) -> None:
    assert could_be_image_revision(text) is False
    assert (
        extract_image_revision_prompt(
            text,
            last_assistant_is_image_only=True,
            previous_subject="black cat",
        )
        is None
    )


def test_image_gen_revision_context_finds_prior_subject() -> None:
    assert is_image_only_assistant_content(
        "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]"
    )
    last_only, subject = image_gen_revision_context(
        [
            {"role": "user", "content": "Generate image: black cat"},
            {
                "role": "assistant",
                "content": "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
            },
        ]
    )
    assert last_only is True
    assert subject == "black cat"


def test_image_gen_revision_context_reads_original_wording() -> None:
    last_only, subject = image_gen_revision_context(
        [
            {"role": "user", "content": "create a cat image"},
            {
                "role": "assistant",
                "content": "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
            },
        ]
    )
    assert last_only is True
    assert subject == "cat"


def test_image_gen_revision_context_skips_lookup_photos() -> None:
    last_only, subject = image_gen_revision_context(
        [
            {"role": "user", "content": "Show me a car."},
            {
                "role": "assistant",
                "content": "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
                "model": "image-search-model",
            },
        ]
    )
    assert last_only is False
    assert subject is None


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        # Live: "for my notes" drew nothing, as if the notes were what to draw.
        (
            "can you draw me a cute cartoon skeleton for my notes",
            "cute cartoon skeleton for my notes",
        ),
        ("draw a cat for my presentation", "cat for my presentation"),
        ("draw a cute owl for my class notes", "cute owl for my class notes"),
    ],
)
def test_a_drawing_for_a_purpose_is_still_a_drawing(text: str, subject: str) -> None:
    assert extract_image_gen_prompt(text) == subject


@pytest.mark.parametrize(
    "text",
    [
        # "Make" and "create" often write: the notes, plan or quiz stays the subject.
        "make a mnemonic for my notes",
        "create a summary for my notes",
        "make me a study plan for my exam",
        "make a quiz for my students",
        # "Draw up" and "draw conclusions" never draw.
        "draw up notes for my meeting",
        "draw conclusions for my report",
        "draw me a plan for my week",
    ],
)
def test_written_work_for_a_purpose_is_not_a_drawing(text: str) -> None:
    assert extract_image_gen_prompt(text) is None
