"""WS and SSE must speak the same protocol.

Both transports build every stream event through
`app.modules.chat.stream_events`. These tests pin the shared shapes so a new
event (or a new field on `stream_end` / `done`) cannot land on one transport
and silently miss the other — the backend is documented as client-agnostic, and
a future web client binds to this same contract.
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

from app.modules.chat import stream_events
from app.modules.chat.stream_events import DoneEvent, StreamEndEvent
from app.modules.chat.turn_outcome import TurnOutcome

_CHAT = Path(__file__).resolve().parents[3] / "modules" / "chat"
_WS = _CHAT / "ws_turn.py"  # one turn on a socket; ws_api reads its frames
_WS_SOCKET = _CHAT / "ws_api.py"
_SSE = _CHAT / "stream_api.py"

# Every event type the protocol defines, and the builder that owns its shape.
_BUILDERS = {
    "start": lambda: stream_events.build_start_event(),
    "token": lambda: stream_events.build_token_event("hi"),
    "status": lambda: stream_events.build_status_event("thinking", None),
    "reasoning": lambda: stream_events.build_reasoning_event("hmm"),
    "stream_end": lambda: StreamEndEvent.from_outcome(TurnOutcome()).model_dump(),
    "done": lambda: DoneEvent.from_outcome(TurnOutcome()).model_dump(),
    "related_prompts": lambda: stream_events.build_related_prompts_event(
        "abc",
        ["Why is the force the product of mass and acceleration?"],
    ),
    "duplicate": lambda: stream_events.build_duplicate_event(),
    "pong": lambda: stream_events.build_pong_event(),
}


@pytest.mark.parametrize("event_type", sorted(_BUILDERS))
def test_builder_emits_its_declared_type(event_type: str) -> None:
    assert _BUILDERS[event_type]()["type"] == event_type


def test_stream_end_carries_model_fields_when_present() -> None:
    outcome = TurnOutcome(resolved_model="smart-chat", fallback_used=True)
    assert StreamEndEvent.from_outcome(outcome).model_dump() == {
        "type": "stream_end",
        "resolved_model": "smart-chat",
        "fallback_used": "1",
    }


def test_stream_end_omits_absent_model_fields() -> None:
    assert StreamEndEvent.from_outcome(TurnOutcome()).model_dump() == {"type": "stream_end"}


def test_done_includes_completion_when_interrupted() -> None:
    outcome = TurnOutcome(message_id="abc", completion="interrupted")
    payload = DoneEvent.from_outcome(outcome).model_dump()
    assert payload["type"] == "done"
    assert payload["completion"] == "interrupted"
    assert payload["message_id"] == "abc"


async def test_done_does_not_carry_related_prompts() -> None:
    async def follow_ups() -> dict[str, object]:
        return stream_events.build_related_prompts_event("abc", ["Why?"])

    related_task = asyncio.create_task(follow_ups())
    outcome = TurnOutcome(message_id="abc", related_task=related_task)
    payload = DoneEvent.from_outcome(outcome).model_dump()
    assert "related_prompts" not in payload
    assert "prompts" not in payload
    assert payload["message_id"] == "abc"
    await related_task


def test_done_is_the_shape_installed_phones_read() -> None:
    """Every field, in this order; the flag and the lists are strings until ES-45."""
    outcome = TurnOutcome(
        message_id="m1",
        final_content="Café ✓",
        resolved_model="smart-chat",
        fallback_used=True,
        completion="interrupted",
        recalled=2,
        memory_hints=["Likes cats"],
        context_summarized=6,
        search_sources=[{"title": "Moon", "url": "https://example.com", "snippet": "Orbit."}],
        todos_changed=True,
    )
    wire = json.dumps(DoneEvent.from_outcome(outcome).model_dump(), separators=(",", ":"))
    assert wire == (
        '{"type":"done","message_id":"m1","recalled":"2","memory_hints":"[\\"Likes cats\\"]",'
        '"context_summarized":"6","todos_sync":"1","search_sources":"[{\\"title\\": '
        '\\"Moon\\", \\"url\\": \\"https://example.com\\", \\"snippet\\": \\"Orbit.\\"}]",'
        '"final_content":"Caf\\u00e9 \\u2713","resolved_model":"smart-chat",'
        '"fallback_used":"1","completion":"interrupted"}'
    )


def test_done_while_the_commit_runs_has_no_id_and_says_persisting() -> None:
    outcome = TurnOutcome(message_id="m1", resolved_model="free-chat", todos_changed=True)
    payload = DoneEvent.from_outcome(outcome, persisting=True).model_dump()
    assert payload == {
        "type": "done",
        "todos_sync": "1",
        "resolved_model": "free-chat",
        "persisting": True,
    }


def test_done_leaves_out_empty_fields() -> None:
    outcome = TurnOutcome(message_id="", final_content=None, memory_hints=[], search_sources=[])
    assert DoneEvent.from_outcome(outcome).model_dump() == {"type": "done"}


def test_done_carries_an_emptied_reply() -> None:
    # None is "settle what you streamed"; "" is a fallback its safety passes emptied.
    payload = DoneEvent.from_outcome(TurnOutcome(final_content="")).model_dump()
    assert payload == {"type": "done", "final_content": ""}


def test_related_prompts_event_shape() -> None:
    question = "Why is the force the product of mass and acceleration?"
    event = stream_events.build_related_prompts_event("abc", [question])
    assert event == {"type": "related_prompts", "message_id": "abc", "prompts": [question]}


@pytest.mark.parametrize("router", [_WS, _SSE], ids=["ws", "sse"])
def test_related_prompts_follow_done(router: Path) -> None:
    source = router.read_text()
    assert source.rindex("settled_turn_event") < source.rindex("take_related_prompts_event")


def test_done_omits_complete_completion() -> None:
    payload = DoneEvent.from_outcome(TurnOutcome(message_id="abc")).model_dump()
    assert "completion" not in payload


def test_status_detail_is_optional() -> None:
    assert stream_events.build_status_event("searching") == {
        "type": "status",
        "phase": "searching",
    }
    assert stream_events.build_status_event("searching", "cats") == {
        "type": "status",
        "phase": "searching",
        "detail": "cats",
    }


def test_both_transports_are_json_serializable() -> None:
    for build in _BUILDERS.values():
        json.dumps(build())


def _inline_event_types(path: Path) -> set[str]:
    """Event `type` values a router still constructs inline, bypassing the builders."""
    source = path.read_text()
    return set(re.findall(r'"type":\s*"([a-z_]+)"', source))


@pytest.mark.parametrize("router", [_WS, _WS_SOCKET, _SSE], ids=["ws", "ws-socket", "sse"])
def test_routers_do_not_rebuild_shared_events_inline(router: Path) -> None:
    """`error` stays inline-free too — it has its own builder.

    Only transport-specific failures may be constructed in a router (the SSE
    "failed to save" message), so anything matching a shared event type here
    means the two transports can drift apart again.
    """
    shared = set(_BUILDERS) | {"error"}
    # "error" is exempt: routers still inline transport-specific failures
    # (auth timeout, invalid JSON, "failed to save") alongside the builder.
    inline = _inline_event_types(router) - {"error"}
    leaked = inline & shared
    assert leaked == set(), f"{router.name} builds shared events inline: {sorted(leaked)}"


def test_done_carries_the_days_usage_for_the_quota_nudge() -> None:
    """The phone read the usage with a GET after every turn (code-health audit NET-14)."""
    from app.modules.chat.turn_outcome import TurnUsage

    outcome = TurnOutcome(usage=TurnUsage(used_tokens=8000, daily_limit=10000))
    payload = DoneEvent.from_outcome(outcome).model_dump()
    assert (payload["used_tokens"], payload["daily_limit"]) == ("8000", "10000")
    assert "used_tokens" not in DoneEvent.from_outcome(TurnOutcome()).model_dump()
