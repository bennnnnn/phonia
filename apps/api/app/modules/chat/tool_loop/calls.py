"""Answering each call of a selection round: refuse it, or run it and merge what it found.

Every call gets exactly one tool message, in order, so the provider accepts the
message list. A call over the round's cap, past its deadline, for a tool this turn
was not offered, or for a trig solve that would drop the user's domain is refused
in that message and never runs.

Calls to different tools run at once under the round's one deadline; calls to the same
tool run one after another, in order (a search runs once per turn and its repeats reuse
the first result; solves share the SymPy pool). What each found merges in call order,
so the turn's verified fences and sources never depend on which call finished first.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.gateways.mcp import registry as mcp_registry
from app.gateways.mcp.base import ToolContext, ToolResult
from app.modules.chat.stream_status import StreamStatusFn, StreamStatusPhase, clip_status_detail
from app.modules.chat.tool_loop.results import (
    ToolResults,
    _canonical_answer_from_tool_result,
    _canonical_from_tool_result,
)
from app.modules.chat.turn_trace import note_tool
from app.modules.turn_reading.readable import unreadable
from app.services.subjects.registry import subject_adapter

logger = logging.getLogger(__name__)

_UNMATCHED_TOOL_NOTE = (
    "\nNote: this call's input does not match the problem as the user wrote it, so this "
    "result is not verified for the user's question. Re-read the user's problem before "
    "using it, and do not call it verified."
)
_TIMED_OUT = "Tool round timed out."
_TRIG_DOMAIN_REFUSAL = (
    "This trig solve cannot verify the domain requested by the user. "
    "No solution was certified. Preserve the requested domain when "
    "answering; do not substitute an unrestricted real solution."
)


@dataclass(frozen=True)
class CallRound:
    """What every call in the turn's selection round shares."""

    settings: Settings
    offered: frozenset[str]
    ctx: ToolContext
    on_status: StreamStatusFn | None
    should_cancel: Callable[[], bool] | None
    # The user's own words, newest first: a result is verified only for these.
    user_texts: list[str]
    # The last user prompt message, whose requested trig domain a solve must keep.
    user_text: str

    def cancelled(self) -> bool:
        return bool(self.should_cancel and self.should_cancel())


def _status_for_tool(name: str) -> StreamStatusPhase | None:
    if name == "web_search":
        return "searching"
    if name == "sympy":
        return "calculating"
    if name == "generate_image":
        return "image_gen"
    # A reference-photo lookup finds a real photo; it is not image generation,
    # whose card (progress estimate, "Sketching it out") would be a false claim.
    if name == "search_image":
        return "finding_photo"
    return None


def _status_detail_for_tool(name: str, raw_args: str) -> str | None:
    """Surface the tool's subject (e.g. the search query) for the status label."""
    if name in ("web_search", "search_image"):
        key = "query"
    elif name == "generate_image":
        key = "prompt"
    else:
        return None
    try:
        args = json.loads(raw_args)
    except (TypeError, ValueError):
        return None
    if not isinstance(args, dict):
        return None
    value = args.get(key)
    return clip_status_detail(value) if isinstance(value, str) else None


async def _tool_call_matches_user(
    raw_args: Any, user_texts: list[str], settings: Settings, locale: str | None = None
) -> bool:
    """A tool result is the verified answer only for the problem the user wrote, in words
    and numbers the readers read (``turn_reading.readable``; ``locale`` is the user's)."""
    from app.core.sympy_executor import run_sympy

    tool = subject_adapter("math").tool
    if tool is None:
        return False
    try:
        matched = await run_sympy(
            tool.call_matches,
            raw_args,
            user_texts,
            timeout=settings.stem_solve_timeout_seconds,
        )
    except Exception:
        logger.info("tool-call match check did not finish; result stays unverified", exc_info=True)
        return False
    return isinstance(matched, str) and unreadable(matched, locale) is None


@dataclass(frozen=True)
class _Call:
    """One call of the round, in the order the model made it."""

    index: int
    call_id: str
    name: str
    raw_args: Any
    # Its tool message when it must not run; None when it runs.
    refusal: str | None


@dataclass(frozen=True)
class _Ran:
    """What one call that ran found, before it merges into the turn's results."""

    content: str
    result: ToolResult | None = None
    fence: dict[str, Any] | None = None
    answer: str | None = None
    # The call's input was not the user's problem: its fence and answer are not verified.
    unmatched: bool = False


async def execute_calls(
    turn: CallRound,
    tool_calls: list[dict[str, Any]],
    working: list[dict[str, Any]],
    collected: ToolResults,
) -> None:
    """Append one tool message per call, in order; a call a cancel kept from running
    gets none (the caller trims the unanswered round)."""
    if turn.cancelled():
        return
    max_calls = max(1, turn.settings.mcp_tool_loop_max_calls_per_round)
    invoke_deadline = time.monotonic() + turn.ctx.seconds_left(
        turn.settings.mcp_tool_loop_invoke_timeout_seconds
    )
    calls = [
        _plan(turn, index, call, over_cap=index >= max_calls, deadline=invoke_deadline)
        for index, call in enumerate(tool_calls)
    ]
    runnable = [call for call in calls if call.refusal is None]
    announced = await _announce(turn, runnable)
    ran = await _run_round(invoke_deadline, turn, runnable)
    for call in calls:
        if call.refusal is not None:
            content = call.refusal
        elif call.index in ran:
            content = await _merge(turn, ran[call.index], collected)
        else:
            continue  # cancelled before it ran
        working.append({"role": "tool", "tool_call_id": call.call_id, "content": content})
    if announced and turn.on_status is not None and collected.terminal_image is None:
        # The tools are done; the model is next. A "Searching — …" label must not
        # keep rotating through that model round. A picture ends the turn itself.
        await turn.on_status("composing")


def _plan(
    turn: CallRound, index: int, call: dict[str, Any], *, over_cap: bool, deadline: float
) -> _Call:
    fn = call.get("function") or {}
    name = str(fn.get("name") or "")
    raw_args = fn.get("arguments") or "{}"
    refusal = _refusal(turn, name, raw_args, over_cap=over_cap, deadline=deadline)
    return _Call(index, str(call.get("id") or name), name, raw_args, refusal)


async def _announce(turn: CallRound, runnable: list[_Call]) -> bool:
    """One status for the round, before its calls start: a picture's when one is drawn
    (its card shows the wait), else the first call's that has one. Calls running at once
    each announcing would flicker the label between them."""
    phased = [call for call in runnable if _status_for_tool(call.name) is not None]
    if not phased:
        return False
    lead = next((call for call in phased if call.name == "generate_image"), phased[0])
    phase = _status_for_tool(lead.name)
    if turn.on_status is not None and phase is not None:
        await turn.on_status(phase, _status_detail_for_tool(lead.name, lead.raw_args))
    return True


async def _run_round(deadline: float, turn: CallRound, runnable: list[_Call]) -> dict[int, _Ran]:
    """Run the round's calls: each tool's in order, the tools at once. A failure cancels
    the rest and is raised, as a cancel of the turn is."""
    by_tool: dict[str, list[_Call]] = {}
    for call in runnable:
        by_tool.setdefault(call.name, []).append(call)
    ran: dict[int, _Ran] = {}

    async def run_tool(calls: list[_Call]) -> None:
        for call in calls:
            if turn.cancelled():
                return
            if time.monotonic() >= deadline:  # an earlier call of this tool used the round up
                ran[call.index] = _Ran(_TIMED_OUT)
                continue
            ran[call.index] = await _run_call_by(deadline, turn, call.name, call.raw_args)

    await gather_or_cancel(*(run_tool(calls) for calls in by_tool.values()))
    return ran


def _refusal(
    turn: CallRound, name: str, raw_args: Any, *, over_cap: bool, deadline: float
) -> str | None:
    """Why this call must not run, as its tool message; None when it may run."""
    if over_cap:
        return "Too many tool calls in one round."
    if time.monotonic() >= deadline:
        return _TIMED_OUT
    if name not in turn.offered:
        # A provider can return a call to a tool it was not given.
        # Never run it (e.g. generate_image the user did not ask for).
        return f"Tool {name or '(unnamed)'} is not available for this turn."
    tool = subject_adapter("math").tool
    if tool is not None and tool.refuses(name, raw_args, turn.user_text):
        # This solver owns all-real trig solutions. The tool schema
        # cannot express the requested interval or alternative domain;
        # do not reintroduce an answer rejected during turn preparation.
        # Other computations and tool calls remain available.
        return _TRIG_DOMAIN_REFUSAL
    return None


async def _run_call_by(deadline: float, turn: CallRound, name: str, raw_args: Any) -> _Ran:
    """``_run_call``, cut off at the round's deadline.

    The deadline used to stop only new calls from starting: a call that started in time
    ran on its own httpx timeouts (Tavily 12 s per phase, image generation 120 s).
    """
    try:
        async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
            return await _run_call(turn, name, raw_args)
    except TimeoutError:
        logger.warning("Tool call timed out tool=%s", name or "(unnamed)")
        return _Ran(_TIMED_OUT)


async def _draws_asked_curve(
    turn: CallRound, fence: dict[str, Any] | None, collected: ToolResults
) -> bool:
    """A curve the learner asked for from earlier in the chat draws, though its formula is
    the model's.

    "can you graph how the balloon's volume changes … from the problem earlier?": the
    formula was only in an earlier reply, so no user line matched the call, the curve
    was dropped and the reply said "here's the plot" over nothing (2026-10-24). A curve
    claims no answer and shows no check. Only when the message holds no formula of its
    own (one it does hold is the user's, and a call that misses it is a typo), and never
    over a curve a matched call already drew.
    """
    tool = subject_adapter("math").tool
    if tool is None or not tool.draws_curve(fence):
        return False
    if str((fence or {}).get("type")) in collected.canonical_by_type:
        return False
    from app.core.sympy_executor import run_sympy

    text = turn.user_texts[0] if turn.user_texts else turn.user_text
    try:
        asked = await run_sympy(
            tool.asks_for_earlier_curve, text, timeout=turn.settings.stem_solve_timeout_seconds
        )
    except Exception:
        logger.info("graph-ask read did not finish; the unmatched curve is dropped", exc_info=True)
        return False
    return bool(asked)


async def _run_call(turn: CallRound, name: str, raw_args: Any) -> _Ran:
    """Run one offered call and check its input against the user's problem."""
    note_tool(name)
    result = await mcp_registry.invoke_validated(name, raw_args, turn.ctx)
    if result is None:
        return _Ran(f"Unknown tool: {name}")
    fence = _canonical_from_tool_result(result)
    answer = _canonical_answer_from_tool_result(result)
    locale = turn.ctx.user.locale if turn.ctx.user is not None else None
    unmatched = (fence is not None or bool(answer)) and not await _tool_call_matches_user(
        raw_args, turn.user_texts, turn.settings, locale
    )
    return _Ran(result.content, result, fence, answer, unmatched)


async def _merge(turn: CallRound, ran: _Ran, collected: ToolResults) -> str:
    """Merge what one call found, in call order, and return its tool message."""
    fence, answer, content = ran.fence, ran.answer, ran.content
    if ran.unmatched:
        # The tool solved what the model typed, not what the user asked: no verified answer.
        if not await _draws_asked_curve(turn, fence, collected):
            fence = None
        answer = None
        content = f"{content}{_UNMATCHED_TOOL_NOTE}"
    if ran.result is not None:
        collected.merge(ran.result, fence=fence, answer=answer)
    return content
