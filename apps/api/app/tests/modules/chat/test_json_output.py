"""JSON the user asks for: detecting the ask, the prompt hint, and checking the reply (R4.9)."""

import json
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.json_output import (
    JSON_INVALID_NOTE,
    JSON_OUTPUT_HINT,
    check_json_reply,
    check_requested_json,
    is_json_request,
    repair_json,
)
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext


@pytest.mark.parametrize(
    "text",
    [
        "give me the list of the planets as valid JSON",
        "Convert this to JSON: name Ann, age 30",
        "list three fruits in JSON",
        "Return a JSON object with name and age for Ann, 30",
        "output json only: the days of the week",
        "respond only with JSON",
        "make me a JSON array of the G7 countries",
    ],
)
def test_is_json_request_catches_asks_for_json_output(text: str) -> None:
    assert is_json_request(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "what is JSON?",
        "how are dates represented in JSON?",
        "how do I parse the json response in python",
        "write a python function that returns json",
        "write code to convert csv to json",
        "what's the difference between yaml and json",
        "my json file won't load",
        "",
        None,
    ],
)
def test_is_json_request_leaves_questions_about_json(text: str | None) -> None:
    assert is_json_request(text) is False


def test_valid_json_fences_are_left_alone() -> None:
    reply = 'Here you go:\n\n```json\n["Mercury", "Venus"]\n```\n'
    assert check_json_reply(reply) == (reply, False)


def test_a_trailing_comma_is_repaired_in_place() -> None:
    reply = 'Planets:\n\n```json\n["Mercury", "Venus",]\n```\nThat is two.'
    fixed, invalid = check_json_reply(reply)
    assert invalid is False
    body = fixed.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(body) == ["Mercury", "Venus"]
    assert fixed.startswith("Planets:") and fixed.endswith("That is two.")


@pytest.mark.parametrize(
    "body, expected",
    [
        ('{"a": 1,}', {"a": 1}),
        ("[1, 2, 3,\n]", [1, 2, 3]),
        ("```json\n[1]\n```", [1]),
        ("{“a”: 1}", {"a": 1}),
    ],
)
def test_repair_json_cheap_fixes(body: str, expected: object) -> None:
    repaired = repair_json(body)
    assert repaired is not None and json.loads(repaired) == expected


def test_repair_json_gives_up_on_real_damage() -> None:
    assert repair_json('{"a": 1, "b": ') is None
    assert repair_json("{'a': 1}") is None


def test_unrepairable_json_is_flagged() -> None:
    reply = '```json\n{"name": "Ann", "age": }\n```'
    fixed, invalid = check_json_reply(reply)
    assert invalid is True and fixed == reply


def test_a_whole_reply_of_json_is_checked_too() -> None:
    assert check_json_reply('{"a": 1,}') == ('{\n  "a": 1\n}', False)
    assert check_json_reply('{"a": ')[1] is True
    assert check_json_reply("No JSON here, sorry.") == ("No JSON here, sorry.", False)


def _state(reply: str, user_message: str) -> FinalizeState:
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="qwen-3.7-flash",
        prompt_messages=[{"role": "user", "content": user_message}],
        run_title=False,
        user_message_content=user_message,
        reserved_tokens=0,
        max_output_tokens=0,
    )
    return FinalizeState(
        deps=None,  # type: ignore[arg-type]  # the JSON pass reads no dependency
        settings=Settings(),
        ctx=ctx,
        raw=reply,
        text=reply,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )


_ASK = "give me the list of the planets as valid JSON"


def test_the_pass_notes_json_that_did_not_validate() -> None:
    state = _state('```json\n["Mercury", "Venus"\n```', _ASK)
    out = check_requested_json(state)
    assert out.endswith(JSON_INVALID_NOTE)


def test_the_pass_repairs_what_it_can_silently() -> None:
    state = _state('```json\n["Mercury", "Venus",]\n```', _ASK)
    out = check_requested_json(state)
    assert JSON_INVALID_NOTE not in out
    assert json.loads(out.split("```json\n", 1)[1].split("\n```", 1)[0]) == ["Mercury", "Venus"]


def test_the_pass_ignores_turns_that_did_not_ask_for_json() -> None:
    reply = 'An example:\n\n```json\n{"a": 1, // comment\n}\n```'
    assert check_requested_json(_state(reply, "how are comments written in JSON?")) == reply


def test_the_hint_names_the_rules_the_pass_checks() -> None:
    # The battery case format-json-planets checks the hint reaches the prompt.
    for rule in ("```json", "no trailing commas", "no comments"):
        assert rule in JSON_OUTPUT_HINT
