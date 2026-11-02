"""Explicit search requests: "do a search", typos, and requests that name a topic."""

from __future__ import annotations

import pytest

from app.modules.web_search.command import asks_to_search, search_command
from app.modules.web_search.detection import needs_web_search
from app.modules.web_search.search_word import is_search_word
from app.modules.web_search.subject import resolve_search_subject

_NAME_CHAT = ["My name is bini", "What is its meaning", "So my name is binary?", "Wrong"]


@pytest.mark.parametrize(
    "text",
    [
        "Do a seearch",
        "Do a search",
        "can you do a search",
        "do an online search",
        "do a web search",
        "search",
        "search it",
        "search it up",
        "search for it",
        "search online",
        "search the internet",
        "search the web",
        "can you search it?",
        "please search",
        "serach it",
        "searh it",
        "seach for it",
        "try searching",
        "try a search",
        "google it",
        "look it up",
        "can you look it up online",
        "look online",
        "check online",
        "check the internet",
        "find it online",
        "verify that online",
        "fact check that claim",
        "use web search",
        "browse the web",
        "search for that name",
    ],
)
def test_search_command_without_a_topic_points_back(text: str) -> None:
    command = search_command(text)
    assert command is not None
    assert command.subject is None


@pytest.mark.parametrize(
    "text, subject",
    [
        ("search for the meaning of bini", "the meaning of bini"),
        ("search bini meaning", "bini meaning"),
        ("search up bini", "bini"),
        ("do a quick search on bini", "bini"),
        ("do a search on the web for bini", "bini"),
        ("search the web for tesla stock price", "tesla stock price"),
        ("search online for bini meaning", "bini meaning"),
        ("google the meaning of bini", "the meaning of bini"),
        ("look up the meaning of bini", "the meaning of bini"),
        ("can you search for flights to Paris next week", "flights to Paris next week"),
    ],
)
def test_search_command_reads_the_topic(text: str, subject: str) -> None:
    command = search_command(text)
    assert command is not None
    assert command.subject == subject


@pytest.mark.parametrize(
    "text",
    [
        "search engine optimization tips",
        "search algorithms in python",
        "what is a search engine",
        "search and replace in vim",
        "search my email for the receipt",
        "I searched everywhere for my keys",
        "starch it",
        "check it",
        "check my answer",
        "find a restaurant",
        "look at this",
        "look",
        "online",
    ],
)
def test_search_command_leaves_other_messages_alone(text: str) -> None:
    assert search_command(text) is None


@pytest.mark.parametrize(
    "word, expected",
    [
        ("search", True),
        ("Seearch", True),
        ("serach", True),
        ("searh", True),
        ("seach", True),
        ("searching", True),
        ("starch", False),
        ("sear", False),
        ("research", False),
    ],
)
def test_is_search_word_accepts_one_typo(word: str, expected: bool) -> None:
    assert is_search_word(word) is expected


@pytest.mark.parametrize("text", ["Do a seearch", "search online", "check online", "google it"])
def test_bare_search_request_searches_after_a_conversation(text: str) -> None:
    assert needs_web_search(text, prior_user_messages=_NAME_CHAT) is True


def test_search_request_with_a_topic_searches_without_history() -> None:
    assert needs_web_search("search for the meaning of bini") is True


def test_subject_fallback_skips_one_word_reactions() -> None:
    # Without the resolver, "Wrong" before "do a search" is not a query.
    assert (
        resolve_search_subject("Do a seearch", prior_user_messages=_NAME_CHAT)
        == "So my name is binary?"
    )


def test_subject_is_the_named_topic() -> None:
    assert (
        resolve_search_subject("search for the meaning of bini", prior_user_messages=_NAME_CHAT)
        == "the meaning of bini"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Can\u2019t you look it up? You looked up the weather",
        "can't you look it up",
        "cant u look it up",
        "couldn't you google it",
        "look it up please. thanks",
    ],
)
def test_a_sentence_that_asks_to_search_is_a_search(text: str) -> None:
    """Live (2026-10-25): "Can't you look it up?" was read as a question about the assistant."""
    assert asks_to_search(text)
    assert needs_web_search(text, prior_user_messages=["did the bears win today"])


@pytest.mark.parametrize(
    "text",
    [
        "I told my students to look it up. They didn't.",
        "can you look after my cat",
        "you looked it up yesterday, thanks",
        "look up to your parents",
    ],
)
def test_a_mention_of_looking_up_is_no_search(text: str) -> None:
    assert not asks_to_search(text)
    assert not needs_web_search(text)
