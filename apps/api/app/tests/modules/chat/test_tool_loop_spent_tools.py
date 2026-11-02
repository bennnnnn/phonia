"""Work a turn already did without an answer is not repeated by its tool loop.

A SymPy pre-solve that ran out of time would run out again a round later, and a
photo lookup that found nothing would find nothing again: the tool loop neither
offers that tool nor runs a selection round for it.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.mcp import registry as mcp_registry
from app.modules.chat import tool_loop
from app.modules.chat.tool_loop import selection
from app.modules.math.schemas import MathIntent
from app.modules.math.tools import solve_timeouts
from app.services.model_health import Breakers

_SOLVE = "Solve 2x + 3 = 7"
_PHOTO = "show me a picture of a human ear"


def test_spent_tools_names_what_the_turn_used_up() -> None:
    assert tool_loop.spent_tools(solve_timed_out=False, photo_missed=False) == frozenset()
    assert tool_loop.spent_tools(solve_timed_out=True, photo_missed=False) == {"sympy"}
    assert tool_loop.spent_tools(solve_timed_out=True, photo_missed=True) == {
        "sympy",
        "search_image",
    }


@pytest.mark.parametrize(
    "content, spent",
    [(_SOLVE, frozenset({"sympy"})), (_PHOTO, frozenset({"search_image"}))],
    ids=["timed-out-solve", "photo-not-found"],
)
def test_a_spent_tool_is_no_reason_for_a_selection_round(content: str, spent: frozenset) -> None:
    settings = Settings(image_search_enabled=True, math_tools_enabled=True)
    assert tool_loop.turn_needs_tool_loop(content, settings=settings) is True
    assert tool_loop.turn_needs_tool_loop(content, settings=settings, skip_tools=spent) is False


def test_a_spent_tool_is_not_offered() -> None:
    from app.modules.images.search_tool import ImageSearchAdapter
    from app.modules.math.tool import SympyAdapter

    settings = Settings(image_search_enabled=True, math_tools_enabled=True)
    mcp_registry.clear()
    mcp_registry.register(SympyAdapter(settings))
    mcp_registry.register(ImageSearchAdapter(settings))
    try:

        def offered(spent: frozenset[str]) -> set[Any]:
            tools = selection._tools_for_user(settings, MagicMock(), skip_tools=spent)
            return {(tool.get("function") or {}).get("name") for tool in tools}

        assert offered(frozenset()) == {"sympy", "search_image"}
        assert offered(frozenset({"sympy"})) == {"search_image"}
        assert offered(frozenset({"search_image"})) == {"sympy"}
    finally:
        mcp_registry.clear()


def _ctx(**fields: Any) -> Any:
    from app.modules.chat.turn_prep import StreamContext

    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": _SOLVE}],
        run_title=False,
        user_message_content=_SOLVE,
        reserved_tokens=100,
        max_output_tokens=50,
        **fields,
    )


def test_the_loop_gate_reads_what_the_turn_spent() -> None:
    from app.modules.chat.stream_paths import _LoopGate

    assert _LoopGate.of(_ctx()).skip_tools == frozenset()
    gate = _LoopGate.of(_ctx(solve_timed_out=True, photo_missed=True))
    assert gate.skip_tools == {"sympy", "search_image"}


@pytest.mark.asyncio
async def test_a_timed_out_solve_runs_no_tool_round(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.chat.stream_paths import run_tool_loop_path

    deps = SimpleNamespace(
        quota=SimpleNamespace(global_spend_exceeded=AsyncMock(return_value=False))
    )
    rounds = AsyncMock()
    monkeypatch.setattr(tool_loop, "run_tool_rounds", rounds)
    settings = Settings(math_tools_enabled=True, mcp_tool_loop_enabled=True)
    for timed_out, runs in ((False, True), (True, False)):
        rounds.reset_mock()
        rounds.return_value = tool_loop.rounds.ToolRoundsOutcome([], None, None, [])
        ctx = _ctx(solve_timed_out=timed_out)
        await run_tool_loop_path(
            deps,  # type: ignore[arg-type]
            AsyncMock(),
            settings,
            ctx,
            usage={},
            on_status=None,
            should_cancel=None,
        )
        assert rounds.await_count == int(runs)


# ── what records a timed-out solve ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_solve_that_runs_out_of_time_is_recorded() -> None:
    from app.modules.math.tools.prompt import _build_verified_block_async

    intent = MathIntent(kind="equation", lhs="2*x+3", rhs="7", operation="solve", variable="x")
    with patch("app.core.sympy_executor.run_sympy", AsyncMock(side_effect=TimeoutError)):
        with solve_timeouts.recording() as timed_out:
            assert await _build_verified_block_async(intent, Settings()) is None
        # Outside a recording, a timeout is only logged.
        assert await _build_verified_block_async(intent, Settings()) is None
    assert timed_out == ["equation"]


@pytest.mark.asyncio
async def test_a_recording_spans_the_tasks_started_inside_it() -> None:
    async def times_out() -> None:
        solve_timeouts.note("integral")

    with solve_timeouts.recording() as timed_out:
        await asyncio.ensure_future(times_out())
    assert timed_out == ["integral"]


@pytest.mark.asyncio
@pytest.mark.parametrize("timed_out", [False, True])
async def test_the_turns_augmentation_says_whether_its_solve_timed_out(timed_out: bool) -> None:
    from app.modules.chat.prompt_builder import SubjectFetch
    from app.modules.chat.turn_prep import augment

    async def fetch(*_args: Any, **_kwargs: Any) -> SubjectFetch:
        if timed_out:
            solve_timeouts.note("equation")
        return SubjectFetch(
            subject_block="MATH NOTE",
            verified=None,
            solver_unverified=timed_out,
            unverified_subject="math" if timed_out else None,
            direct_text=None,
        )

    request = SimpleNamespace(
        content=_SOLVE, has_image_attachment=False, image_math_extract=None, on_status=None
    )
    identity = SimpleNamespace(
        mode=SimpleNamespace(
            lightweight=False, minimal_personal=False, day_planning=False, rich_context=True
        ),
        geo=SimpleNamespace(ambiguous_nearby=False),
        user=SimpleNamespace(locale="en"),
    )
    # A maths line: the gate lets it through to the solve, whose answer is stood in for.
    with patch.object(augment, "fetch_subject", fetch):
        got = await augment.gather_and_inject(
            request,  # type: ignore[arg-type]
            identity,  # type: ignore[arg-type]
            Settings(),
            AsyncMock(),
            [{"role": "user", "content": _SOLVE}],
            MagicMock(),
            instant_reply=None,
        )
    assert got.solve_timed_out is timed_out


# ── what records a photo lookup that found nothing ─────────────────────────────


def _photo_deps(search: AsyncMock) -> Any:
    from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps

    return turn_deps(
        session_factory=FakeSessionCM,
        locks={
            "acquire_lock": AsyncMock(return_value="lock"),
            "refresh_lock": AsyncMock(return_value=True),
            "release_lock": AsyncMock(),
        },
        chats={"get_by_id": AsyncMock(return_value=MagicMock(project_id=None))},
        messages={"list_recent": AsyncMock(return_value=[])},
        quota={"daily_limit_for_user": MagicMock(return_value=100_000)},
        plan={
            "resolve_user_model_override": MagicMock(return_value="free-chat"),
            "can_use": MagicMock(return_value=False),
        },
        image_search={"search_and_attach_for_chat": search},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 502, 503])
async def test_a_photo_lookup_that_found_nothing_is_a_miss(status: int) -> None:
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn
    from app.modules.images.search import ImageSearchError

    search = AsyncMock(side_effect=ImageSearchError("no usable photo", status_code=status))
    misses: set[str] = set()
    handled = await try_image_lookup_for_turn(
        _photo_deps(search),
        Settings(image_search_enabled=True),
        user=MagicMock(),
        chat_id=uuid4(),
        content=_PHOTO,
        outcome=None,
        create_user_message=True,
        misses=misses,
    )
    assert handled is False
    assert misses == {"photo"}


@pytest.mark.asyncio
async def test_a_lookup_that_never_searched_is_no_miss() -> None:
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    search = AsyncMock()
    misses: set[str] = set()
    # Not a photo request at all: nothing was looked up.
    handled = await try_image_lookup_for_turn(
        _photo_deps(search),
        Settings(image_search_enabled=True),
        user=MagicMock(),
        chat_id=uuid4(),
        content="what is an ear made of?",
        outcome=None,
        create_user_message=True,
        misses=misses,
    )
    assert handled is False
    search.assert_not_awaited()
    assert misses == set()


@pytest.mark.asyncio
async def test_the_turn_tells_its_tool_loop_the_photo_was_not_found() -> None:
    from app.modules.chat import stream_entry
    from app.modules.images.search import ImageSearchError

    search = AsyncMock(side_effect=ImageSearchError("no usable photo", status_code=502))
    prepared = SimpleNamespace(reply_picture=None)
    streamed: list[Any] = []

    async def fake_stream(_deps: Any, _redis: Any, _settings: Any, ctx: Any, **_kwargs: Any):
        streamed.append(ctx)
        yield "An ear has three parts."

    user = MagicMock(id=uuid4(), plan="free")
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
        patch("app.services.model_health.read_breakers", AsyncMock(return_value=Breakers())),
        patch("app.modules.chat.turn_resources.reserve_turn_quota", AsyncMock(return_value=100)),
        patch("app.modules.chat.stream_entry.top_up_reserve_for_prompt", AsyncMock()),
        patch("app.modules.chat.stream_entry.prepare_chat_turn", AsyncMock(return_value=prepared)),
        patch("app.modules.chat.stream_entry.start_reply_picture", return_value=None),
        patch("app.modules.chat.stream_entry.await_user_message_persist", AsyncMock()),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
    ):
        tokens = [
            token
            async for token in stream_entry.stream_chat_response(
                _photo_deps(search),
                AsyncMock(),
                Settings(image_search_enabled=True),
                user_id=user.id,
                chat_id=uuid4(),
                content=_PHOTO,
                user=user,
                skip_usage_seed=True,
            )
        ]
    assert tokens == ["An ear has three parts."]
    search.assert_awaited_once()
    assert streamed[0].photo_missed is True
