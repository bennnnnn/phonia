"""The reply's own model call carries web_search; a call runs and a second call answers.

Production decided search with word rules alone, so "who won the champions league" and
"what's the population of Ethiopia" were answered from training data.
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.gateways.mcp import registry
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.stream_paths import run_llm_token_stream, run_tool_loop_path
from app.modules.chat.tool_loop import live_denial
from app.modules.chat.tool_loop.reply_calls import ReplyTurn, reply_tools
from app.modules.chat.turn_prep.context import StreamContext
from app.modules.web_search import WebSearchAdapter
from app.tests.fakes import isolated_settings, redis_mock
from app.tests.modules.chat.chat_test_support import turn_deps

_SETTINGS = isolated_settings(web_search_enabled=True, mcp_tool_loop_enabled=True)
_HIT = WebSearchHit(title="UCL final", url="https://uefa.example/final", snippet="PSG won.")
_SEARCH_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "web_search", "arguments": '{"query": "champions league winner"}'},
}


@pytest.fixture
def web_search_tool() -> dict[str, Any]:
    """The tool as production registers it at startup."""
    adapter = WebSearchAdapter(_SETTINGS)
    registry.register(adapter)
    return adapter.to_openai_tool()


def _turn(content: str, **fields: Any) -> ReplyTurn:
    values: dict[str, Any] = {
        "content": content,
        "lightweight": False,
        "has_instant_reply": False,
        "has_verified_math": False,
        "has_search_sources": False,
        "prior_user_messages": None,
        "prior_assistant": None,
        **fields,
    }
    return ReplyTurn(**values)


def _context(content: str) -> StreamContext:
    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": content}],
        run_title=False,
        user_message_content=content,
        reserved_tokens=100,
        max_output_tokens=100,
    )


def _model(*calls: tuple[list[str], list[dict[str, Any]]]) -> tuple[Any, list[dict[str, Any]]]:
    """A model whose nth call writes ``calls[n]``'s tokens, then makes its tool calls."""
    seen: list[dict[str, Any]] = []
    plays = iter(calls)

    async def stream_chat_completion(**kwargs: Any) -> AsyncIterator[str]:
        seen.append({**kwargs, "messages": list(kwargs["messages"])})
        tokens, tool_calls = next(plays)
        for token in tokens:
            yield token
        kwargs["tool_calls"].extend(tool_calls)
        kwargs["stream_meta"]["model_alias"] = kwargs["model_alias"]
        if tool_calls:
            kwargs["stream_meta"]["finish_reason"] = "tool_calls"

    return SimpleNamespace(stream_chat_completion=stream_chat_completion), seen


async def _reply(
    ctx: StreamContext, llm: Any, *, accum: StreamAccum | None = None, **kwargs: Any
) -> str:
    tokens = [
        token
        async for token in run_llm_token_stream(
            turn_deps(llm=llm),
            redis_mock(),
            _SETTINGS,
            ctx,
            usage={},
            outcome=None,
            on_reasoning=None,
            accum=accum or StreamAccum(),
            should_cancel=kwargs.pop("should_cancel", None),
            **kwargs,
        )
    ]
    return "".join(tokens)


@pytest.mark.parametrize(
    "content",
    [
        "who won the champions league",
        "what's the population of Ethiopia",
        "is the new iphone worth it",
    ],
)
def test_reply_tools_offer_web_search_on_a_question_about_the_world(
    web_search_tool: dict[str, Any], content: str
) -> None:
    assert reply_tools(_SETTINGS, _turn(content)) == [web_search_tool]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "thanks!",
        "hello there",
        "remind me to call mom at 5pm",
        "where do I work?",
        "what time is it in Tokyo",
        "why does this return undefined? function add(a, b) { a + b }",
    ],
)
def test_reply_tools_offer_nothing_when_nothing_is_to_look_up(
    web_search_tool: dict[str, Any], content: str
) -> None:
    assert reply_tools(_SETTINGS, _turn(content)) == []


@pytest.mark.parametrize(
    "answered",
    [
        {"lightweight": True},
        {"has_instant_reply": True},
        {"has_search_sources": True},
        {"has_verified_math": True},
    ],
)
def test_reply_tools_offer_nothing_on_a_turn_already_answered(
    web_search_tool: dict[str, Any], answered: dict[str, bool]
) -> None:
    assert reply_tools(_SETTINGS, _turn("who won the champions league", **answered)) == []


@pytest.mark.parametrize(
    "off",
    [
        {"reply_search_tool_enabled": False},
        {"web_search_enabled": False},
        {"mcp_tool_loop_enabled": False},
    ],
)
def test_reply_tools_follow_the_switches(
    web_search_tool: dict[str, Any], off: dict[str, bool]
) -> None:
    settings = isolated_settings(
        **{"web_search_enabled": True, "mcp_tool_loop_enabled": True, **off}
    )
    assert reply_tools(settings, _turn("who won the champions league")) == []


def test_reply_tools_need_the_registered_tool() -> None:
    registry.clear()
    assert reply_tools(_SETTINGS, _turn("who won the champions league")) == []


@pytest.mark.asyncio
async def test_tool_loop_path_leaves_the_search_to_the_reply(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    deps = turn_deps(quota={"global_spend_exceeded": AsyncMock(return_value=False)})
    await run_tool_loop_path(
        deps, redis_mock(), _SETTINGS, ctx, usage={}, on_status=None, should_cancel=None
    )
    assert ctx.reply_tools == [web_search_tool]


@pytest.mark.asyncio
async def test_tool_loop_path_offers_nothing_past_the_spend_cap(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    deps = turn_deps(quota={"global_spend_exceeded": AsyncMock(return_value=True)})
    await run_tool_loop_path(
        deps, redis_mock(), _SETTINGS, ctx, usage={}, on_status=None, should_cancel=None
    )
    assert ctx.reply_tools == []


@pytest.mark.asyncio
async def test_reply_searches_then_answers_from_the_results(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    ctx.reply_tools = [web_search_tool]
    llm, seen = _model(([], [_SEARCH_CALL]), (["PSG won it."], []))
    statuses: list[tuple[str, str | None]] = []

    async def on_status(phase: str, detail: str | None = None) -> None:
        statuses.append((phase, detail))

    with patch(
        "app.modules.web_search.tool.run_cached_search", AsyncMock(return_value=([_HIT], ["q"]))
    ):
        text = await _reply(ctx, llm, on_status=on_status)

    assert text == "PSG won it."
    assert seen[0]["tools"] == [web_search_tool]
    # One search a turn: the call that answers carries no tools.
    assert seen[1]["tools"] is None
    call_turn, result = seen[1]["messages"][-2:]
    assert call_turn == {"role": "assistant", "content": None, "tool_calls": [_SEARCH_CALL]}
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_1"
    assert _HIT.url in result["content"]
    # The pages the search found become the reply's source chips.
    assert [hit.url for hit in ctx.search_sources] == [_HIT.url]
    assert ("searching", "champions league winner") in statuses
    assert statuses[-1] == ("composing", None)


@pytest.mark.asyncio
async def test_reply_text_before_its_search_gets_a_paragraph_break(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    ctx.reply_tools = [web_search_tool]
    llm, seen = _model((["Let me check."], [_SEARCH_CALL]), (["PSG won it."], []))

    with patch(
        "app.modules.web_search.tool.run_cached_search", AsyncMock(return_value=([_HIT], ["q"]))
    ):
        text = await _reply(ctx, llm)

    assert text == "Let me check.\n\nPSG won it."
    assert seen[1]["messages"][-2]["content"] == "Let me check."


@pytest.mark.asyncio
async def test_reply_stopped_during_its_search_ends_there(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    ctx.reply_tools = [web_search_tool]
    llm, seen = _model(([], [_SEARCH_CALL]), (["never written"], []))
    stopped = {"now": False}

    async def search(*_args: Any, **_kwargs: Any) -> tuple[list[WebSearchHit], list[str]]:
        stopped["now"] = True
        return [_HIT], ["q"]

    accum = StreamAccum()
    with patch("app.modules.web_search.tool.run_cached_search", search):
        text = await _reply(ctx, llm, accum=accum, should_cancel=lambda: stopped["now"])

    assert text == ""
    assert len(seen) == 1
    assert accum.was_cancelled


@pytest.mark.asyncio
async def test_reply_call_to_a_tool_it_was_not_offered_is_refused(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    ctx.reply_tools = [web_search_tool]
    image_call = {
        "id": "call_2",
        "type": "function",
        "function": {"name": "generate_image", "arguments": '{"prompt": "a trophy"}'},
    }
    llm, seen = _model(([], [image_call]), (["Here is what I know."], []))

    text = await _reply(ctx, llm)

    assert text == "Here is what I know."
    refusal = seen[1]["messages"][-1]
    assert refusal["role"] == "tool"
    assert refusal["tool_call_id"] == "call_2"
    assert "not available" in refusal["content"]
    assert ctx.search_sources == []


@pytest.mark.asyncio
async def test_reply_without_tools_is_one_call() -> None:
    ctx = _context("explain Newton's third law")
    llm, seen = _model((["Equal and opposite."], []))

    assert await _reply(ctx, llm) == "Equal and opposite."
    assert len(seen) == 1
    assert seen[0]["tools"] is None


@pytest.mark.asyncio
async def test_reply_searches_once_whatever_the_second_call_returns(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    ctx.reply_tools = [web_search_tool]
    llm, seen = _model(
        ([], [_SEARCH_CALL]), (["PSG won it."], [_SEARCH_CALL]), (["never asked"], [])
    )

    with patch(
        "app.modules.web_search.tool.run_cached_search", AsyncMock(return_value=([_HIT], ["q"]))
    ):
        text = await _reply(ctx, llm)

    assert text == "PSG won it."
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_reply_answers_without_a_search_that_breaks(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _context("who won the champions league")
    ctx.reply_tools = [web_search_tool]
    prompt = list(ctx.prompt_messages)
    llm, seen = _model(([], [_SEARCH_CALL]), (["From what I know, PSG."], []))

    with patch(
        "app.modules.web_search.tool.run_cached_search",
        AsyncMock(side_effect=RuntimeError("search client bug")),
    ):
        text = await _reply(ctx, llm)

    assert text == "From what I know, PSG."
    # The unanswered call never reaches the provider, which would reject the list.
    assert seen[1]["messages"] == prompt
    assert ctx.search_sources == []


_BEARS = "Perfect. totally unrelated but did the bears win today"
_DENIAL = "I can't check live scores, so I don't know how the Bears did today."
_ANSWER = "The Bears beat the Falcons 27-20."


@pytest.mark.parametrize(
    "reply",
    [
        _DENIAL,
        "Sorry, I don't have real-time sports results, so I can't confirm it.",
        "Good question! I don't have access to live data. Check the NFL app.",
        "I'm unable to access real-time information right now.",
        "I can't browse the web, sorry.",
        # Review: the usual openings.
        "I'm sorry, but I can't access real-time data.",
        "Sorry \u2014 I can't check live scores.",
        "**I can't check live scores**, but ESPN has them.",
        "Hmm, I can't check live scores right now.",
        "As an AI, I don't have real-time data.",
        "I'm not able to check live scores.",
    ],
)
def test_a_live_data_denial_is_read(reply: str) -> None:
    assert live_denial.denies_live_data(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Sounds like a long day. Rest up tonight!",
        "I can't check your calendar, but you could add it to To-do.",
        "The Bears beat the Patriots 30-24 on Thursday.",
        # Talk about a denial, not one (review, 2026-10-25).
        'Some assistants say "I can\'t access real-time data", but Recall can search.',
        "A good line is: 'I don't have real-time information on that.'",
        "When I can't check live scores I say so.",
        # A long answer that mentions live data in passing is an answer.
        "Here is a long answer. " * 40 + "I can't check live scores.",
    ],
)
def test_other_replies_are_no_denial(reply: str) -> None:
    assert not live_denial.denies_live_data(reply)


def _retry_context(content: str = _BEARS, tool: dict[str, Any] | None = None) -> StreamContext:
    ctx = _context(content)
    ctx.denial_retry_tools = [tool] if tool else []
    return ctx


@pytest.mark.asyncio
async def test_a_denial_is_asked_again_with_search_offered(
    web_search_tool: dict[str, Any],
) -> None:
    """Live (2026-10-25): no tool was offered, and the reply said it couldn't check."""
    ctx = _retry_context(tool=web_search_tool)
    llm, seen = _model(([_DENIAL], []), ([], [_SEARCH_CALL]), ([_ANSWER], []))
    accum = StreamAccum()
    with patch(
        "app.modules.web_search.tool.run_cached_search", AsyncMock(return_value=([_HIT], ["q"]))
    ):
        await _reply(ctx, llm, accum=accum)

    assert accum.reply_text() == _ANSWER
    assert accum.retracted == _DENIAL
    assert [call["tools"] for call in seen] == [None, [web_search_tool], None]
    assert [hit.url for hit in ctx.search_sources] == [_HIT.url]


@pytest.mark.asyncio
async def test_the_model_may_answer_the_retry_without_searching(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _retry_context("what's my heart rate right now", web_search_tool)
    llm, seen = _model(
        (["I can't access real-time data from your watch."], []),
        (["Your watch's health app shows it."], []),
    )
    accum = StreamAccum()
    await _reply(ctx, llm, accum=accum)
    assert accum.reply_text() == "Your watch's health app shows it."
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_no_retry_without_the_offer_or_for_a_clock_denial(
    web_search_tool: dict[str, Any],
) -> None:
    llm, seen = _model(([_DENIAL], []), (["never asked"], []))
    assert await _reply(_retry_context(), llm) == _DENIAL
    assert len(seen) == 1
    clock = "I don't have access to real-time data, so I can't tell you the current time."
    llm, seen = _model(([clock], []), (["never asked"], []))
    assert await _reply(_retry_context("what time is it", web_search_tool), llm) == clock
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_a_stop_during_the_retry_keeps_the_denial_the_phone_drew(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _retry_context(tool=web_search_tool)
    llm, seen = _model(([_DENIAL], []), (["never drawn"], []))
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return len(seen) > 1

    accum = StreamAccum()
    await _reply(ctx, llm, accum=accum, should_cancel=should_cancel)
    assert accum.was_cancelled
    assert accum.reply_text() == _DENIAL


@pytest.mark.asyncio
async def test_a_failure_during_the_retry_keeps_the_denial(
    web_search_tool: dict[str, Any],
) -> None:
    from app.gateways.litellm_gateway import ModelUnavailableError

    ctx = _retry_context(tool=web_search_tool)
    first = {"done": False}

    async def stream_chat_completion(**kwargs: Any) -> AsyncIterator[str]:
        if first["done"]:
            raise ModelUnavailableError("down", failed_alias="free-chat")
        first["done"] = True
        yield _DENIAL

    accum = StreamAccum()
    with pytest.raises(ModelUnavailableError):
        await _reply(
            ctx, SimpleNamespace(stream_chat_completion=stream_chat_completion), accum=accum
        )
    # The pipeline finalizes a reply with parts: the denial the phone drew.
    assert accum.reply_text() == _DENIAL


def test_a_stop_after_a_retraction_cuts_the_answer_where_the_phone_did() -> None:
    accum = StreamAccum(parts=[_DENIAL], shown=[_DENIAL])
    accum.retract(0, 0)
    accum.parts.append("\n\nThe Bears beat")
    accum.shown.append("\n\nThe Bears beat")
    accum.mark_user_stop()
    drawn = len(_DENIAL) + len("\n\nThe Bears")
    assert accum.reply_text(drawn) == "The Bears"


@pytest.mark.asyncio
async def test_a_held_mark_of_the_denial_never_reaches_the_answer(
    web_search_tool: dict[str, Any],
) -> None:
    ctx = _retry_context(tool=web_search_tool)
    llm, _seen = _model((["Sorry, I can't check live scores!"], []), (["The Bears won."], []))
    accum = StreamAccum()
    await _reply(ctx, llm, accum=accum)
    assert accum.reply_text() == "The Bears won."
