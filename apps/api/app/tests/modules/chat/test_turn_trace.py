"""A turn's trace line: its decisions, by name and count, and never anyone's words."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.log_context import bound_log_ids
from app.core.logging import _JsonFormatter
from app.core.request_id import client_request_id
from app.models import model_catalog
from app.modules.chat import stream_pipeline, turn_trace
from app.modules.chat.finalize_passes import FALL_BACK, FinalizePass, FinalizeState, OnError
from app.modules.chat.finalize_passes import _run_pass as run_pass
from app.modules.chat.model_routing.route import resolve_alias_in_pool
from app.modules.chat.prompt_format import HINT_RULES, PromptRule, render_rules
from app.modules.chat.prompt_sections import (
    CONTEXT_SECTIONS,
    NEARBY_CONTRACTS,
    STABLE_SECTIONS,
    TURN_SECTIONS,
)
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_trace import (
    begin_turn_trace,
    current_turn_trace,
    emit_turn_trace,
    note_lightweight,
    note_pass,
    note_plan,
    note_prompt_rule,
    note_route,
    note_subject,
    note_teaching,
    note_tool,
    plain_record,
)

_SECRET = "my bank password is hunter2 and I live at 12 Elm St"
_ALLOWED_KEYS = {
    "kind",
    "path",
    "transport",
    "outcome",
    "error",
    "route",
    "plan",
    "plan_reason",
    "lightweight_reason",
    "teaching_reason",
    "subject_reason",
    "prompt_rules",
    "tools",
    "passes_changed",
    "passes_failed",
    "total_ms",
    "resolved_model",
    "fallback_used",
    "model",
    "fallback_models",
    "thinking",
    "lightweight",
    "rich_context",
    "instant",
    "solver",
    "money",
    "search_hits",
    "local_places",
    "recalled",
    "summarized",
    "prior_messages",
    "settings_card",
    "answer_photos",
    "reply_tools",
    "prep_ms",
    "first_token_ms",
}


@pytest.fixture(autouse=True)
def _no_trace_between_tests() -> Iterator[None]:
    token = turn_trace._TRACE.set(None)
    yield
    turn_trace._TRACE.reset(token)


def _ctx(**fields: Any) -> StreamContext:
    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[
            {"role": "system", "content": f"Memory: {_SECRET}"},
            {"role": "user", "content": _SECRET},
        ],
        run_title=False,
        user_message_content=_SECRET,
        reserved_tokens=0,
        max_output_tokens=0,
        memory_hints=[_SECRET],
        **fields,
    )


def _emitted(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    records = [record for record in caplog.records if record.getMessage().startswith("turn_trace")]
    assert len(records) == 1
    return records[0]


def test_a_turn_line_holds_its_decisions_and_none_of_its_words(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=turn_trace.__name__)
    begin_turn_trace("new")
    note_route("auto.math")
    note_plan(["ask", "solve"], "several_requests")
    note_lightweight("answers_offer")
    note_teaching("procedure")
    note_subject("chemistry_closed")
    note_prompt_rule("hints.format_pack")
    note_tool("web_search")
    note_tool("web_search")
    note_pass("prose", _SECRET, _SECRET + "!")
    outcome = TurnOutcome(resolved_model="free-chat", final_content=_SECRET)

    with bound_log_ids(transport="ws"):
        emit_turn_trace(_ctx(unverified_subject=_SECRET), outcome=outcome)

    record = _emitted(caplog)
    trace: dict[str, Any] = record.turn_trace  # type: ignore[attr-defined]
    assert set(trace) <= _ALLOWED_KEYS
    assert plain_record(trace)
    assert "hunter2" not in record.getMessage()
    assert json.loads(record.getMessage().removeprefix("turn_trace ")) == trace
    assert trace["route"] == "auto.math"
    assert trace["plan"] == ["ask", "solve"]
    assert trace["plan_reason"] == "several_requests"
    assert trace["lightweight_reason"] == "answers_offer"
    assert trace["teaching_reason"] == "procedure"
    assert trace["subject_reason"] == "chemistry_closed"
    assert trace["tools"] == {"web_search": 2}
    assert trace["passes_changed"] == [["prose", 1]]
    assert trace["transport"] == "ws"
    assert trace["outcome"] == "complete"
    assert trace["solver"]["unverified_subject"] is None


@pytest.mark.parametrize(
    "note, value",
    [
        (lambda: note_route("route me to 'smart' please"), lambda trace: trace.route),
        (lambda: note_prompt_rule("hints.1 my secret"), lambda trace: trace.prompt_rules),
        (lambda: note_plan(["ask", "I owe $200"]), lambda trace: trace.plan),
        (lambda: note_lightweight("hi there"), lambda trace: trace.lightweight_reason),
    ],
)
def test_a_string_that_is_no_identifier_never_enters_the_trace(note: Any, value: Any) -> None:
    trace = begin_turn_trace("new")
    note()
    assert value(trace) in (None, [], ("ask",))


def test_a_tool_with_an_odd_name_is_counted_as_unknown() -> None:
    trace = begin_turn_trace("new")
    note_tool("rm -rf /; cat secrets")
    assert dict(trace.tools) == {"unknown": 1}


def test_notes_outside_a_turn_go_nowhere() -> None:
    note_route("auto.math")
    note_tool("web_search")
    assert current_turn_trace() is None


def test_the_line_is_logged_once_and_later_notes_are_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=turn_trace.__name__)
    trace = begin_turn_trace("regenerate")
    emit_turn_trace(None, outcome=None, path="intercept")
    note_tool("web_search")
    emit_turn_trace(None, outcome=None)
    record = _emitted(caplog)
    assert record.turn_trace["path"] == "intercept"  # type: ignore[attr-defined]
    assert record.turn_trace["kind"] == "regenerate"  # type: ignore[attr-defined]
    assert not trace.tools


def test_a_broken_trace_never_breaks_the_turn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("bug")

    monkeypatch.setattr(turn_trace, "turn_record", broken)
    begin_turn_trace("new")
    emit_turn_trace(_ctx(), outcome=None)
    assert "turn trace could not be built" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure, outcome, error",
    [
        (RuntimeError("boom"), "error", "RuntimeError"),
        (asyncio.CancelledError(), "cancelled", "CancelledError"),
        (None, "user_stop", None),
    ],
)
async def test_a_closing_turn_says_how_it_ended(
    caplog: pytest.LogCaptureFixture,
    failure: BaseException | None,
    outcome: str,
    error: str | None,
) -> None:
    caplog.set_level(logging.INFO, logger=turn_trace.__name__)
    begin_turn_trace("new")
    await stream_pipeline._close_turn(_ctx(), TurnOutcome(completion="user_stop"), failure)
    trace = _emitted(caplog).turn_trace  # type: ignore[attr-defined]
    assert (trace["outcome"], trace["error"]) == (outcome, error)


def test_each_prompt_rule_that_adds_text_is_named_by_its_table() -> None:
    trace = begin_turn_trace("new")
    rules: tuple[PromptRule[object], ...] = (
        PromptRule(lambda _t: True, lambda _t: ["a rule's text"], name="first"),
        PromptRule(lambda _t: True, lambda _t: [], name="empty"),
        PromptRule(lambda _t: False, lambda _t: ["never"], name="skipped"),
        PromptRule(lambda _t: True, lambda _t: ("text",), name="last"),
    )
    assert render_rules(rules, object(), table="hints") == ["a rule's text", "text"]
    assert trace.prompt_rules == ["hints.first", "hints.last"]


@pytest.mark.parametrize(
    "rules", [HINT_RULES, STABLE_SECTIONS, TURN_SECTIONS, CONTEXT_SECTIONS, NEARBY_CONTRACTS]
)
def test_every_prompt_rule_has_a_name_of_its_own_in_its_table(
    rules: tuple[PromptRule[Any], ...],
) -> None:
    """The name, not the place: a rule added above another leaves the other's name.
    (The text and order the rules render are pinned byte for byte by test_prompt_golden.)"""
    names = [rule.name for rule in rules]
    assert len(set(names)) == len(names)
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in names)


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/x?q=1",
        "evil.example/collect",
        "me@example.com",
        "two words",
        "auto:math",
        "line\nbreak",
        "x" * 65,
        "",
    ],
)
def test_no_url_address_sentence_or_long_string_is_an_identifier(value: str) -> None:
    trace = begin_turn_trace("new")
    note_route(value)
    note_tool(value)
    assert trace.route is None
    assert dict(trace.tools) == {"unknown": 1}


def _state(text: str) -> FinalizeState:
    return FinalizeState(
        deps=MagicMock(),
        settings=Settings(),
        ctx=_ctx(),
        raw=text,
        text=text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[text],
        should_cancel=None,
    )


@pytest.mark.asyncio
async def test_a_finalize_pass_is_traced_when_it_changes_the_text_or_fails() -> None:
    trace = begin_turn_trace("new")
    state = _state("reply")
    await run_pass(FinalizePass("same", lambda s: s.text, FALL_BACK), state)
    state.text = await run_pass(FinalizePass("grow", lambda s: s.text + "!!", FALL_BACK), state)

    def fail(_state: FinalizeState) -> str:
        raise ValueError("bad")

    await run_pass(FinalizePass("soft", fail, OnError(log_as="soft")), state)
    assert trace.passes_changed == [("grow", 2)]
    assert trace.passes_failed == ["soft"]


@pytest.mark.parametrize(
    "alias, content, pool, route",
    [
        ("auto", "Teach me fractions", None, "auto.teaching"),
        ("fast", "hi", None, "mode_fast"),
        ("free-chat", "hi", ["free-chat"], "picked"),
    ],
)
def test_routing_says_why_it_chose_the_lane(
    alias: str, content: str, pool: list[str] | None, route: str
) -> None:
    trace = begin_turn_trace("new")
    pool = pool or [model_catalog.auto_fast_alias(), model_catalog.auto_smart_alias()]
    resolve_alias_in_pool(alias, content, pool, Settings())
    assert trace.route == route


def test_the_json_log_carries_the_trace_as_fields() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "turn_trace %s", ("{}",), None)
    record.turn_trace = {"kind": "new", "tools": {"web_search": 1}}
    payload = json.loads(_JsonFormatter().format(record))
    assert payload["event"] == "turn_trace"
    assert payload["msg"] == "turn_trace"
    assert payload["trace"] == {"kind": "new", "tools": {"web_search": 1}}


@pytest.mark.parametrize(
    "scope_type, headers, query, expected",
    [
        ("websocket", [], b"token=x&request_id=phone-1234abcd", "phone-1234abcd"),
        ("websocket", [(b"x-request-id", b"header-id")], b"request_id=query-id", "header-id"),
        ("websocket", [], b"token=x", None),
        ("http", [], b"request_id=query-id", None),
    ],
)
def test_a_socket_may_name_its_request_in_the_query(
    scope_type: str, headers: list[tuple[bytes, bytes]], query: bytes, expected: str | None
) -> None:
    scope = {"type": scope_type, "headers": headers, "query_string": query}
    assert client_request_id(scope) == expected


def test_a_turn_a_photo_or_picture_answered_is_logged_when_its_reply_is_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from types import SimpleNamespace

    from app.modules.chat import turn_intercepts

    caplog.set_level(logging.INFO, logger=turn_trace.__name__)
    begin_turn_trace("new")
    message = SimpleNamespace(id=uuid4(), content=_SECRET, model=None)
    turn_intercepts._record(TurnOutcome(), message, "image-gen-model")  # type: ignore[arg-type]
    trace = _emitted(caplog).turn_trace  # type: ignore[attr-defined]
    assert (trace["path"], trace["resolved_model"]) == ("intercept", "image-gen-model")
    assert "hunter2" not in caplog.text
