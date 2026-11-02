"""One round's calls: different tools run at once, a tool's own calls in order, and the
tool messages and merged results always follow the order the model made the calls."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import patch

import pytest

from app.gateways.mcp import registry as mcp_registry
from app.gateways.mcp.base import ToolResult
from app.modules.chat.tool_loop.calls import CallRound, execute_calls
from app.modules.chat.tool_loop.results import ToolResults
from app.tests.tool_context import tool_context

from .tool_loop_support import settings

_OFFERED = frozenset({"web_search", "search_image", "sympy"})


def _call(call_id: str, name: str, query: str) -> dict[str, Any]:
    args = json.dumps({"query": query})
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}


def _round(
    *,
    on_status: Any = None,
    should_cancel: Any = None,
    timeout: float = 5.0,
) -> CallRound:
    return CallRound(
        settings=settings(mcp_tool_loop_invoke_timeout_seconds=timeout),
        offered=_OFFERED,
        ctx=tool_context(),
        on_status=on_status,
        should_cancel=should_cancel,
        user_texts=["what is it"],
        user_text="what is it",
    )


def _hits(url: str) -> dict[str, Any]:
    return {"hits": [{"title": url, "url": url, "snippet": "s"}]}


class _Invoke:
    """A registry stand-in: each query sleeps its delay; records start and end order."""

    def __init__(self, delays: dict[str, float], fail: str | None = None) -> None:
        self.delays = delays
        self.fail = fail
        self.events: list[str] = []
        self.cancelled: list[str] = []

    async def __call__(self, name: str, raw_args: str, _ctx: object) -> ToolResult:
        query = json.loads(raw_args)["query"]
        self.events.append(f"start {query}")
        try:
            await asyncio.sleep(self.delays.get(query, 0.0))
        except asyncio.CancelledError:
            self.cancelled.append(query)
            raise
        if query == self.fail:
            raise RuntimeError("tool broke")
        self.events.append(f"end {query}")
        return ToolResult(name=name, content=f"found {query}", data=_hits(f"https://{query}"))


async def _execute(turn: CallRound, tool_calls: list[dict[str, Any]], invoke: _Invoke) -> Any:
    working: list[dict[str, Any]] = []
    collected = ToolResults()
    with patch.object(mcp_registry, "invoke_validated", invoke):
        await execute_calls(turn, tool_calls, working, collected)
    return working, collected


@pytest.mark.wall_clock
async def test_different_tools_run_at_once_and_answer_in_call_order() -> None:
    invoke = _Invoke({"news": 0.3, "ear": 0.05})
    started = time.monotonic()
    working, collected = await _execute(
        _round(), [_call("c1", "web_search", "news"), _call("c2", "search_image", "ear")], invoke
    )

    assert time.monotonic() - started < 0.3 + 0.2  # not 0.35 run one after the other
    assert invoke.events[:2] == ["start news", "start ear"]
    # The photo finished first, yet each message and source keeps the call's order.
    assert [(m["tool_call_id"], m["content"]) for m in working] == [
        ("c1", "found news"),
        ("c2", "found ear"),
    ]
    assert [hit.url for hit in collected.search_hits] == ["https://news", "https://ear"]


async def test_one_tools_calls_run_in_order() -> None:
    invoke = _Invoke({"a": 0.05, "b": 0.0})
    working, _collected = await _execute(
        _round(), [_call("c1", "web_search", "a"), _call("c2", "web_search", "b")], invoke
    )

    assert invoke.events == ["start a", "end a", "start b", "end b"]
    assert [m["tool_call_id"] for m in working] == ["c1", "c2"]


async def test_a_failed_call_cancels_the_others_and_raises() -> None:
    invoke = _Invoke({"slow": 5.0, "bad": 0.01}, fail="bad")
    with pytest.raises(RuntimeError, match="tool broke"):
        await _execute(
            _round(), [_call("c1", "web_search", "slow"), _call("c2", "sympy", "bad")], invoke
        )
    assert invoke.cancelled == ["slow"]


async def test_a_cancel_stops_calls_not_yet_started() -> None:
    stop = False

    async def on_status(_phase: str, _detail: str | None = None) -> None:
        return None

    invoke = _Invoke({"a": 0.0})

    def should_cancel() -> bool:
        return stop

    async def invoke_then_stop(name: str, raw_args: str, ctx: object) -> ToolResult:
        nonlocal stop
        result = await invoke(name, raw_args, ctx)
        stop = True
        return result

    working: list[dict[str, Any]] = []
    with patch.object(mcp_registry, "invoke_validated", invoke_then_stop):
        await execute_calls(
            _round(on_status=on_status, should_cancel=should_cancel),
            [_call("c1", "web_search", "a"), _call("c2", "web_search", "b")],
            working,
            ToolResults(),
        )

    assert invoke.events == ["start a", "end a"]
    assert [m["tool_call_id"] for m in working] == ["c1"]  # the caller trims the round


@pytest.mark.parametrize(
    "tool_calls, expected",
    [
        (
            [_call("c1", "web_search", "news"), _call("c2", "search_image", "ear")],
            [("searching", "news"), ("composing", None)],
        ),
        (
            [_call("c1", "sympy", "x"), _call("c2", "web_search", "news")],
            [("calculating", None), ("composing", None)],
        ),
        ([_call("c1", "calendar", "x")], []),  # not offered: refused, nothing announced
    ],
)
async def test_one_status_for_the_round(
    tool_calls: list[dict[str, Any]], expected: list[tuple[str, str | None]]
) -> None:
    statuses: list[tuple[str, str | None]] = []

    async def on_status(phase: str, detail: str | None = None) -> None:
        statuses.append((phase, detail))

    await _execute(_round(on_status=on_status), tool_calls, _Invoke({}))
    assert statuses == expected


@pytest.mark.wall_clock
async def test_the_round_shares_one_deadline() -> None:
    invoke = _Invoke({"a": 1.0, "b": 1.0, "c": 1.0})
    started = time.monotonic()
    working, _collected = await _execute(
        _round(timeout=0.2),
        [_call("c1", "web_search", "a"), _call("c2", "web_search", "b"), _call("c3", "sympy", "c")],
        invoke,
    )

    assert time.monotonic() - started < 0.8
    assert [m["content"] for m in working] == ["Tool round timed out."] * 3
    assert "start b" not in invoke.events  # its tool's first call used the round up
