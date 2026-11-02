"""Tests for app.modules.images.lookup_intent."""

import pytest

from app.modules.images.gen_intent import extract_image_gen_prompt
from app.modules.images.lookup_intent import extract_image_lookup_query


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Show me ear", "ear"),
        ("show me an ear", "ear"),
        ("show me a golden retriever", "golden retriever"),
        ("Show me the Eiffel Tower", "Eiffel Tower"),
        ("show me a picture of an ear", "ear"),
        ("show me a photo of a shark", "shark"),
        ("show me an image of Mount Everest", "Mount Everest"),
        ("let me see an ear", "ear"),
        ("let me see a golden retriever", "golden retriever"),
        ("what does an ear look like", "ear"),
        ("what does a golden retriever look like", "golden retriever"),
        ("What does a golden retriever look like?", "golden retriever"),
        ("what do octopuses look like", "octopuses"),
        # A feature word about something to see is still a photo.
        ("show me the roots of a mangrove tree", "roots of a mangrove tree"),
        # A photo asked for as a question (2026-10-24: "do you have a picture of him?"
        # after "who was Charles?" got "search online").
        ("do you have a picture of him?", "him"),
        ("do you have a photo of Jacques Charles?", "Jacques Charles"),
        ("you got a photo of a gelada?", "gelada"),
        ("have you got any pics of the Titanic wreck?", "Titanic wreck"),
        # Whether one exists is the answer's to say; only someone named earlier is looked up.
        ("is there a picture of her?", "her"),
        ("any pics of them?", "them"),
    ],
)
def test_extracts_lookup_subject(text: str, expected: str) -> None:
    assert extract_image_lookup_query(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "show me my todos",
        "show me the code",
        # The question form needs "picture of" and a subject that is no one's own.
        "do you have a photo editing app you like?",
        "is there a picture limit for uploads?",
        "do you have a picture of your family?",
        "do you have a picture of my receipt?",
        "do you have pictures?",
        "any photos?",
        "is there a picture of how to tie a tie?",
        "are there pictures of Muhammad allowed in Islam?",
        "is there a photo of Mozart?",
        "any photo of a person counts as personal data under GDPR?",
        # News, not a request.
        "got a picture of the northern lights last night!",
        # The user, Recall, the user's own files, code.
        "do you have a picture of me?",
        "is there a picture of you?",
        "do you have a photo of the receipt I uploaded?",
        "show me a photo of me",
        "do you have an image of the error?",
        "show me an example",
        "show me how to solve this",
        "show me a summary of this chapter",
        "show me my reminders",
        "show me the graph",
        "show me a flowchart",
        "show me the steps",
        "Show me THE STOPS OF BECOMING SMART",
        "show me the stops of becoming smart",
        "show me the steps of becoming smart",
        "show me ways to be smarter",
        "show me five tips, please",
        "show me ways, please",
        "show me the answer",
        "show me the equation",
        "Show long division: 1,572 ÷ 12",
        "show multiplication 23 × 14",
        "show 503 - 278",
        "show x + 3 = 9",
        "let me see the fraction 3/4",
        "show me the derivative",
        "let me see my notes",
        "what does my code look like",
        "what does the schedule look like",
        "what is a fraction",
        "what's the capital of France",
        "",
        "   ",
        "draw me a cat",
        "create an image of a sunset",
        "Show the structure of carbon dioxide.",
        "show the structure of carbon dioxide",
        # A free-body diagram the app draws, not a photo.
        "show the forces acting on a hanging mass",
        "show me a free-body diagram of a box on a ramp",
        "show me a right triangle",
        # A feature of the graph on screen: maths the app draws, not a photo.
        "show the vertex",
        "show the intercepts",
        "show me the roots",
        "show me the asymptotes",
        "show the slope",
        "show me the axis of symmetry",
        "show me the maximum and minimum",
        "show me the x-intercepts of the parabola",
        "show me the turning points of the graph",
    ],
)
def test_rejects_non_lookup_or_non_image_subjects(text: str) -> None:
    assert extract_image_lookup_query(text) is None


def test_rejects_overly_long_message() -> None:
    assert extract_image_lookup_query("show me " + "a" * 300) is None


def test_rejects_overly_long_subject() -> None:
    assert (
        extract_image_lookup_query(
            "show me a very long winded rambling detailed description of a thing"
        )
        is None
    )


def test_disjoint_from_generation_verbs() -> None:
    """Lookup and generation must never both claim the same input."""
    lookup_only = ["show me an ear", "let me see a shark", "what does a cat look like"]
    for text in lookup_only:
        assert extract_image_lookup_query(text) is not None
        assert extract_image_gen_prompt(text) is None

    generation_only = ["draw me a cat", "create an image of a sunset", "Create a cat pic"]
    for text in generation_only:
        assert extract_image_gen_prompt(text) is not None
        assert extract_image_lookup_query(text) is None


def test_howto_picture_phrase_is_not_lookup_or_generation() -> None:
    """Denied lookup how-to must not fall through to image generation."""
    text = "show me a picture of ways to be smarter"
    assert extract_image_lookup_query(text) is None
    assert extract_image_gen_prompt(text) is None
