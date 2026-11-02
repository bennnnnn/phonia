"""One log line per chat turn: what it decided, never what anyone wrote.

"Why did the bot say that?" had no answer from production: routing, the turn's plan,
the prompt's rules, the subject readers and the finalize passes decide silently, and
only the final text is saved. A turn collects its decisions here and logs them once,
at the end, as one INFO line (``event=turn_trace``) beside the ids the log context
already carries (request, chat, turn, user).

Ids and decisions only: names of rules and passes, model aliases, operation ids,
counts, sizes and timings. A string that is not a plain identifier never enters the
record (``_token``), so no message, reply, prompt, memory or URL can, whatever a
caller passes. The collector lives in a context variable like the log ids: code deep
in the turn notes a decision without a parameter, a note outside a turn does nothing,
and a note or the line itself can never fail the turn.
"""

from __future__ import annotations

import functools
import json
import logging
import re
import time
from asyncio import CancelledError
from collections import Counter
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from app.core.log_context import current_log_ids

if TYPE_CHECKING:
    from app.modules.chat.turn_outcome import TurnOutcome
    from app.modules.chat.turn_prep import StreamContext

logger = logging.getLogger(__name__)

# An alias, an operation id, a rule or pass name: letters, digits, ``_``, ``-`` and ``.``.
# No space, ``:``, ``/`` or ``@``: no sentence, URL or address passes.
_TOKEN = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
_MAX_NAMES = 64


@dataclass
class TurnTrace:
    """What one turn decided, as it decides it."""

    kind: str
    started: float = field(default_factory=time.perf_counter)
    route: str | None = None
    plan: tuple[str, ...] = ()
    # Why the plan is what it is (``turn_reading.turn.PlanReason``).
    plan_reason: str | None = None
    # Why the turn is small talk or not (``turn_prep.mode.LightReason``).
    lightweight_reason: str | None = None
    # Why the message asks to be taught or not (``turn_reading.teaching.TeachingReason``).
    teaching_reason: str | None = None
    # Which step of the subject order decided the message's subject, or that the pool did
    # not read it (``services.subjects.dispatch.SubjectReason``, ``not_read``,
    # ``read_declined``).
    subject_reason: str | None = None
    prompt_rules: list[str] = field(default_factory=list)
    tools: Counter[str] = field(default_factory=Counter)
    passes_changed: list[tuple[str, int]] = field(default_factory=list)
    passes_failed: list[str] = field(default_factory=list)
    # The model reader's shadow read (``turn_prep.model_read_shadow``): its task, and the
    # ``model_reader.schemas.ModelRead`` it set when it finished.
    model_read_task: Any = None
    model_read: Any = None
    emitted: bool = False


_TRACE: ContextVar[TurnTrace | None] = ContextVar("turn_trace", default=None)


def _token(value: object) -> str | None:
    """``value`` when it is a plain identifier, else nothing."""
    if isinstance(value, str) and _TOKEN.fullmatch(value):
        return value
    return None


def _quietly(note: Any) -> Any:
    """A note that fails is dropped: tracing never breaks a turn."""

    def run(*args: Any, **kwargs: Any) -> None:
        trace = _TRACE.get()
        if trace is None or trace.emitted:
            return
        try:
            note(trace, *args, **kwargs)
        except Exception as exc:
            logger.info("turn trace note %s failed (%s)", note.__name__, type(exc).__name__)

    return run


def begin_turn_trace(kind: str) -> TurnTrace:
    """Start collecting the turn running in this context (``new`` or ``regenerate``).

    Like ``readings.begin_turn``: tasks the turn starts share it, and the next turn
    starts its own. Once its line is logged, later notes go nowhere.
    """
    trace = TurnTrace(kind=kind)
    _TRACE.set(trace)
    return trace


def current_turn_trace() -> TurnTrace | None:
    return _TRACE.get()


@_quietly
def note_route(trace: TurnTrace, reason: str) -> None:
    """Why routing chose the turn's lane (``route.routed_chat_model``)."""
    trace.route = _token(reason)


@_quietly
def note_lightweight(trace: TurnTrace, reason: str) -> None:
    """Why the turn is small talk or not (``turn_prep.mode.classify_turn_mode``)."""
    trace.lightweight_reason = _token(reason)


@_quietly
def note_subject(trace: TurnTrace, reason: str) -> None:
    """Which step of the subject order decided the message's subject (the turn's reading)."""
    trace.subject_reason = _token(reason)


@_quietly
def note_teaching(trace: TurnTrace, reason: str) -> None:
    """Why the message asks to be taught or not (the turn's reading)."""
    trace.teaching_reason = _token(reason)


@_quietly
def note_plan(trace: TurnTrace, kinds: Iterable[str], reason: str | None = None) -> None:
    """The kinds of the requests the message holds (``intents.plan_turn``), and why
    (the turn's reading, ``turn_reading.turn``)."""
    trace.plan = tuple(kind for kind in map(_token, kinds) if kind)[:_MAX_NAMES]
    trace.plan_reason = _token(reason)


@_quietly
def note_prompt_rule(trace: TurnTrace, name: str) -> None:
    if len(trace.prompt_rules) < _MAX_NAMES and (token := _token(name)):
        trace.prompt_rules.append(token)


@_quietly
def note_tool(trace: TurnTrace, name: str) -> None:
    trace.tools[_token(name) or "unknown"] += 1


@_quietly
def note_pass(trace: TurnTrace, name: str, before: str, after: str) -> None:
    """A finalize pass's effect: recorded only when it changed the text."""
    if after != before and len(trace.passes_changed) < _MAX_NAMES:
        trace.passes_changed.append((_token(name) or "unknown", len(after) - len(before)))


@_quietly
def note_pass_failed(trace: TurnTrace, name: str) -> None:
    if len(trace.passes_failed) < _MAX_NAMES:
        trace.passes_failed.append(_token(name) or "unknown")


def _solver(ctx: StreamContext) -> dict[str, Any]:
    """The subject that answered with a checked card, and the operation it ran."""
    block = ctx.verified_subject
    found: dict[str, Any] = {
        "verified": None,
        "op": None,
        "unverified": ctx.solver_unverified,
        "unverified_subject": _token(ctx.unverified_subject),
        "timed_out": ctx.solve_timed_out,
    }
    if block is None:
        return found
    found["verified"] = _token(block.subject)
    physics = getattr(block, "physics_intent", None)
    chemistry = getattr(block, "intent", None)
    maths = getattr(block, "response_intent", None)
    op = (
        getattr(physics, "physics_op", None)
        or getattr(chemistry, "chemistry_op", None)
        or getattr(getattr(maths, "mode", None), "value", None)
    )
    found["op"] = _token(op)
    return found


def _money(ctx: StreamContext) -> dict[str, Any] | None:
    money = ctx.money
    if money is None:
        return None
    product = getattr(getattr(money.request, "product", None), "key", None)
    return {"product": _token(product), "worked": money.worked is not None}


def _model_read(trace: TurnTrace, solver: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """How the model reader's shadow read compares with the patterns' verified read;
    ``pending`` while it is still reading (its own line follows, ``_log_late_read``)."""
    if trace.model_read_task is None:
        return None
    if trace.model_read is None:
        return {"verdict": "pending"}
    return _shadow_fields(trace.model_read, solver)


def _shadow_fields(read: Any, solver: Mapping[str, Any] | None) -> dict[str, Any]:
    from app.modules.model_reader.schemas import verdict

    regex_subject = solver.get("verified") if solver else None
    regex_op = solver.get("op") if solver else None
    return {
        "verdict": verdict(regex_subject, regex_op, read),
        "subject": _token(read.subject),
        "op": _token(read.op),
        "reason": _token(read.reason),
        "ms": read.ms,
        "tokens": read.input_tokens + read.output_tokens,
    }


def _log_late_read(trace: TurnTrace, solver: Mapping[str, Any] | None, task: Any) -> None:
    """A shadow read that finished after the turn's line logs its own, with the same ids
    (the callback runs in the turn's context). It is bounded by its calls' own timeouts."""
    if task.cancelled() or task.exception() is not None or trace.model_read is None:
        return
    try:
        fields = _shadow_fields(trace.model_read, solver)
        logger.info(
            "turn_model_read %s",
            json.dumps(fields, separators=(",", ":"), sort_keys=True),
            extra={"turn_model_read": fields},
        )
    except Exception as exc:
        logger.info("turn model read line failed (%s)", type(exc).__name__)


def _completion(outcome: TurnOutcome | None, failure: BaseException | None) -> str:
    """``complete``, ``user_stop``, ``interrupted`` (``stream_accum``), ``cancelled`` or
    ``error``."""
    if failure is not None:
        return "cancelled" if isinstance(failure, GeneratorExit | CancelledError) else "error"
    completion = outcome.completion if outcome is not None else None
    return _token(completion) or "complete"


def turn_record(
    trace: TurnTrace,
    ctx: StreamContext | None,
    *,
    outcome: TurnOutcome | None,
    failure: BaseException | None = None,
    path: str = "stream",
) -> dict[str, Any]:
    """The turn's line, from its notes, its context and how it ended."""
    record: dict[str, Any] = {
        "kind": _token(trace.kind),
        "path": _token(path),
        "transport": _token(current_log_ids().get("transport")),
        "outcome": _completion(outcome, failure),
        "error": _token(type(failure).__name__) if failure is not None else None,
        "route": trace.route,
        "plan": list(trace.plan),
        "plan_reason": trace.plan_reason,
        "lightweight_reason": trace.lightweight_reason,
        "teaching_reason": trace.teaching_reason,
        "subject_reason": trace.subject_reason,
        "prompt_rules": list(trace.prompt_rules),
        "tools": dict(trace.tools),
        "passes_changed": [list(item) for item in trace.passes_changed],
        "passes_failed": list(trace.passes_failed),
        "total_ms": round((time.perf_counter() - trace.started) * 1000, 1),
    }
    if outcome is not None:
        # The model that answered: a fallback's, or the picture model's.
        record["resolved_model"] = _token(outcome.resolved_model)
        record["fallback_used"] = outcome.fallback_used
    if ctx is not None:
        record.update(
            model=_token(ctx.model),
            fallback_models=len(ctx.fallback_models),
            thinking=ctx.thinking if isinstance(ctx.thinking, bool) else _token(ctx.thinking),
            lightweight=ctx.lightweight_turn,
            rich_context=ctx.rich_context_turn,
            instant=ctx.instant_reply is not None,
            solver=_solver(ctx),
            money=_money(ctx),
            search_hits=len(ctx.search_sources),
            local_places=ctx.local_places,
            recalled=ctx.recalled_count,
            summarized=ctx.context_summarized,
            prior_messages=ctx.prior_count,
            settings_card=ctx.settings_card is not None,
            answer_photos=len(ctx.answer_photo_ids),
            reply_tools=len(ctx.reply_tools),
        )
        if ctx.timing is not None:
            record.update(ctx.timing.milestones())
    shadow = _model_read(trace, record.get("solver"))
    if shadow is not None:
        record["model_read"] = shadow
    return record


def traced_turn[**P](
    kind: str,
) -> Callable[[Callable[P, AsyncIterator[str]]], Callable[P, AsyncIterator[str]]]:
    """A turn's stream (``stream_entry``), traced: its line is logged once, by the time the
    stream ends. A turn refused or cancelled before its reply streamed (quota, consent, an
    intercept's error, a Stop during preparation) logs ``path=prep`` and how it ended."""

    def wrap(stream: Callable[P, AsyncIterator[str]]) -> Callable[P, AsyncIterator[str]]:
        @functools.wraps(stream)
        async def run(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[str]:
            begin_turn_trace(kind)
            tokens = stream(*args, **kwargs)
            failure: BaseException | None = None
            try:
                async for token in tokens:
                    yield token
            except BaseException as exc:
                failure = exc
                raise
            finally:
                try:
                    # Closed here, not when collected: its locks and saves end with it.
                    close = getattr(tokens, "aclose", None)
                    if close is not None:
                        await close()
                finally:
                    outcome = cast("TurnOutcome | None", kwargs.get("outcome"))
                    emit_turn_trace(None, outcome=outcome, failure=failure, path="prep")

        return run

    return wrap


def emit_turn_trace(
    ctx: StreamContext | None,
    *,
    outcome: TurnOutcome | None,
    failure: BaseException | None = None,
    path: str = "stream",
) -> None:
    """Log the turn's line once. Never raises."""
    trace = _TRACE.get()
    if trace is None or trace.emitted:
        return
    trace.emitted = True
    try:
        record = turn_record(trace, ctx, outcome=outcome, failure=failure, path=path)
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
    except Exception:
        logger.warning("turn trace could not be built", exc_info=True)
        return
    logger.info("turn_trace %s", line, extra={"turn_trace": record})
    task = trace.model_read_task
    if task is not None and not task.done():
        task.add_done_callback(functools.partial(_log_late_read, trace, record.get("solver")))


def plain_record(record: Mapping[str, Any]) -> bool:
    """True when every value is a number, a bool, None, an identifier, or a list or map
    of them: what a turn's line may hold (the tests' check)."""

    def plain(value: object) -> bool:
        if value is None or isinstance(value, bool | int | float):
            return True
        if isinstance(value, str):
            return _token(value) is not None
        if isinstance(value, list | tuple):
            return all(plain(item) for item in value)
        if isinstance(value, Mapping):
            return all(_token(key) is not None and plain(item) for key, item in value.items())
        return False

    return plain(record)
