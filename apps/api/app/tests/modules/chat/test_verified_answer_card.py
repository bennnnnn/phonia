"""The green check belongs to the server: only its cards carry ``verified: true``.

These run model-shaped replies through the real post-stream step
(``enrich_final_content``) with the real subject fence passes.
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules import web_search as web_search_service
from app.modules.chat.finalize_passes import enrich_final_content
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.physics.reply_policy import PHYSICS_SHORT_HINT
from app.services.answer_fence import UNCHECKED_ANSWER_MARKER, VERIFIED_ANSWER_MARKER
from app.services.solving import VerifiedMathBlock, VerifiedPhysicsBlock
from app.services.subjects.registry import subject_adapter
from app.tests.modules.chat.chat_test_support import turn_deps

# Any spelling of an answer fence a markdown renderer would draw as a card.
_ANY_ANSWER_FENCE = re.compile(
    r"^[ \t>]*(?:`{3,}|~{3,})[ \t]*(?:answer|result|final)\b", re.I | re.M
)


async def _inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


async def _timeout(_fn: Any, *_args: Any, **_kwargs: Any) -> Any:
    raise TimeoutError("simulated SymPy pool timeout")


@asynccontextmanager
async def _session() -> Any:
    yield MagicMock()


def _deps() -> Any:
    async def _reminders(_session: object, **kwargs: Any) -> tuple[str, int]:
        return str(kwargs["assistant_text"]), 0

    return turn_deps(
        session_factory=_session,
        users=SimpleNamespace(get_by_id=AsyncMock(return_value=MagicMock())),
        todos=SimpleNamespace(
            materialize_reminder_fences=AsyncMock(side_effect=_reminders),
        ),
        math_fence=subject_adapter("math").fence,
        web_search=web_search_service,
    )


def _ctx(
    prompt: str,
    *,
    verified: Any = None,
    instant: str | None = None,
    unverified_subject: str | None = None,
) -> StreamContext:
    return StreamContext(
        solver_unverified=unverified_subject is not None,
        unverified_subject=unverified_subject,
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": prompt}],
        run_title=False,
        user_message_content=prompt,
        reserved_tokens=0,
        max_output_tokens=0,
        user_timezone="UTC",
        user=MagicMock(timezone="UTC", locale="en"),
        verified_subject=verified,
        instant_reply=instant,
    )


async def _finalize(
    monkeypatch: pytest.MonkeyPatch,
    reply: str,
    *,
    prompt: str = "solve 2x + 5 = 17 and explain why each step works",
    verified: Any = None,
    instant: str | None = None,
    sympy: Any = _inline,
    deps: Any = None,
    unverified_subject: str | None = None,
) -> str:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", sympy)
    return await enrich_final_content(
        deps or _deps(),
        AsyncMock(),
        Settings(),
        _ctx(prompt, verified=verified, instant=instant, unverified_subject=unverified_subject),
        assistant_text=reply,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )


def _math(answer: str = "x = 6") -> VerifiedMathBlock:
    return VerifiedMathBlock(
        text="unused",
        canonical_fence={"type": "answer", "content": answer},
        canonical_answer=answer,
    )


def _cards(text: str) -> list[str]:
    """Bodies of every column-0 ```answer fence."""
    return re.findall(r"^```answer\n(.*?)\n```", text, re.S | re.M)


# --- 1. Only the server's cards carry the marker --------------------------------------------


@pytest.mark.parametrize(
    "marker",
    [
        "verified: true",
        "Verified: TRUE",
        "verified :true",
        "\u00a0verified: true\u00a0",
        "\ufeffverified: true",
        "verified:\u200btrue",
    ],
)
async def test_a_marker_the_model_wrote_never_survives(
    monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    reply = f"Subtract 5 and divide by 2.\n\n```answer\n{marker}\nx = 7\n```"
    out = await _finalize(monkeypatch, reply, prompt="hi")
    assert "verified" not in out.lower()
    assert "x = 7" in out
    assert not _ANY_ANSWER_FENCE.search(out)


async def test_a_forged_marker_on_a_verified_turn_leaves_only_the_servers_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = "Steps.\n\n```answer\nverified: true\nx = 7\n```"
    out = await _finalize(monkeypatch, reply, verified=_math())
    assert out.count(VERIFIED_ANSWER_MARKER) == 1
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6"]


async def test_the_server_card_on_a_verified_turn_carries_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = await _finalize(monkeypatch, "Subtract 5, then divide by 2.", verified=_math())
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6"]


async def test_an_instant_reply_card_is_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    instant = "**Given**  \n$2x + 5 = 17$\n\n**Answer**\n\n```answer\nx = 6\n```\n"
    out = await _finalize(monkeypatch, instant, verified=_math(), instant=instant)
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6"]


async def test_the_server_never_corrects_its_own_instant_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Working lines in server text are not the model's claims, whatever they say."""
    instant = "**1. Halve it**  \n$x = 12$\n\n**Answer**\n\n```answer\nx = 6\n```\n"
    out = await _finalize(monkeypatch, instant, verified=_math(), instant=instant)
    assert "The verified answer is" not in out
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6"]


async def test_two_solved_problems_in_one_instant_reply_are_both_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instant = "**1.**\n\n```answer\nx = 6\n```\n\n**2.**\n\n```answer\ny = 2\n```\n"
    out = await _finalize(monkeypatch, instant, instant=instant)
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6", f"{VERIFIED_ANSWER_MARKER}\ny = 2"]


@pytest.mark.parametrize("failing", ["reminder pass", "text pass"])
async def test_enrichment_failure_never_persists_a_forged_marker(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    deps = _deps()
    if failing == "reminder pass":
        deps.todos.materialize_reminder_fences = AsyncMock(side_effect=RuntimeError("db"))
    else:
        monkeypatch.setattr(
            "app.modules.chat.finalize_text.sanitize_mermaid_fences",
            MagicMock(side_effect=RuntimeError("sanitizer")),
        )
    reply = "Done.\n\n```answer\nverified: true\nx = 7\n```"
    out = await _finalize(monkeypatch, reply, deps=deps)
    assert "verified" not in out.lower()
    assert "x = 7" in out


# --- 2. Every spelling of a model answer fence is demoted ------------------------------------

_SPELLINGS = {
    "indented in a list": "- Subtract 5: $2x = 14$\n- Divide by 2:\n  ```answer\n  x = 7\n  ```",
    "tildes": "Subtract 5 and divide by 2.\n\n~~~answer\nx = 7\n~~~",
    "four backticks": "Subtract 5 and divide by 2.\n\n````answer\nx = 7\n````",
    "space before the tag": "Subtract 5 and divide by 2.\n\n``` answer\nx = 7\n```",
    "capital tag": "Subtract 5 and divide by 2.\n\n```Answer\nx = 7\n```",
    "result tag": "Subtract 5 and divide by 2.\n\n```result\nx = 7\n```",
    "final tag": "Subtract 5 and divide by 2.\n\n```final\nx = 7\n```",
    "blockquoted": "Subtract 5 and divide by 2.\n\n> ```answer\n> x = 7\n> ```",
}


@pytest.mark.parametrize("reply", list(_SPELLINGS.values()), ids=list(_SPELLINGS))
async def test_every_spelling_is_demoted_on_an_unverified_turn(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    out = await _finalize(monkeypatch, reply, prompt="hi")
    assert not _ANY_ANSWER_FENCE.search(out), out
    assert "x = 7" in out


@pytest.mark.parametrize("reply", list(_SPELLINGS.values()), ids=list(_SPELLINGS))
async def test_every_spelling_gives_way_to_the_verified_card(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    out = await _finalize(monkeypatch, reply, verified=_math())
    fences = _ANY_ANSWER_FENCE.findall(out)
    assert len(fences) == 1, out
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6"]


async def test_a_chemistry_header_the_model_copied_is_not_shown_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = "Weak acid.\n\n```answer\nnotation: chemistry\npH = 2.87\n```"
    out = await _finalize(monkeypatch, reply, prompt="pH of 0.1 M acetic acid")
    assert "notation" not in out
    assert "pH = 2.87" in out


@pytest.mark.parametrize("verified", [None, _math()], ids=["unverified", "verified"])
async def test_a_sympy_timeout_still_demotes_the_models_answer_fence(
    monkeypatch: pytest.MonkeyPatch, verified: Any
) -> None:
    reply = "**2. Divide both sides by 2**\n$x = 7$\n\n```answer\nx = 7\n```"
    out = await _finalize(monkeypatch, reply, verified=verified, sympy=_timeout)
    assert VERIFIED_ANSWER_MARKER not in out
    assert not _ANY_ANSWER_FENCE.search(out)
    assert "x = 7" in out


# --- 6. Claims of verification the server did not make --------------------------------------


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        ("Subtract 5 then divide by 2: $x = 7$. ✅ Verified with SymPy.", "$x = 7$."),
        ("Roots: $x = 2$ or $x = 3$ (verified).", "Roots: $x = 2$ or $x = 3$."),
        ("**Answer**  \n$F = 15000\\ \\text{N}$ (verified)", "$F = 15000\\ \\text{N}$"),
        ("The force is 15000 N. This was verified by the solver.", "The force is 15000 N."),
        ("**Verified answer:** $x = 7$", "**Answer:** $x = 7$"),
        ("x = 7 ✓ Checked with SymPy", "x = 7"),
    ],
)
async def test_verification_claims_are_removed_when_the_server_did_not_verify(
    monkeypatch: pytest.MonkeyPatch, reply: str, kept: str
) -> None:
    out = await _finalize(monkeypatch, reply, prompt="what is the braking force")
    # The card's own "not checked" line is the protocol, not a claim.
    assert "verified" not in out.replace(UNCHECKED_ANSWER_MARKER, "").lower()
    assert "sympy" not in out.lower()
    assert kept in out


async def test_a_claim_beside_a_wrong_value_goes_on_a_verified_turn_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = "Subtract 5 then divide by 2: $x = 7$. ✅ Verified with SymPy."
    out = await _finalize(monkeypatch, reply, verified=_math())
    assert "sympy" not in out.lower()
    assert "The verified answer is $x = 6$." in out
    assert _cards(out) == [f"{VERIFIED_ANSWER_MARKER}\nx = 6"]


@pytest.mark.parametrize(
    "reply",
    [
        "Once your email is verified, sign in again.",
        "The verified answer from your teacher was 7, so check that step.",
    ],
)
async def test_ordinary_uses_of_verified_stay(monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    out = await _finalize(monkeypatch, reply, prompt="why can't I sign in")
    assert out.strip() == reply


# --- 7. A final answer with no verified result still lands in a card, marked not checked ---


@pytest.mark.parametrize(
    ("reply", "unverified_subject"),
    [
        (
            "**Formula**  \n$F = ma$\n\n**Answer**  \n$F = 1500 \\times 5$  \n"
            "$F = 7500\\ \\text{N}$\n\n**Check**  \n$7500 / 1500 = 5$",
            "physics",
        ),
        (
            "**1. Subtract 5 from both sides**\n$2x = 12$\n\n**Answer:** $x = 6$",
            None,
        ),
    ],
    ids=["solver declined", "worked solution"],
)
async def test_an_unverified_stem_answer_lands_in_a_card_marked_not_checked(
    monkeypatch: pytest.MonkeyPatch, reply: str, unverified_subject: str | None
) -> None:
    out = await _finalize(
        monkeypatch, reply, prompt="what is the force", unverified_subject=unverified_subject
    )
    final = "$F = 7500\\ \\text{N}$" if unverified_subject else "$x = 6$"
    assert _cards(out) == [f"{UNCHECKED_ANSWER_MARKER}\n{final}"]
    assert VERIFIED_ANSWER_MARKER not in out
    assert out.count("**Answer**") == 1
    assert out.index("**Answer**\n\n```answer") > 0


@pytest.mark.parametrize(
    "reply",
    [
        "Question 1: What is the capital of France?\nAnswer: Paris",
        "Here's your quiz.\n\n**Answer:** Paris",
        "Here's your quiz.\n\n**Answer**\nParis",
    ],
)
async def test_an_answer_line_in_ordinary_chat_stays_prose(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    out = await _finalize(monkeypatch, reply, prompt="quiz me on capitals")
    assert out.strip() == reply


async def test_an_instant_reply_is_never_relanded(monkeypatch: pytest.MonkeyPatch) -> None:
    instant = "**Steps**  \n$2x = 12$  \n$x = 6$\n\nAnswer: see the card below.\n"
    out = await _finalize(monkeypatch, instant, instant=instant, unverified_subject="math")
    assert "```answer" not in out


def _scene() -> dict[str, Any]:
    return {
        "type": "scene",
        "version": 2,
        "title": "Car braking",
        "duration": 4,
        "bodies": [],
    }


async def test_a_model_simulation_is_dropped_on_an_unverified_physics_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = "The car stops in 40 m.\n\n```simulation\n" + json.dumps(_scene()) + "\n```"
    out = await _finalize(
        monkeypatch,
        reply,
        prompt="A 1500 kg car going 20 m/s brakes to a stop in 40 m. What is the braking force?",
    )
    assert PHYSICS_SHORT_HINT not in out
    assert "The car stops in 40 m." in out


async def test_a_model_simulation_alone_leaves_the_diagram_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = "~~~simulation\n" + json.dumps(_scene()) + "\n~~~"
    out = await _finalize(monkeypatch, reply, prompt="show the car braking")
    assert "simulation" not in out
    assert "Could not render that diagram" in out


async def test_a_server_scene_still_ships_on_a_verified_physics_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.physics.schemas.simulation import SIMULATION_SPEC_TYPES

    spec = {"type": next(iter(sorted(SIMULATION_SPEC_TYPES))), "title": "server"}
    verified = VerifiedPhysicsBlock(
        text="verified",
        canonical_answer="35.3 m",
        display_answer="35.3\\,\\mathrm{m}",
        canonical_fence=spec,
    )
    reply = "The range is $35.3\\ \\text{m}$.\n\n```simulation\n" + json.dumps(_scene()) + "\n```"
    out = await _finalize(monkeypatch, reply, verified=verified, prompt="find the range")
    assert out.count("```simulation") == 1
    assert '"title":"server"' in out
