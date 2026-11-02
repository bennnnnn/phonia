""" "What is the president?" in a chat about Ethiopia got a made-up president.

Who holds an office is a live fact, so the ask searches; a follow-up that names
no place searches for the chat's subject.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.web_search import turn_query
from app.modules.web_search.detection import needs_web_search, web_search_fast_yes
from app.modules.web_search.officeholder import asks_who_holds_office, office_without_place


@pytest.mark.parametrize(
    "text",
    [
        "who is the president of ethiopia",
        "who is the prime minister of ethiopia",
        "who is the ceo of tesla",
        "who is the current president of ethiopia",
        "who's the mayor of Nairobi right now",
        "What is the president?",
        "and who is the king?",
    ],
)
def test_who_holds_an_office_searches(text: str) -> None:
    assert asks_who_holds_office(text)
    assert web_search_fast_yes(text)
    assert needs_web_search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the president of my club asked me to give a speech",
        "explain what a prime minister does",
        "write a speech for a CEO",
        "what is a president",
        "who was the first president of the US",
        "who is the president of my club",
    ],
)
def test_an_office_word_alone_is_not_a_lookup(text: str) -> None:
    assert not asks_who_holds_office(text)


def test_only_a_placeless_ask_reads_the_chat() -> None:
    assert office_without_place("What is the president?")
    assert not office_without_place("who is the president of ethiopia")


_ETHIOPIA_CHAT = [
    {"role": "user", "content": "tell me about the war in ethiopia"},
    {"role": "assistant", "content": "The Tigray war began in November 2020."},
    {"role": "user", "content": "What is the president?"},
]


@pytest.mark.asyncio
async def test_placeless_office_ask_searches_the_chat_subject() -> None:
    resolve = AsyncMock(return_value="president of Ethiopia")
    with patch.object(turn_query, "resolve_reference", resolve):
        queries = await turn_query.search_queries_for_turn(
            Settings(), "What is the president?", _ETHIOPIA_CHAT
        )
    assert queries == ["president of Ethiopia"]
    awaited: Any = resolve.await_args
    assert awaited is not None and awaited.kwargs["kind"] == "search"


@pytest.mark.asyncio
async def test_placeless_office_ask_falls_back_to_the_last_topic() -> None:
    with patch.object(turn_query, "resolve_reference", AsyncMock(return_value=None)):
        queries = await turn_query.search_queries_for_turn(
            Settings(), "What is the president?", _ETHIOPIA_CHAT
        )
    assert queries == ["president tell me about the war in ethiopia"]
