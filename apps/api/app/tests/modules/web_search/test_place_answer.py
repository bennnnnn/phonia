"""A place named after "I don't have your location yet" answers the earlier question there."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.web_search import needs_web_search, turn_query
from app.modules.web_search.geo_intent import format_location_not_set_answer
from app.modules.web_search.place_answer import given_place, question_in_given_place

_ASK = format_location_not_set_answer()
# The old wording, still in chats written before it changed.
_OLD_ASK = (
    "I don't have your location yet, so I can't answer nearby or distance questions "
    "accurately.\n\nTurn on **Location** in **Settings** (or allow location when "
    "prompted), then ask again."
)


@pytest.mark.parametrize(
    ("text", "place"),
    [
        ("im in indianapolis", "indianapolis"),
        ("I’m in Indianapolis", "Indianapolis"),
        ("Indianapolis", "Indianapolis"),
        ("in Addis Ababa", "Addis Ababa"),
        ("we're in Paris, France right now", "Paris, France"),
        ("I live in New York City", "New York City"),
        # Not a place: a yes, a question, the settings, a pronoun, home.
        ("yes please", None),
        ("I’m in yes please", None),
        ("ok", None),
        ("how do I turn it on?", None),
        ("turn it on", None),
        ("Settings", None),
        ("my house", None),
        ("home", None),
        ("nvm", None),
        ("", None),
    ],
)
def test_given_place(text: str, place: str | None) -> None:
    assert given_place(text) == place


@pytest.mark.parametrize("ask", [_ASK, _OLD_ASK])
def test_a_place_after_the_location_ask_is_the_question_asked_there(ask: str) -> None:
    # Live: "I'm in indianapolis" searched nothing; the model offered, then refused.
    asked = question_in_given_place("I’m in indianapolis", "Is it gonna rain tonight?", ask)
    assert asked == "Is it gonna rain tonight in indianapolis"
    # "Near me" becomes the place.
    assert (
        question_in_given_place("Indianapolis", "best coffee near me", ask)
        == "best coffee in Indianapolis"
    )


def test_a_place_after_any_other_reply_is_just_a_message() -> None:
    assert question_in_given_place("Indianapolis", "is it gonna rain tonight", "Sure!") is None
    assert question_in_given_place("Indianapolis", None, _ASK) is None


def test_the_gate_searches_the_answered_question() -> None:
    assert needs_web_search(
        "im in indianapolis",
        prior_user_messages=["is it gonna rain tonight"],
        prior_assistant=_ASK,
    )
    # Not after the ask: telling where you are is not a search.
    assert not needs_web_search(
        "im in indianapolis",
        prior_user_messages=["what should i cook"],
        prior_assistant="Pasta is quick.",
    )


@pytest.mark.asyncio
async def test_the_search_sends_the_question_in_that_place() -> None:
    messages = [
        {"role": "user", "content": "is it gonna rain tonight"},
        {"role": "assistant", "content": _ASK},
        {"role": "user", "content": "im in indianapolis"},
    ]
    queries = await turn_query.search_queries_for_turn(Settings(), "im in indianapolis", messages)
    assert queries == ["is it gonna rain tonight in indianapolis"]
