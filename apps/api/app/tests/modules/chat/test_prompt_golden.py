"""Golden prompts: ``build_prompt_messages`` returns these messages, byte for byte.

``golden/prompt_messages.json`` holds one battery case per category, recorded on the
real turn path (``behavior/harness.py``), and ``branch:`` turns. Together they reach
every line and branch of ``build_prompt_messages``, ``_style_format_hints`` and their
helpers. A case stores only what differs from ``defaults``. A message is a list of
tokens joined with nothing between: ``@NAME`` is that prompt constant's text (from
``_COPY_MODULES`` and the modules of ``_COPY_PACKAGES``), a number is a piece of ``texts``. Rewording a named constant leaves
the fixture as it is; a change to which text a turn gets, or its order, fails here.

An intended prompt change means regenerating with this command and reviewing the diff:

    uv run python -m app.tests.modules.chat.test_prompt_golden
"""

from __future__ import annotations

import asyncio
import difflib
import importlib
import json
import pkgutil
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.core.config import Settings
from app.models.orm import Chat, User
from app.modules.chat.prompt_builder import PromptStats, build_prompt_messages
from app.modules.chat.prompt_context import _PromptContextBlocks
from app.modules.chat.turn_prep.intents import plan_turn
from app.tests.behavior.cases import CASES, CATEGORIES
from app.tests.behavior.sweep import frozen_clock

GOLDEN = Path(__file__).with_name("golden") / "prompt_messages.json"
CHAT_ID = UUID(int=0xC4A7)
USER_ID = UUID(int=0x05E5)
# Gap rows (older than the recent window) are numbered after the window's rows.
_OLDER_FIRST_ID = 10_000
_T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
# Where the named prompt copy comes from; shorter strings stay in ``texts``.
_COPY_MODULES = (
    "app.modules.chat.prompt_constants",
    "app.modules.web_search",
    "app.modules.math.reply_policy",
    "app.modules.math.followup",
    "app.modules.physics.reply_policy",
    "app.modules.physics.followup",
    "app.modules.chemistry.reply_policy",
    "app.modules.chemistry.followup",
    "app.modules.chat.response_tone",
)
# Packages whose every module is read too: a constant counts whether or not the
# package re-exports it.
_COPY_PACKAGES = ("app.modules.chat.prompt_constants",)
_MIN_COPY_CHARS = 60

Case = dict[str, Any]


class _Session:
    async def __aenter__(self) -> AsyncMock:
        return AsyncMock()

    async def __aexit__(self, *_args: object) -> None:
        return None


def _rows(pairs: list[list[str]], *, first_id: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=UUID(int=first_id + index),
            role=role,
            content=content,
            created_at=_T0 + timedelta(minutes=first_id + index),
        )
        for index, (role, content) in enumerate(pairs)
    ]


def _row_id(index: int) -> UUID:
    """History row ``index`` as ``_rows`` numbers it; -1 is an id no row has."""
    return UUID(int=1 + index)


def resolve(case: Case, defaults: Case) -> Case:
    """The case's full inputs: its overrides on top of the file's defaults."""
    full = {**defaults, **case}
    for nested in ("user", "settings", "kwargs"):
        full[nested] = {**defaults[nested], **case.get(nested, {})}
    return full


async def render(case: Case) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Run the real builder on resolved inputs, with only IO and the clock stubbed."""
    history = _rows(case["history"], first_id=1)
    older = _rows(case["older"], first_id=_OLDER_FIRST_ID)
    chat = Chat(id=CHAT_ID, user_id=USER_ID, **case["chat"]) if case["chat"] is not None else None
    blocks = _PromptContextBlocks(
        memory_block=case["memory_block"],
        todos_section=case["todos_section"],
        recent_all=history,
        attachment_rag_block=case["attachment_rag_block"],
        chat=chat,
        history_rag_query_vec=[0.0] if case["history_rag_vec"] else None,
    )
    kwargs = dict(case["kwargs"])
    omit = kwargs.pop("omit", None)
    current = kwargs.pop("current", None)
    # "plan": the turn's separate requests, as turn prep plans them (``turn_prep.intents``).
    if kwargs.pop("plan", False):
        kwargs["turn_plan"] = plan_turn(kwargs["query_text"])
    user = User(id=USER_ID, **case["user"])
    settings = Settings(_env_file=None, **case["settings"])  # type: ignore[call-arg]
    stats = PromptStats()
    stubs = {
        "app.modules.chat.prompt_builder._load_context_blocks": AsyncMock(return_value=blocks),
        "app.modules.attachments.rag.SessionLocal": _Session,
        "app.modules.chat.prompt_context.SessionLocal": _Session,
        # "error": the attachment-chunk probe fails, and the turn goes on without it.
        "app.modules.attachments.service.chat_has_document_chunks": AsyncMock(
            side_effect=RuntimeError("probe") if case["has_chunks"] == "error" else None,
            return_value=case["has_chunks"],
        ),
        "app.modules.conversation.messages_repository.count_for_chat": AsyncMock(
            return_value=case["total"]
        ),
        "app.modules.conversation.messages_repository.list_before": AsyncMock(return_value=older),
        "app.modules.conversation.history_rag.retrieve_for_prompt": AsyncMock(
            return_value=case["history_rag_block"]
        ),
    }
    with frozen_clock(), ExitStack() as stack:
        for target, value in stubs.items():
            stack.enter_context(patch(target, value))
        messages = await build_prompt_messages(
            user,
            CHAT_ID,
            settings,
            chat=chat,
            stats=stats,
            omit_message_ids={_row_id(i) for i in omit} if omit is not None else None,
            current_user_message_id=_row_id(current) if current is not None else None,
            **kwargs,
        )
    # Recorded as ``out``: the stats the prompt filled in (none but a summary here).
    return messages, {name: value for name, value in asdict(stats).items() if value}


def prompt_copy() -> dict[str, str]:
    """Name -> text of each long string constant (``NAME[key]`` in a dict of them)."""
    copy: dict[str, str] = {}
    package_modules = [
        f"{package}.{info.name}"
        for package in _COPY_PACKAGES
        for info in sorted(
            pkgutil.iter_modules(importlib.import_module(package).__path__),
            key=lambda info: info.name,
        )
    ]
    for module_name in (*_COPY_MODULES, *package_modules):
        module = importlib.import_module(module_name)
        for name in sorted(dir(module)):
            value = getattr(module, name)
            if name.startswith("_") or not name.isupper():
                continue
            if isinstance(value, str):
                items = {name: value}
            elif isinstance(value, dict):
                items = {f"{name}[{k}]": v for k, v in value.items() if isinstance(v, str)}
            else:
                continue
            for key, text in sorted(items.items()):
                if len(text) >= _MIN_COPY_CHARS:
                    copy.setdefault(key, text)
    return copy


def load_golden() -> tuple[Case, list[str], list[Case]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return data["defaults"], data["texts"], data["cases"]


def expected_of(texts: list[str], case: Case) -> list[dict[str, str]]:
    copy = prompt_copy()

    def text_of(token: str) -> str:
        return copy[token[1:]] if token.startswith("@") else texts[int(token)]

    return [
        {"role": role, "content": "".join(text_of(token) for token in tokens.split(" "))}
        for role, tokens in case["expected"]["messages"]
    ]


async def write_golden(defaults: Case, cases: list[Case]) -> None:
    """Render every case with the current code and store that as its expected output."""
    named = sorted(prompt_copy().items(), key=lambda item: (-len(item[1]), item[0]))
    texts: list[str] = []
    index_of: dict[str, int] = {}

    def piece(text: str) -> str:
        if text not in index_of:
            index_of[text] = len(texts)
            texts.append(text)
        return str(index_of[text])

    def encode(text: str) -> str:
        # Longest constants first, so a hint built from others is one token.
        spans: list[tuple[int, int, str]] = []
        for name, value in named:
            start = text.find(value)
            while start != -1:
                end = start + len(value)
                if all(end <= a or start >= b for a, b, _ in spans):
                    spans.append((start, end, name))
                start = text.find(value, start + 1)
        tokens, at = [], 0
        for start, end, name in sorted(spans):
            if start > at:
                tokens.append(piece(text[at:start]))
            tokens.append(f"@{name}")
            at = end
        if at < len(text) or not tokens:
            tokens.append(piece(text[at:]))
        return " ".join(tokens)

    stored = []
    for case in cases:
        messages, out = await render(resolve(case, defaults))
        expected = {"messages": [[m["role"], encode(m["content"])] for m in messages], "out": out}
        stored.append({**{k: v for k, v in case.items() if k != "expected"}, "expected": expected})
    data = {"defaults": defaults, "texts": texts, "cases": stored}
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _difference(want: list[dict[str, str]], got: list[dict[str, str]]) -> str:
    lines = difflib.unified_diff(
        [f"[{m['role']}] {line}" for m in want for line in m["content"].splitlines()],
        [f"[{m['role']}] {line}" for m in got for line in m["content"].splitlines()],
        "golden",
        "built",
        lineterm="",
        n=1,
    )
    return "\n".join(list(lines)[:60])


_DEFAULTS, _TABLE, _CASES = load_golden() if GOLDEN.is_file() else ({}, [], [])


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
async def test_prompt_matches_golden(case: Case) -> None:
    messages, out = await render(resolve(case, _DEFAULTS))
    want = expected_of(_TABLE, case)
    assert messages == want, _difference(want, messages)
    assert out == case["expected"]["out"]


def test_golden_has_one_battery_case_per_category() -> None:
    category = {f"battery:{case.id}": case.category for case in CASES}
    battery = [category[case["id"]] for case in _CASES if case["id"] in category]
    assert sorted(battery) == sorted(CATEGORIES)
    assert len({case["id"] for case in _CASES}) == len(_CASES)


if __name__ == "__main__":
    # As pytest runs them: the message readers in-process. The production pool's
    # 3 s reading deadline, missed on a busy machine, recorded a turn that read no
    # subject (a maths case lost its maths pack) with no error.
    from app.core.sympy_executor import set_sympy_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    asyncio.run(write_golden(_DEFAULTS, _CASES))
    print(f"wrote {len(_CASES)} cases to {GOLDEN}")
