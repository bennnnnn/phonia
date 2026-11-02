"""Count what a chat turn sends out of the process: the ledger and its fakes.

``test_turn_whole_trips`` drives whole turns through the app and reads this ledger. It
counts model calls (by the code that made them), embedding requests, web and photo
searches, SQL statements, pool checkouts, transactions and Redis round trips.

The model is faked at the provider seam (``litellm_gateway.acompletion``,
``embedding_gateway.aembedding``), not in mock mode: mock mode skips most model
calls (``should_mock_llm``), and the point is to see each call production makes. The
fakes answer each kind of call as a model would: a stream of words (or a tool call),
JSON its schema accepts, a tool choice.
"""

from __future__ import annotations

import inspect
import json
import types
import typing
from collections import Counter
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from pydantic import BaseModel

APP_DIR = Path(__file__).resolve().parents[3]
# Frames that say nothing about who made a call: the provider seams and this harness.
_SEAMS = ("gateways", "tests")
_VECTOR = [0.1] * 8 + [0.0] * 1528


@dataclass(frozen=True)
class Counts:
    """What left the process: one ceiling, or one measurement."""

    sql: int = 0
    checkouts: int = 0
    transactions: int = 0
    redis: int = 0
    models: int = 0
    embeds: int = 0
    searches: int = 0

    def __add__(self, other: Counts) -> Counts:
        return Counts(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    def over(self, ceiling: Counts) -> list[str]:
        return [
            f"{f.name}: {getattr(self, f.name)} > {getattr(ceiling, f.name)}"
            for f in fields(self)
            if getattr(self, f.name) > getattr(ceiling, f.name)
        ]


@dataclass
class Ledger:
    """What left the process while ``counting``, each entry with who sent it."""

    counting: bool = False
    sql: list[str] = field(default_factory=list)
    checkouts: int = 0
    transactions: int = 0
    redis: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    embeds: list[int] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)
    # What the fake model answers: the reply it streams, the tool it calls when
    # offered it, and JSON for a structured call, by schema name.
    reply: str = "Hello! What can I help you with?"
    tool_call: tuple[str, dict[str, Any]] | None = None
    # A callable answers each call afresh, as a model told what it said before would.
    structured: dict[str, dict[str, Any] | Callable[[], dict[str, Any]]] = field(
        default_factory=dict
    )

    def start(self) -> None:
        self.sql, self.redis, self.models, self.embeds, self.searches = [], [], [], [], []
        self.checkouts = self.transactions = 0
        self.counting = True

    def stop(self) -> Ledger:
        """Stop counting; a copy of what was counted."""
        self.counting = False
        return Ledger(
            sql=list(self.sql),
            checkouts=self.checkouts,
            transactions=self.transactions,
            redis=list(self.redis),
            models=list(self.models),
            embeds=list(self.embeds),
            searches=list(self.searches),
        )

    def counts(self) -> Counts:
        return Counts(
            sql=len(self.sql),
            checkouts=self.checkouts,
            transactions=self.transactions,
            redis=len(self.redis),
            models=len(self.models),
            embeds=len(self.embeds),
            searches=len(self.searches),
        )

    def detail(self) -> str:
        """Every entry, counted, for ``pytest -s``."""
        lines = [str(self.counts())]
        for name in ("models", "embeds", "searches", "sql", "redis"):
            seen = Counter(map(str, getattr(self, name)))
            lines += [f"  {name}: {count}x {entry}" for entry, count in seen.items()]
        return "\n".join(lines)


def callers(skip: tuple[str, ...] = _SEAMS, depth: int = 1) -> str:
    """The first ``depth`` app frames outside ``skip`` (top-level folders, or
    ``repository`` for repository modules), innermost first."""
    found: list[str] = []
    for frame in inspect.stack()[2:]:
        try:
            rel = Path(frame.filename).resolve().relative_to(APP_DIR)
        except ValueError:
            continue
        if not rel.parts or rel.parts[0] in (*skip, "tests"):
            continue
        if "repository" in skip and rel.stem.endswith("repository"):
            continue
        found.append(f"{'/'.join(rel.with_suffix('').parts[-2:])}:{frame.function}")
        if len(found) == depth:
            break
    return " < ".join(found) or "?"


def _frame_local(name: str) -> Any:
    for frame in inspect.stack()[2:]:
        if name in frame.frame.f_locals:
            return frame.frame.f_locals[name]
    return None


def _fill(annotation: Any) -> Any:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Literal:
        return args[0]
    if origin in (typing.Union, types.UnionType):
        return _fill(next(a for a in args if a is not type(None)))
    if origin in (list, tuple, set, frozenset):
        return []
    if origin is dict:
        return {}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return sample(annotation)
    return {str: "x", int: 0, float: 0.0, bool: False}.get(annotation)


def sample(schema: type[BaseModel]) -> dict[str, Any]:
    """The least JSON ``schema`` accepts: its defaults, and a filler for each required field."""
    return {
        name: _fill(info.annotation)
        for name, info in schema.model_fields.items()
        if info.is_required()
    }


def _call(name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"call_{name}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }
    ]


def _response(content: str | None, tool_calls: list[dict[str, Any]] | None = None) -> Any:
    calls = [
        types.SimpleNamespace(
            id=call["id"],
            type="function",
            function=types.SimpleNamespace(**call["function"]),
            model_dump=lambda call=call: call,
        )
        for call in tool_calls or []
    ]
    message = types.SimpleNamespace(content=content, tool_calls=calls or None)
    finish = "tool_calls" if calls else "stop"
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=message, finish_reason=finish)],
        usage=types.SimpleNamespace(prompt_tokens=400, completion_tokens=40),
    )


def _chunk(delta: Any, finish: str | None = None, usage: Any = None) -> Any:
    choices = [] if delta is None else [types.SimpleNamespace(delta=delta, finish_reason=finish)]
    return types.SimpleNamespace(choices=choices, usage=usage)


class _Stream:
    """A provider stream: the reply word by word, or one tool call; then its usage."""

    def __init__(self, text: str, call: list[dict[str, Any]] | None = None) -> None:
        self._text = text
        self._call = call

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._chunks()

    async def _chunks(self) -> AsyncIterator[Any]:
        if self._call:
            [call] = self._call
            piece = types.SimpleNamespace(
                index=0, id=call["id"], function=types.SimpleNamespace(**call["function"])
            )
            delta = types.SimpleNamespace(content=None, reasoning_content=None, tool_calls=[piece])
            yield _chunk(delta, "tool_calls")
            return
        for index, word in enumerate(self._text.split(" ")):
            content = word if index == 0 else f" {word}"
            yield _chunk(types.SimpleNamespace(content=content, tool_calls=None))
        usage = types.SimpleNamespace(prompt_tokens=1200, completion_tokens=80)
        yield _chunk(None, usage=usage)

    async def aclose(self) -> None:
        return None


def fake_acompletion(ledger: Ledger) -> Callable[..., Any]:
    """``litellm_gateway.acompletion``: counted, answered by the kind of call."""

    async def acompletion(**kwargs: Any) -> Any:
        if ledger.counting:
            ledger.models.append(callers())
        tools = kwargs.get("tools") or []
        offered = {tool["function"]["name"] for tool in tools}
        wanted = ledger.tool_call if ledger.tool_call and ledger.tool_call[0] in offered else None
        if kwargs.get("stream"):
            answered = any(m.get("role") == "tool" for m in kwargs.get("messages") or [])
            if wanted is not None and not answered:
                return _Stream("", _call(*wanted))
            return _Stream(ledger.reply)
        if tools:
            none = next(name for name in offered if name.endswith("no_tool_needed"))
            return _response(None, _call(*wanted) if wanted else _call(none, {}))
        if kwargs.get("response_format"):
            schema = _frame_local("schema")
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                answer = ledger.structured.get(schema.__name__)
                body = (answer() if callable(answer) else answer) or sample(schema)
                return _response(json.dumps(body))
            return _response("{}")
        return _response("Capital of France")

    return acompletion


def fake_aembedding(ledger: Ledger) -> Callable[..., Any]:
    """``embedding_gateway.aembedding``: counted per request, with its input count."""

    async def aembedding(**kwargs: Any) -> Any:
        inputs = kwargs.get("input") or []
        if ledger.counting:
            ledger.embeds.append(len(inputs))
        return types.SimpleNamespace(
            data=[{"index": i, "embedding": _VECTOR} for i in range(len(inputs))],
            usage=types.SimpleNamespace(prompt_tokens=10 * len(inputs), completion_tokens=0),
        )

    return aembedding
