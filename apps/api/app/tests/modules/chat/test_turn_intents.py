"""A turn's plan: the separate requests one message holds, and how each gate reads them.

``turn_prep.intents.plan_turn`` cuts a message into requests; the tool loop searches
each live part for itself, a verified solve closes only its own part, and the prompt
gets a multi-part contract only when there are two or more parts.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.mcp import registry as mcp_registry
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.chat import tool_loop
from app.modules.chat.prompt_constants import (
    BREVITY_REQUEST_HINT,
    COMPARISON_FORMAT_HINT,
    HOWTO_FORMAT_HINT,
    STEPS_FORMAT_HINT,
    TEACHING_HINT,
)
from app.modules.chat.prompt_constants.multi_part import MULTI_PART_MARKER, multi_part_contract
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.chat.prompt_sections import part_shape_hints
from app.modules.chat.tool_loop.parts import live_parts, open_parts, searchable_parts
from app.modules.chat.turn_prep.clauses import points_back, request_clauses
from app.modules.chat.turn_prep.intents import plan_turn
from app.modules.turn_reading.plan import TurnPart, TurnPlan
from app.modules.web_search import WebSearchAdapter


def _settings(**overrides: object) -> Settings:
    configured = Settings()
    for key, value in overrides.items():
        setattr(configured, key, value)
    return configured


@pytest.fixture
def web_search_tool() -> Iterator[None]:
    mcp_registry.clear()
    mcp_registry.register(WebSearchAdapter(_settings()))
    yield
    mcp_registry.clear()


# ── The plan ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        (
            "I need a new laptop, and I also want to find remote backend engineering jobs",
            [
                ("I need a new laptop", "ask"),
                ("I want to find remote backend engineering jobs", "live"),
            ],
        ),
        (
            "what's the weather in Paris tomorrow and also solve 2x + 5 = 17",
            [("what's the weather in Paris tomorrow", "live"), ("solve 2x + 5 = 17", "solve")],
        ),
        (
            "solve 2x + 5 = 17 and also what's the weather in Paris tomorrow",
            [("solve 2x + 5 = 17", "solve"), ("what's the weather in Paris tomorrow", "live")],
        ),
        (
            "what's the capital of Australia? and how do I boil an egg?",
            [("what's the capital of Australia?", "ask"), ("how do I boil an egg?", "ask")],
        ),
        (
            "switch to dark mode and tell me a joke",
            [("switch to dark mode", "settings"), ("tell me a joke", "ask")],
        ),
        (
            "draw a cat wearing a hat and also explain what a black hole is",
            [("draw a cat wearing a hat", "image"), ("explain what a black hole is", "ask")],
        ),
        (
            "remind me to buy milk at 5pm and what's the weather in Nairobi today?",
            [
                ("remind me to buy milk at 5pm", "reminder"),
                ("what's the weather in Nairobi today?", "live"),
            ],
        ),
        (
            "teach me python dictionaries, and what is the current price of bitcoin?",
            [
                ("teach me python dictionaries", "ask"),
                ("what is the current price of bitcoin?", "live"),
            ],
        ),
        (
            "write a function to reverse a list, and who won the champions league final last night",
            [
                ("write a function to reverse a list", "ask"),
                ("who won the champions league final last night", "live"),
            ],
        ),
        (
            "compare python and javascript, and how do I install node on mac?",
            [("compare python and javascript", "ask"), ("how do I install node on mac?", "ask")],
        ),
        (
            "in one sentence what is DNS? Also explain in detail how TLS handshakes work",
            [
                ("in one sentence what is DNS?", "ask"),
                ("explain in detail how TLS handshakes work", "ask"),
            ],
        ),
        (
            "switch to dark mode, and also what is the capital of France?",
            [("switch to dark mode", "settings"), ("what is the capital of France?", "ask")],
        ),
        (
            "how do I make cold brew? btw what's the weather in Addis today",
            [("how do I make cold brew?", "ask"), ("what's the weather in Addis today", "live")],
        ),
        # Beside a solve, a search for something else and a maths command keep their parts.
        (
            "solve 2x + 5 = 17 and find me a good book to read",
            [("solve 2x + 5 = 17", "solve"), ("find me a good book to read", "ask")],
        ),
        (
            "Graph y = x^2 + 4x + 1 and find the vertex",
            [("Graph y = x^2 + 4x + 1", "solve"), ("find the vertex", "ask")],
        ),
    ],
)
def test_plan_turn_splits_independent_requests(text: str, parts: list[tuple[str, str]]) -> None:
    plan = plan_turn(text)
    assert [(part.text, part.kind) for part in plan.parts] == parts


@pytest.mark.parametrize(
    "text",
    [
        # Related questions stay one request: they point back or share their subject.
        "difference between TCP and UDP and when to use each",
        "solve 2x+5=17 and graph it",
        "compare python and javascript and tell me which is faster",
        "what is DNS and how does it work",
        "who is the CEO of Tesla and how old is he",
        "how do I make pasta and what sauce goes well with it",
        "what's the weather in Paris and what can I do there",
        "What's the weather in Paris? What about London?",
        "what is bitcoin and what's the price of bitcoin today",
        "How tall is the Eiffel Tower? When was it built?",
        "who won the world cup in 2022 and who scored the goals",
        "I'm going to Paris tomorrow. What's the weather going to be like and what should I pack?",
        "How long does a ball take to fall 20 m on Earth? Compare with Jupiter.",
        # A physics calculation asked after its givens: solved apart, the first half's
        # parallel resistance was the answer card for a question about the current.
        "Draw a circuit with a 9V battery and two 3 ohm resistors in parallel and find the total current",
        "A ball is dropped from 20 m and work out how fast it hits the ground",
        "why does it look like that? what are the scales made of",
        # A request that names nothing of its own, or only shapes the one before.
        "explain recursion and give me an example",
        "explain recursion and give me an example in python",
        "Explain quantum computing. Use simple words.",
        "plan a 3 day trip to Rome and include a budget",
        "What's a good laptop for coding? My budget is $1000.",
        "Can you help me plan a trip to Japan? I want to see Tokyo and Kyoto.",
        "how do I learn python? Where do I start?",
        "what's 2+2 and why",
        "thanks! and what about tomorrow?",
        # Text to work on is never cut.
        "translate to French: where is the station and how much is a ticket?",
        "translate 'where is the station and how much is a ticket' to French",
        "write an email to my boss: I'm sick and also need Friday off",
        "write an email to my landlord and tell him the rent will be late",
        "fix this: for i in range(10): print(i) and also explain it",
        # One reminder line; two reminders are the reminder parser's.
        "remind me to call mom at 5pm and to pay rent on friday at 9am",
        "hi! what's the weather in Nairobi?",
    ],
)
def test_plan_turn_keeps_one_request_whole(text: str) -> None:
    plan = plan_turn(text)
    assert not plan.multi, [part.text for part in plan.parts]
    assert plan.texts() == (text,)


def test_plan_turn_keeps_what_the_user_said_first_as_context() -> None:
    plan = plan_turn("I'm a backend dev. I need a new laptop, and I also want to find remote jobs")
    assert plan.context == "I'm a backend dev"
    assert plan.texts() == ("I need a new laptop", "I want to find remote jobs")


def test_long_pasted_text_is_never_cut() -> None:
    pasted = "What is this? " + "The quarterly report shows growth and also losses. " * 15
    assert not plan_turn(pasted).multi


@pytest.mark.parametrize(
    ("text", "leans"),
    [
        ("and graph it", True),
        ("which is faster", True),
        ("when to use each", True),
        ("and what can I do there", True),
        ("what time is it in Tokyo", False),
        ("is there a good museum in Berlin", False),
        ("how do I boil an egg", False),
        ("what should I do this weekend", False),
    ],
)
def test_points_back(text: str, leans: bool) -> None:
    assert points_back(text) is leans


def test_request_clauses_masks_quotes() -> None:
    split = request_clauses('how do you say "where is it and how much" in French?')
    assert len(split.clauses) == 1


# ── The prompt ──────────────────────────────────────────────────────────────


def test_contract_names_every_part_and_asks_for_sections() -> None:
    plan = plan_turn("I need a new laptop, and I also want to find remote backend engineering jobs")
    contract = multi_part_contract(plan, [part_shape_hints(text) for text in plan.texts()])
    assert contract.startswith(MULTI_PART_MARKER)
    assert '1. "I need a new laptop"' in contract
    assert '2. "I want to find remote backend engineering jobs": a live question' in contract
    assert "under its own `###` heading" in contract
    # Clarify within the part that needs it, and still answer the rest (I5).
    assert "ask about it inside that request's section and still answer the others" in contract


def test_contract_for_one_answer_and_a_settings_card_has_no_headings() -> None:
    plan = plan_turn("switch to dark mode and tell me a joke")
    contract = multi_part_contract(plan, [[], []])
    assert "a settings change" in contract
    assert "do not say it is done" in contract
    assert "answer it directly, with no heading" in contract


def test_each_part_gets_its_own_layout() -> None:
    """The whole message no longer picks one layout (I7)."""
    plan = plan_turn("compare python and javascript, and how do I install node on mac?")
    shapes = [part_shape_hints(text) for text in plan.texts()]
    assert COMPARISON_FORMAT_HINT in shapes[0]
    assert shapes[1] and (HOWTO_FORMAT_HINT in shapes[1] or STEPS_FORMAT_HINT in shapes[1])
    contract = multi_part_contract(plan, shapes)
    assert f"For request 1 only: {COMPARISON_FORMAT_HINT}" in contract


def test_a_length_limit_binds_only_its_part() -> None:
    """ "In one sentence" on part 1 is not a cap on part 2 (Q3)."""
    plan = plan_turn("in one sentence what is DNS? Also explain in detail how TLS handshakes work")
    shapes = [part_shape_hints(text) for text in plan.texts()]
    assert shapes[0] == [BREVITY_REQUEST_HINT]
    assert BREVITY_REQUEST_HINT not in shapes[1]
    whole = _style_format_hints(
        query_text=" ".join(plan.texts()),
        is_day_plan=False,
        minimal_personal_context=False,
        multi=True,
    )
    assert BREVITY_REQUEST_HINT not in whole


def test_a_lesson_shapes_only_its_part() -> None:
    """ "Teach me Python and also give me a workout plan" is not one lesson outline."""
    plan = plan_turn("teach me Python and also give me a workout plan")
    shapes = [part_shape_hints(text) for text in plan.texts()]
    assert TEACHING_HINT in shapes[0]
    assert TEACHING_HINT not in shapes[1]
    whole = _style_format_hints(
        query_text="teach me Python and also give me a workout plan",
        is_day_plan=False,
        minimal_personal_context=False,
        multi=True,
    )
    assert TEACHING_HINT not in whole


@pytest.mark.parametrize(
    "text",
    [
        "What is a Python list?",
        "difference between TCP and UDP and when to use each",
        "solve 2x+5=17 and graph it",
    ],
)
def test_one_part_turns_get_no_contract(text: str) -> None:
    from app.modules.chat.prompt_format import render_rules
    from app.modules.chat.prompt_sections import NEARBY_CONTRACTS, PromptTurn

    plan = plan_turn(text)
    turn = PromptTurn(
        user=None,  # type: ignore[arg-type]
        settings=_settings(),
        query_text=text,
        local_tz="UTC",
        lightweight=False,
        slim=True,
        recall_memory=False,
        advice_memory=False,
        minimal_personal_context=False,
        prompt_location=None,
        summary=None,
        memory_block="",
        attachment_rag_block="",
        todos_section=None,
        chat_history_rag_block="",
        exchange=[],
        followup=None,
        plan=plan if plan.multi else None,
    )
    assert not any(MULTI_PART_MARKER in text for text in render_rules(NEARBY_CONTRACTS, turn))


# ── Search and tools, per part ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "verified"),
    [
        # A reminder half no longer cancels the live half (I4).
        ("remind me to buy milk at 5pm and what's the weather in Nairobi today?", False),
        # Nor does a request to make something.
        ("teach me python dictionaries, and what is the current price of bitcoin?", False),
        (
            "write a function to reverse a list, and who won the champions league final last night",
            False,
        ),
        # A verified solve closes its own part only.
        ("what's the weather in Paris tomorrow and also solve 2x + 5 = 17", True),
        ("I need a new laptop, and I also want to find remote backend engineering jobs", False),
    ],
)
def test_turn_needs_tool_loop_reads_each_part(text: str, verified: bool) -> None:
    configured = _settings(mcp_tool_loop_enabled=True, web_search_enabled=True)
    assert (
        tool_loop.turn_needs_tool_loop(text, settings=configured, has_verified_math=verified)
        is True
    )


def test_a_verified_single_solve_still_skips_the_loop() -> None:
    configured = _settings(mcp_tool_loop_enabled=True, math_tools_enabled=True)
    assert (
        tool_loop.turn_needs_tool_loop(
            "solve 2x + 5 = 17", settings=configured, has_verified_math=True
        )
        is False
    )


def test_open_parts_leave_out_handled_and_verified_parts() -> None:
    text = "what's the weather in Paris tomorrow and also solve 2x + 5 = 17"
    assert open_parts(text, has_verified_math=True) == ["what's the weather in Paris tomorrow"]
    assert open_parts("switch to dark mode and tell me a joke") == ["tell me a joke"]
    assert open_parts("What is a Python list?") == ["What is a Python list?"]
    assert open_parts("solve 2x + 5 = 17", has_verified_math=True) == []
    assert live_parts(open_parts(text, has_verified_math=True)) == [
        "what's the weather in Paris tomorrow"
    ]


def test_parts_are_read_without_the_chat() -> None:
    verdicts = {"what's a good laptop for coding": False, "who is the mayor of Addis": True}

    def gate(text: str, _settings: Settings, **kwargs: object) -> bool:
        assert kwargs == {}
        return verdicts[text]

    with patch("app.modules.web_search.detection.should_web_search", side_effect=gate):
        found = searchable_parts(
            list(verdicts), _settings(), prior_user_messages=["earlier"], prior_assistant="x"
        )
    assert found == ["who is the mayor of Addis"]


@pytest.mark.asyncio
async def test_forced_search_queries_the_live_part_not_the_whole_line(web_search_tool) -> None:
    """ "a laptop, and remote backend jobs" searches the jobs, in the user's words (I6)."""
    text = "I need a new laptop, and I also want to find remote backend engineering jobs"
    hit = WebSearchHit(title="Jobs", url="https://example.com/jobs", snippet="Remote backend")
    forced = AsyncMock(return_value=([hit], ["q"]))
    complete = AsyncMock(return_value={"content": "", "tool_calls": []})
    with (
        patch("app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools", complete),
        patch("app.modules.chat.tool_loop.forced_search.run_cached_search", forced),
    ):
        _out, _verified, _terminal, hits = await tool_loop.run_tool_rounds(
            settings=_settings(mcp_tool_loop_enabled=True, web_search_enabled=True),
            messages=[{"role": "user", "content": text}],
            usage={},
        )
    complete.assert_not_awaited()
    assert hits == [hit]
    call = forced.await_args
    assert call is not None
    queries = call.args[1]
    assert len(queries) == 1
    assert "remote backend engineering jobs" in queries[0]
    assert "laptop" not in queries[0]


@pytest.mark.asyncio
async def test_two_live_parts_search_each_and_share_the_results(web_search_tool) -> None:
    text = "what's the weather in Paris tomorrow? Also, what is the current price of bitcoin?"
    weather = WebSearchHit(title="Weather", url="https://example.com/w", snippet="Rain")
    coin = WebSearchHit(title="BTC", url="https://example.com/b", snippet="$70k")

    async def search(_settings: Settings, queries: list[str], **_kwargs: object):
        return ([weather] if "weather" in queries[0] else [coin]), queries

    with patch("app.modules.chat.tool_loop.forced_search.run_cached_search", side_effect=search):
        _out, _verified, _terminal, hits = await tool_loop.run_tool_rounds(
            settings=_settings(mcp_tool_loop_enabled=True, web_search_enabled=True),
            messages=[{"role": "user", "content": text}],
            usage={},
        )
    assert hits == [weather, coin]


@pytest.mark.asyncio
async def test_verified_maths_does_not_cancel_the_live_part(web_search_tool) -> None:
    text = "what's the weather in Paris tomorrow and also solve 2x + 5 = 17"
    hit = WebSearchHit(title="Paris", url="https://example.com/p", snippet="Sunny")
    forced = AsyncMock(return_value=([hit], ["q"]))
    complete = AsyncMock(return_value={"content": "", "tool_calls": []})
    with (
        patch("app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools", complete),
        patch("app.modules.chat.tool_loop.forced_search.run_cached_search", forced),
    ):
        _out, _verified, _terminal, hits = await tool_loop.run_tool_rounds(
            settings=_settings(mcp_tool_loop_enabled=True, web_search_enabled=True),
            messages=[{"role": "user", "content": text}],
            usage={},
            has_verified_math=True,
        )
    # The server solved the maths: no selection round, one search for the weather.
    complete.assert_not_awaited()
    assert hits == [hit]
    call = forced.await_args
    assert call is not None and "2x" not in call.args[1][0]


def test_a_multi_part_turn_is_never_offered_a_turn_ending_photo_tool() -> None:
    from app.modules.chat.tool_loop.selection import _tools_for_user
    from app.modules.images.search_tool import ImageSearchAdapter

    configured = _settings(image_search_enabled=True)
    mcp_registry.clear()
    mcp_registry.register(ImageSearchAdapter(configured))
    try:
        single = _tools_for_user(configured, None, user_text="show me an ear")
        multi = _tools_for_user(
            configured, None, user_text="what's the capital of Australia? and how do I boil an egg?"
        )
    finally:
        mcp_registry.clear()
    assert [tool["function"]["name"] for tool in single] == ["search_image"]
    assert multi == []


def test_plan_type_is_plain_data() -> None:
    plan = TurnPlan((TurnPart("a"), TurnPart("b", "live")), context="c")
    assert plan.multi and plan.of_kind("live") == (TurnPart("b", "live"),)
