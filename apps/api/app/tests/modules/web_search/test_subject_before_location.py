"""Homework is its subject's question before it is one about the user's place: "A ball is
dropped from a height of 20 m. How long does it take to reach the ground?" was answered "I
don't have your location yet" (2026-11-01). The turn's reading, read in the pool, names the
message's subject; every reader of the user's place defers to it, solved or not
(``turn_reading.turn.is_homework``), unless the line says it is about where the user is ("near me",
"near here", "in my area", "from my location"). A request beside the homework that asks about
a place or the weather on its own words keeps its reader.
"""

from __future__ import annotations

import contextvars

import pytest

from app.core.config import Settings
from app.core.readings import begin_turn
from app.modules.chat.turn_prep.reading import ask_turn_readings, read_turn
from app.modules.turn_reading.turn import TurnReading, is_homework
from app.modules.web_search.detection import web_search_fast_yes
from app.modules.web_search.geo_intent import (
    is_distance_query,
    is_geo_query,
    is_places_list_query,
)
from app.modules.web_search.weather import is_weather_request
from app.services.text_normalize import collapse_ws

_SETTINGS = Settings.model_validate({})


def _read_as_turn(text: str) -> TurnReading:
    """``text`` read as the turn's message, as the pool reads it."""
    begin_turn()
    ask_turn_readings(
        text,
        prior_user=None,
        prior_model=None,
        lesson_active=False,
        has_image_attachment=False,
        settings=_SETTINGS,
    )
    return read_turn(text, _SETTINGS, has_image_attachment=False)


def _in_turn(text: str) -> tuple[TurnReading, bool, bool, bool]:
    def run() -> tuple[TurnReading, bool, bool, bool]:
        reading = _read_as_turn(text)
        return (
            reading,
            is_geo_query(text),
            is_geo_query(collapse_ws(text)),
            is_distance_query(text),
        )

    return contextvars.copy_context().run(run)


@pytest.mark.parametrize(
    "text",
    [
        "A ball is dropped from a height of 20 m. How long does it take to reach the ground?",
        "A stone falls from the top of a cliff 45 m high. How long does it take to reach the bottom?",
        "A coin is dropped from a height of 1.8 m. How long does it take to reach the floor?",
        "A rock is dropped from a bridge 30 m above the river. How long does it take to reach "
        "the water?",
        "If a ball is dropped from 10 m, how long does it take to get to the ground?",
        "A stone is dropped down a well and hits the water after 2 s. How far down is the water?",
        # Homework physics claims and cannot solve is still no question about a place.
        "A ball rolls off a table 1.2 m high. How long does it take to reach the floor?",
        "A block slides down a frictionless slope 10 m long inclined at 30 degrees. How long "
        "does it take to reach the bottom of the slope?",
        "The height of a ball is h = 80 - 5t^2. How long does it take to reach the ground?",
    ],
)
def test_homework_asks_nothing_about_the_users_place(text: str) -> None:
    # Without the turn's reading the place readers claim it, as they did.
    assert is_geo_query(text)

    reading, geo, geo_collapsed, distance = _in_turn(text)

    assert reading.subject is not None
    assert not geo and not geo_collapsed and not distance


@pytest.mark.parametrize(
    "text",
    [
        "How long does it take to reach the airport?",
        "how long to get to the beach?",
        "How far is the nearest hospital?",
        "How long does it take to reach the top of the nearest mountain?",
        "What's the weather like here today?",
        "coffee shops near me",
        "how hot is it here",
        "how far is the airport from me",
        "What's the temperature in my area?",
    ],
)
def test_a_real_location_ask_still_asks_for_the_place(text: str) -> None:
    reading, geo, geo_collapsed, _ = _in_turn(text)

    assert reading.subject is None
    assert geo and geo_collapsed


@pytest.mark.parametrize(
    ("text", "geo"),
    [
        # A subject's line that says it is about where the user is keeps the place.
        ("How long does it take to drive 10 km to the airport from my location?", True),
        # Exercises say "from here" and "here is": no cue.
        ("I walk 5 km from here at 1.5 m/s. How long does it take to reach the lake?", False),
        ("Here is my homework: a ball is dropped from 5 m. How long to reach the ground?", False),
        ("Here, a ball is dropped from 20 m. How long does it take to reach the ground?", False),
        ("Question here: a stone falls from a 45 m cliff. How long to reach the bottom?", False),
        ("Okay here goes: a ball is dropped from 20 m. How long to reach the ground?", False),
        (
            "A block slides from rest down a frictionless slope 10 m long at 30 degrees. How long "
            "does it take to reach the bottom here?",
            False,
        ),
    ],
)
def test_only_a_cue_about_the_user_outweighs_a_subject(text: str, geo: bool) -> None:
    reading, geo_now, _, _ = _in_turn(text)

    assert reading.subject is not None
    assert geo_now is geo


def test_a_search_around_the_user_outweighs_a_problem() -> None:
    text = "Find coffee shops near me within 2 km, max 5 km"

    def run() -> tuple[bool, bool]:
        _read_as_turn(text)
        return is_geo_query(text), is_places_list_query(text)

    assert contextvars.copy_context().run(run) == (True, True)


def test_only_the_turns_own_message_is_known() -> None:
    problem = "A ball is dropped from a height of 20 m. How long does it take to reach the ground?"

    def run() -> tuple[bool, bool, bool]:
        _read_as_turn(problem)
        return (
            is_homework(problem),
            is_homework(f"  {problem}\n"),
            is_homework("How long does it take to reach the airport?"),
        )

    assert contextvars.copy_context().run(run) == (True, True, False)
    # Outside a turn nothing is read.
    assert contextvars.Context().run(is_homework, problem) is False


@pytest.mark.parametrize(
    "text",
    [
        # The plan splits these: the weather part keeps its search.
        "What's the weather like today? Also solve 2x + 3 = 7",
        "What's the weather today and how fast does a ball fall from 20 m?",
        # The plan reads one request: its sentences are judged one by one.
        "Will it rain tomorrow? And what's 15% of 80?",
    ],
)
def test_a_weather_ask_beside_homework_keeps_its_search(text: str) -> None:
    def run() -> tuple[str | None, bool, bool, bool]:
        reading = _read_as_turn(text)
        return (
            reading.subject,
            is_weather_request(text),
            is_geo_query(text),
            web_search_fast_yes(text),
        )

    subject, weather, geo, searches = contextvars.copy_context().run(run)

    assert subject is not None
    assert weather and geo and searches


@pytest.mark.parametrize(
    "text",
    [
        # A place ask beside numbers physics claims: still the user's place.
        "How far is the nearest gas station? My car does 30 mpg",
        "How far is the nearest pharmacy? Also, a ball is dropped from 20 m, how long to reach "
        "the ground?",
    ],
)
def test_a_place_ask_beside_homework_keeps_the_place(text: str) -> None:
    reading, geo, geo_collapsed, _ = _in_turn(text)

    assert reading.subject == "physics"
    assert geo and geo_collapsed


def test_a_second_question_of_the_same_problem_is_still_homework() -> None:
    text = (
        "A ball is dropped from 20 m. What is its speed after 1 s? How long does it take to "
        "reach the ground?"
    )
    _, geo, geo_collapsed, distance = _in_turn(text)

    assert not geo and not geo_collapsed and not distance
