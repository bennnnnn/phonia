"""The cheap strong-lane signals: each one, and the everyday messages that look like it."""

import time

import pytest

from app.modules.chat.model_routing.signals import (
    has_structured_data,
    is_code_review,
    is_hard_reasoning,
    needs_strong_model,
)

_JSON_RECORDS = (
    'find the duplicate ids: [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, '
    '{"id": 1, "name": "c"}]'
)


@pytest.mark.parametrize(
    "content",
    [
        "plan a zero-downtime migration of a monolith Postgres schema to sharded tables",
        "All cats are mammals. Some mammals are black. Does it follow that some cats are "
        "black? Explain carefully.",
        "explain carefully why the sum of two odd numbers is even",
        "Here's a logic puzzle: three boxes are all mislabeled, which do you open?",
        "knights and knaves: A says B is a knave. B says both of us are knights.",
        "how would you design the backend and caching for a chat app with high availability",
        "migrate our mysql database to postgres with replication",
        "Seat 6 people at a round table such that no two siblings sit together, Alice must "
        "sit next to Bob, and each couple sits apart",
    ],
)
def test_is_hard_reasoning_catches_hard_asks(content: str) -> None:
    assert is_hard_reasoning(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "plan a trip to Rome",
        "plan my week",
        "drive carefully",
        "listen carefully to me",
        "handle the vase carefully please",
        "all my friends are busy and some days are hard",
        "what is a database?",
        "can you explain what a postgres database is?",
        "bird migration patterns",
        "design a logo for my bakery",
        "I have no downtime this week, plan my schedule",
        "plan seating for 3 tables and the servers at my restaurant",
        "I must buy milk, at least 2 liters, without sugar",
        "tell me a riddle",
        "Give me a 30-day workout plan",
        "Create a 12-week business plan",
        "I studied Python for 70 days and now plan to apply for jobs",
        "how do I migrate my photos to a new phone",
        "explain quantum computing",
        "write a tweet announcing that we finished migrating our backend to postgres, zero "
        "downtime",
        "write a blog post about our zero-downtime migration to postgres",
    ],
)
def test_is_hard_reasoning_leaves_everyday_look_alikes(content: str) -> None:
    assert is_hard_reasoning(content) is False


@pytest.mark.parametrize(
    "content",
    [
        "can you review my function that reverses a linked list, it keeps looping forever",
        "why does my loop never end",
        "why is my function returning None",
        "my python script crashes on startup",
        "I get a syntax error on line 3",
        "code review please: it works but feels slow",
        "look over this function for me",
        "write a python function to reverse a string",
        "implement a recursive function for fibonacci",
        "write me a bash script that backs up my photos",
    ],
)
def test_is_code_review_catches_unfenced_code_work(content: str) -> None:
    assert is_code_review(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "review my resume",
        "review my essay for class",
        "can you review my cover letter",
        "review my class notes",
        "review my query letter to an agent",
        "why does my cat keep scratching",
        "my promo code doesn't work",
        "my zip code is wrong on the form",
        "the program at school is stuck",
        "why does my back hurt",
        "loop me in on the plan",
        "why is my app crashing",
        "why does my bread method not work",
        "write a script for my youtube video",
        "create a class schedule",
        "write me a poem about functions",
        "write the go program for the conference",
    ],
)
def test_is_code_review_leaves_everyday_look_alikes(content: str) -> None:
    assert is_code_review(content) is False


@pytest.mark.parametrize(
    "content",
    [
        _JSON_RECORDS,
        '{"name": "Ann", "age": 30, "city": "Nairobi"} what is wrong with this record?',
        "id,name,score\n1,ann,90\n2,bob,85\n3,cat,77\nwho scored highest?",
        "date,amount\n2026-01-01,40\n2026-01-02,55\n2026-01-03,40\nsum these",
        "name\tteam\tgoals\nAna\tred\t3\nBen\tblue\t1\nCy\tred\t2",
    ],
)
def test_has_structured_data_catches_short_pasted_data(content: str) -> None:
    assert len(content) < 800
    assert has_structured_data(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "my scores were [90, 85, 77] is that good?",
        "Roses are red,\nViolets are blue,\nSugar is sweet,\nAnd so are you.",
        "eggs, milk\nbread, butter\njam, tea",
        "I said [hi] to her",
        'give me the planets as JSON like [{"name": "Mercury", "order": 1}]',
        "Dear John,\nThanks, see you soon,\nBest, Ann",
        # A matrix is maths, not records.
        "determinant of [[1,2,3],[0,1,4],[5,6,0]]",
    ],
)
def test_has_structured_data_leaves_prose_with_brackets_or_commas(content: str) -> None:
    assert has_structured_data(content) is False


def test_needs_strong_model_is_any_signal() -> None:
    assert needs_strong_model(_JSON_RECORDS)
    assert needs_strong_model("why does my loop never end")
    assert needs_strong_model("explain carefully why 0.999... equals 1")
    assert not needs_strong_model("what's for dinner tonight")


@pytest.mark.wall_clock
def test_signals_stay_linear_on_adversarial_input() -> None:
    """Routing reads every message; a long run of near-matches must stay fast."""
    nasty = "all a is " * 2_000 + "carefully " * 2_000 + "[{" * 2_000 + ",\n" * 2_000
    started = time.perf_counter()
    needs_strong_model(nasty)
    assert time.perf_counter() - started < 2.0
