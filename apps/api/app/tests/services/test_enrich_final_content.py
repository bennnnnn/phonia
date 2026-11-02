"""Live done.final_content must match the string we persist."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules import todos as todos_service
from app.modules import web_search as web_search_service
from app.modules.chat.finalize_passes import enrich_final_content
from app.modules.chat.prompt_constants import MERMAID_FORMAT_HINT
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.conversation import chats_repository as chats_repo
from app.modules.todos import repository as todos_repo
from app.modules.todos.prompt_hint import TODO_HINT
from app.modules.web_search.formatting import format_sources_fence
from app.repositories import users as users_repo
from app.services.answer_fence import mark_server_answer_fences
from app.services.solving import VERIFIED_PHYSICS_END, VerifiedPhysicsBlock
from app.tests.modules.chat.chat_test_support import turn_deps

_CARD = re.compile(r"```reminder_proposal\n(.*?)\n```", re.DOTALL)
_MERMAID_REPLY = "```mermaid\nflowchart TD\n  D --> E[Grind Beans (Medium Grind)]\n```"


def _fail_mermaid_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pure text pass late in finalize raises (any of them could)."""

    def _boom(_text: str) -> str:
        raise RuntimeError("mermaid sanitizer failed")

    monkeypatch.setattr("app.modules.chat.finalize_text.sanitize_mermaid_fences", _boom)


def _passthrough_math(
    content: str, verified: object = None, correct: bool = True, user_text: str = ""
) -> str:
    return content


async def _run_sympy_inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


@asynccontextmanager
async def _fake_session() -> Any:
    yield MagicMock()


def _deps() -> Any:
    async def _passthrough_reminders(_session: object, **kwargs: Any) -> tuple[str, int]:
        return str(kwargs["assistant_text"]), 0

    todos = MagicMock()
    todos.materialize_reminder_fences = AsyncMock(side_effect=_passthrough_reminders)
    math_fence = MagicMock()
    math_fence.check = _passthrough_math
    math_fence.recover = lambda content, _verified: content
    return turn_deps(
        session_factory=_fake_session,
        users=MagicMock(get_by_id=AsyncMock(return_value=MagicMock())),
        todos=todos,
        math_fence=math_fence,
        web_search=web_search_service,
    )


def _ctx(
    *, search_sources: list[WebSearchHit] | None = None, local_places: bool = False
) -> MagicMock:
    ctx = MagicMock()
    ctx.user = MagicMock()
    ctx.user.timezone = "UTC"
    ctx.user_timezone = "UTC"
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.search_sources = search_sources or []
    ctx.verified_subject = None
    ctx.local_places = local_places
    ctx.skip_memory_jobs = False
    ctx.instant_reply = None
    ctx.user_message_content = "what's the news"
    ctx.solver_unverified = False
    ctx.unverified_subject = None
    ctx.answer_photo = None
    return ctx


async def _finalize_failed_subject_pass(deps: Any, verified: object, reply: str) -> str:
    ctx = _ctx()
    ctx.verified_subject = verified
    return await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=reply,
        usage={"input": 4, "output": 8},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )


@pytest.mark.asyncio
async def test_exception_fallback_dispatches_to_chemistry_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.chemistry import fence as chemistry_fence
    from app.modules.chemistry.block import build_verified_chemistry
    from app.modules.chemistry.extract import extract_chemistry_intent

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    math_safe = MagicMock(return_value="math-safe")
    deps.math_fence.recover = math_safe
    intent = extract_chemistry_intent("Find pH when [H+] = 0.001")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    validate = chemistry_fence.validate_chemistry_fences
    calls: list[str] = []

    def fail_the_pass(content: str, *args: Any, **kwargs: Any) -> str:
        """The chemistry pass fails; its recovery's own check runs for real."""
        calls.append(content)
        if len(calls) == 1:
            raise RuntimeError("chemistry fence pass failed")
        return validate(content, *args, **kwargs)

    monkeypatch.setattr(chemistry_fence, "validate_chemistry_fences", fail_the_pass)

    result = await _finalize_failed_subject_pass(deps, verified, "```answer\n4\n```")

    assert len(calls) == 2
    assert "notation: chemistry\npH = 3" in result
    assert "```answer\n4\n```" not in result
    math_safe.assert_not_called()


@pytest.mark.asyncio
async def test_exception_fallback_dispatches_to_physics_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    math_safe = MagicMock(return_value="math-safe")
    deps.math_fence.recover = math_safe
    verified = VerifiedPhysicsBlock(text="verified", canonical_answer="10 N")
    monkeypatch.setattr(
        "app.modules.physics.fence.validate_physics_fences",
        MagicMock(side_effect=RuntimeError("physics fence pass failed")),
    )
    safe = MagicMock(return_value="physics-safe")
    monkeypatch.setattr(
        "app.modules.physics.fence.replace_unclosed_physics_fences_safe",
        safe,
    )

    result = await _finalize_failed_subject_pass(deps, verified, "raw")

    assert result == "physics-safe"
    safe.assert_called_once_with("raw", verified)
    math_safe.assert_not_called()


@pytest.mark.asyncio
async def test_reminder_finalization_uses_effective_client_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    ctx = _ctx()
    ctx.user.timezone = "UTC"
    ctx.user_timezone = "America/Los_Angeles"
    ctx.user_message_content = "Remind me tomorrow at 3 PM to submit my application."

    await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text="I'll help with that.",
        usage={"input": 1, "output": 2},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=["I'll help with that."],
        should_cancel=None,
    )

    kwargs = deps.todos.materialize_reminder_fences.await_args.kwargs
    assert kwargs["user_timezone"] == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_search_sources_final_content_matches_persisted_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Appending ```sources used to update persist only; done.final_content
    stayed stripped. Mobile then saw a different string live vs on reload."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)

    hits = [
        WebSearchHit(
            title="Example Source",
            url="https://example.com/a",
            snippet="A snippet about the topic.",
        )
    ]
    prose = "Here is the latest on the topic."
    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(search_sources=hits),
        assistant_text=prose,
        usage={"input": 10, "output": 20},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[prose],
        should_cancel=None,
    )

    expected_fence = format_sources_fence(hits)
    assert persisted == f"{prose}{expected_fence}".strip()
    assert outcome.final_content == persisted
    assert "```sources" in outcome.final_content
    assert "https://example.com/a" in [source["url"] for source in outcome.search_sources]


@pytest.mark.asyncio
async def test_unchanged_turn_omits_final_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text="Plain answer.",
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=["Plain answer."],
        should_cancel=None,
    )

    assert persisted == "Plain answer."
    assert outcome.final_content is None


@pytest.mark.asyncio
async def test_cancelled_turn_closes_unclosed_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)

    outcome = TurnOutcome()
    open_fence = "```mermaid\ngraph TD\n  A-->B"
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=open_fence,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=True,
        assistant_parts=[open_fence],
        should_cancel=None,
    )

    assert persisted.rstrip().endswith("```")
    assert "Generation stopped" not in persisted
    assert outcome.final_content == persisted


@pytest.mark.asyncio
async def test_truncated_turn_closes_unclosed_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)

    outcome = TurnOutcome()
    open_fence = "```python\nprint(1"
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=open_fence,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[open_fence],
        should_cancel=None,
    )

    assert persisted.rstrip().endswith("```")
    assert "Generation stopped" not in persisted


@pytest.mark.asyncio
async def test_normal_completion_also_closes_provider_unclosed_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider can emit done normally while forgetting the final backticks."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)

    outcome = TurnOutcome()
    open_fence = "```message\nHappy birthday! Hope you have a wonderful day."
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=open_fence,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[open_fence],
        should_cancel=None,
    )

    assert persisted.rstrip().endswith("```")
    assert outcome.final_content == persisted


@pytest.mark.asyncio
async def test_mermaid_parenthetical_labels_quoted_on_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)

    outcome = TurnOutcome()
    raw = "```mermaid\nflowchart TD\n  D --> E[Grind Beans (Medium Grind)]\n```"
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=raw,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[raw],
        should_cancel=None,
    )

    assert 'E["Grind Beans (Medium Grind)"]' in persisted
    assert MERMAID_FORMAT_HINT not in persisted


@pytest.mark.asyncio
async def test_verified_math_markers_are_stripped_from_final_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stripper must actually run in the pipeline, not just exist.

    Every other test asserts these markers are present in the *prompt*. This
    one asserts the post-stream path removes them from what is persisted and
    shown, since instruction alone never stopped a model echoing them.
    """
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=(
            "[BEGIN VERIFIED MATH]\nVerified result: 2.02 s\n[END VERIFIED MATH]\n\n"
            "So it lands after about 2 seconds."
        ),
        usage={"input": 1, "output": 2},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=["ignored"],
        should_cancel=None,
    )

    assert "BEGIN VERIFIED" not in persisted
    assert VERIFIED_PHYSICS_END not in persisted
    assert "So it lands after about 2 seconds." in persisted


@pytest.mark.asyncio
async def test_unverified_math_note_appended_to_final_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.math import fence as math_fence_mod

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    deps.math_fence.append_unverified_math_note = math_fence_mod.append_unverified_math_note
    ctx = _ctx()
    ctx.solver_unverified = True
    persisted = await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text="The mass is 12 kg.",
        usage={"input": 1, "output": 2},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=["The mass is 12 kg."],
        should_cancel=None,
    )
    assert persisted == "The mass is 12 kg."
    assert "*I couldn't automatically verify this result.*" not in persisted
    assert "\n>" not in persisted
    assert "```answer" not in persisted


@pytest.mark.asyncio
async def test_unverified_chemistry_uses_the_chemistry_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    ctx = _ctx()
    ctx.solver_unverified = True
    ctx.unverified_subject = "chemistry"
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=True),
        ctx,
        assistant_text="The pH is about 6.",
        usage={"input": 1, "output": 2},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=["The pH is about 6."],
        should_cancel=None,
    )
    assert persisted == "The pH is about 6."
    assert "Chemistry note:" not in persisted
    assert "*I couldn't automatically verify this result.*" not in persisted


@pytest.mark.asyncio
async def test_direct_verified_math_skips_sympy_pool_for_fence_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.solving import VerifiedMathBlock

    async def _must_not_run(*_a: Any, **_k: Any) -> str:
        raise AssertionError("direct math must not queue fence rewrite on the pool")

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _must_not_run)
    ctx = _ctx()
    ctx.instant_reply = "$x = 2$\n\n```answer\nx = 2\n```"
    ctx.verified_subject = VerifiedMathBlock(
        text="verified",
        canonical_fence={"type": "answer", "content": "x = 2"},
        canonical_answer="x = 2",
    )
    ctx.user_message_content = "1+1=x"
    ctx.solver_unverified = False
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=ctx.instant_reply,
        usage={"input": 0, "output": 8},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[ctx.instant_reply],
        should_cancel=None,
    )
    # The instant reply is the server's own text: it persists with its card marked.
    assert persisted == mark_server_answer_fences(ctx.instant_reply)


@pytest.mark.asyncio
async def test_paired_direct_reply_keeps_both_answer_fences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.subjects.registry import subject_adapter

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    deps.math_fence.needs_check = subject_adapter("math").fence.needs_check
    deps.math_fence.check = subject_adapter("math").fence.check
    reply = (
        "**Answer**\n\n```answer\nnotation: chemistry\nV₂ = 100 mL\n```\n\n"
        "**Answer**\n\n```answer\nx = 3 \\text{ or } x = 4\n```\n"
    )
    ctx = _ctx()
    ctx.instant_reply = reply
    ctx.verified_subject = None
    ctx.user_message_content = (
        "Dilute 25 mL of 1 M NaOH to 0.25 M, and also solve x^2 - 7x + 12 = 0."
    )
    persisted = await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=True),
        ctx,
        assistant_text=reply,
        usage={"input": 0, "output": 0},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )
    assert persisted.count("```answer") == 2
    assert "notation: chemistry\nV₂ = 100 mL" in persisted
    assert "x = 3 \\text{ or } x = 4" in persisted


@pytest.mark.asyncio
async def test_verified_chemistry_replaces_model_answer_without_math_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.chemistry.block import build_verified_chemistry
    from app.modules.chemistry.extract import extract_chemistry_intent

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    deps.math_fence.check = MagicMock(
        side_effect=AssertionError("math fences must not rewrite chemistry")
    )
    question = "Find pH when [H+] = 0.001"
    intent = extract_chemistry_intent(question)
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    ctx = _ctx()
    ctx.verified_subject = verified
    ctx.user_message_content = question
    invented = "The pH is 4.\n\n```answer\n4\n```\n\n```smiles\nCCO\n```"
    persisted = await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=True),
        ctx,
        assistant_text=invented,
        usage={"input": 1, "output": 2},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[invented],
        should_cancel=None,
    )
    assert persisted.count("```answer") == 1
    assert "notation: chemistry\npH = 3" in persisted
    assert "```smiles" not in persisted
    assert "```answer\n4\n```" not in persisted


PHOTO_REPLY = "```photo\nEthiopia location map\n```\n\nEthiopia lies in the Horn of Africa."


@pytest.mark.asyncio
async def test_answer_photo_replaces_its_fence_in_final_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.images import answer_photo

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    photo_id = uuid4()
    monkeypatch.setattr(
        answer_photo.image_search, "photos_for_answer", AsyncMock(return_value=[photo_id])
    )
    ctx = _ctx()
    ctx.answer_photo = answer_photo.AnswerPhoto(Settings(), MagicMock())
    ctx.answer_photo.feed(PHOTO_REPLY)

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=PHOTO_REPLY,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[PHOTO_REPLY],
        should_cancel=None,
    )

    assert persisted.startswith(f"[Image: /attachments/{photo_id}/file]\n\nEthiopia lies")
    assert "```photo" not in persisted
    assert outcome.final_content == persisted
    assert ctx.answer_photo_ids == [photo_id]


@pytest.mark.asyncio
async def test_stopped_reply_drops_its_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    ctx = _ctx()
    ctx.answer_photo = MagicMock()
    ctx.answer_photo_ids = []

    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=PHOTO_REPLY,
        usage={"input": 4, "output": 8},
        outcome=TurnOutcome(),
        was_cancelled=True,
        assistant_parts=[PHOTO_REPLY],
        should_cancel=None,
    )

    assert persisted == "Ethiopia lies in the Horn of Africa."
    ctx.answer_photo.cancel.assert_called_once()
    assert ctx.answer_photo_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unverified", "reply", "noted"),
    [
        # A worked reply the server could not verify: its slip is named.
        (True, "**Substitution**\n$a = 3.2 \\times 4.5 = 14.8$\n\n**Answer**\n$14.8$", True),
        # A worked solution with no subject detected is checked too.
        (False, "**Steps**\n$12 \\times 3 = 38$\n\n**Answer**\n$38$", True),
        # Right working, or arithmetic outside a worked solution, adds nothing.
        (True, "**Substitution**\n$a = 3.2 \\times 4.5 = 14.4$\n\n**Answer**\n$14.4$", False),
        (False, "Is $3 \\times 4 = 13$? No, it's 12.", False),
    ],
)
async def test_unverified_working_names_its_first_slip(
    monkeypatch: pytest.MonkeyPatch, unverified: bool, reply: str, noted: bool
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    ctx = _ctx()
    ctx.solver_unverified = unverified
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=reply,
        usage={"input": 1, "output": 2},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )
    assert ("Check this step:" in persisted) is noted


# --- ES-03: a failed text pass never throws away a side effect that already happened ---------

_DENTIST_ASK = "add dentist tomorrow at 3pm to my reminders"


async def _reminder_turn(
    db_session: Any, fake_redis: Any, reply: str, *, was_cancelled: bool = False
) -> tuple[str, TurnOutcome, list[Any], Any]:
    """Finalize ``reply`` to ``_DENTIST_ASK`` with the real reminder pass on Postgres."""
    user = await users_repo.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")

    @asynccontextmanager
    async def _session() -> Any:
        yield db_session

    deps = replace(_deps(), session_factory=_session, todos=todos_service)
    ctx = _ctx()
    ctx.user_id = user.id
    ctx.chat_id = chat.id
    ctx.user_message_content = _DENTIST_ASK
    ctx.prompt_messages = [{"role": "user", "content": _DENTIST_ASK}]

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        deps,
        fake_redis,
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=reply,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=was_cancelled,
        assistant_parts=[reply],
        should_cancel=None,
    )
    rows = await todos_repo.list_for_user(db_session, user.id, limit=10)
    return persisted, outcome, rows, user


@pytest.mark.asyncio
@pytest.mark.parametrize("text_pass_fails", [False, True], ids=["passes ok", "text pass fails"])
async def test_a_failed_text_pass_keeps_the_reminder_card(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Any,
    fake_redis: Any,
    text_pass_fails: bool,
) -> None:
    """A text pass that failed after the reminder pass persisted the raw reply: the card
    was lost while its proposal sat in Redis."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    if text_pass_fails:
        _fail_mermaid_pass(monkeypatch)
    due = (datetime.now(UTC) + timedelta(days=1)).replace(hour=15, minute=0, second=0)
    fence = json.dumps({"title": "Dentist", "due_at": due.isoformat()})
    reply = f"Good idea to book early. I'll set a reminder.\n\n```reminder\n{fence}\n```"

    persisted, outcome, rows, user = await _reminder_turn(db_session, fake_redis, reply)

    assert persisted.startswith("Good idea to book early.")
    # A card waits for the tap, so the model's "I'll set a reminder" goes with it.
    assert "I'll set a reminder" not in persisted
    assert TODO_HINT not in persisted
    assert outcome.final_content == persisted
    # Nothing is written yet: the list refreshes on the tap.
    assert outcome.todos_changed is False
    card = _CARD.search(persisted)
    assert card is not None, persisted
    assert json.loads(card.group(1))["items"][0]["title"] == "Dentist"
    assert await fake_redis.keys(f"todos:proposal:{user.id}:*")
    assert rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("was_cancelled", [True, False], ids=["stopped", "stream dropped"])
async def test_a_reply_cut_inside_its_reminder_fence_still_offers_the_card(
    monkeypatch: pytest.MonkeyPatch, db_session: Any, fake_redis: Any, was_cancelled: bool
) -> None:
    """An open fence is never applied, even though finalize closes open fences
    before the reminder pass: the user's own words still make the card."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    reply = 'Sure, I\'ll set a reminder.\n\n```reminder\n{"title": "Den'

    persisted, _outcome, rows, _user = await _reminder_turn(
        db_session, fake_redis, reply, was_cancelled=was_cancelled
    )

    card = _CARD.search(persisted)
    assert card is not None, persisted
    assert json.loads(card.group(1))["items"][0]["title"].lower() == "dentist"
    assert "Could not save" not in persisted
    assert TODO_HINT not in persisted
    assert rows == []


@pytest.mark.asyncio
async def test_a_failed_reminder_pass_keeps_the_finished_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every text pass already succeeded, so their work persists, not the raw reply."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    deps = _deps()
    deps.todos.materialize_reminder_fences = AsyncMock(side_effect=RuntimeError("db"))

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=_MERMAID_REPLY,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[_MERMAID_REPLY],
        should_cancel=None,
    )

    assert 'E["Grind Beans (Medium Grind)"]' in persisted
    assert outcome.final_content == persisted
    assert not outcome.todos_changed


@pytest.mark.asyncio
async def test_a_failed_text_pass_keeps_the_attached_answer_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.images import answer_photo

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    _fail_mermaid_pass(monkeypatch)
    photo_id = uuid4()
    monkeypatch.setattr(
        answer_photo.image_search, "photos_for_answer", AsyncMock(return_value=[photo_id])
    )
    ctx = _ctx()
    ctx.answer_photo = answer_photo.AnswerPhoto(Settings(), MagicMock())
    ctx.answer_photo.feed(PHOTO_REPLY)

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        ctx,
        assistant_text=PHOTO_REPLY,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[PHOTO_REPLY],
        should_cancel=None,
    )

    assert persisted.startswith(f"[Image: /attachments/{photo_id}/file]\n\nEthiopia lies")
    assert "```photo" not in persisted
    assert outcome.final_content == persisted
    assert ctx.answer_photo_ids == [photo_id]


@pytest.mark.asyncio
async def test_a_failed_text_pass_keeps_the_source_chips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``done`` already carries the sources, so the saved reply keeps their fence."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    _fail_mermaid_pass(monkeypatch)
    hits = [
        WebSearchHit(
            title="Example Source",
            url="https://example.com/a",
            snippet="A snippet about the topic.",
        )
    ]
    prose = "Here is the latest on the topic."

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(search_sources=hits),
        assistant_text=prose,
        usage={"input": 10, "output": 20},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[prose],
        should_cancel=None,
    )

    assert persisted == f"{prose}{format_sources_fence(hits)}".strip()
    assert outcome.final_content == persisted
    assert "https://example.com/a" in [source["url"] for source in outcome.search_sources]


@pytest.mark.asyncio
async def test_a_failed_text_pass_before_any_side_effect_persists_the_raw_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing committed, the text passes are all or nothing."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    _fail_mermaid_pass(monkeypatch)

    outcome = TurnOutcome()
    persisted = await enrich_final_content(
        _deps(),
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=_MERMAID_REPLY,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=False,
        assistant_parts=[_MERMAID_REPLY],
        should_cancel=None,
    )

    assert persisted == _MERMAID_REPLY
    assert outcome.final_content is None
