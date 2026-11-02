"""Tests for chat model routing (``modules/chat/model_routing``): pure functions, no I/O."""

import time

import pytest

from app.core.config import Settings
from app.models import model_catalog
from app.modules.billing import plan
from app.modules.billing import plan as plan_service
from app.modules.chat.model_routing.route import (
    message_needs_thinking,
    resolve_alias_in_pool,
    route_chat_model,
)
from app.modules.physics import lane as routing_physics
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solver import PhysicsResult


@pytest.mark.parametrize(
    "content,expected",
    [
        # Simple messages → the fast auto alias (Gemini Flash).
        ("hi", "qwen-3.7-flash"),
        ("hello world", "qwen-3.7-flash"),
        ("what's for lunch", "qwen-3.7-flash"),
        ("explain quantum computing", "qwen-3.7-flash"),
        ("why is the sky blue", "qwen-3.7-flash"),
        ("compare two options", "qwen-3.7-flash"),
        # Smart triggers → smart-chat
        ("prove p = np", "smart-chat"),
        ("debug the memory leak", "smart-chat"),
        ("analyze this algorithm", "smart-chat"),
        ("design a distributed queue", "smart-chat"),
        ("derive the formula", "smart-chat"),
        ("refactor this module", "smart-chat"),
        ("step by step how to deploy", "smart-chat"),
        ("optimize this query", "smart-chat"),
        ("trade-off between latency and throughput", "smart-chat"),
        ("what is the complexity of this", "smart-chat"),
        # Tutoring has a strict format/state contract and uses the low-latency
        # teaching lane; live QA showed the reasoning tier added 10-20s TTFT.
        ("Teach me python dictionaries", "qwen-3.7-flash"),
        ("Teach me python dictionaries step by step", "qwen-3.7-flash"),
        ("Help me learn SQL joins", "qwen-3.7-flash"),
        ("Give me a 70-day Python mastery plan", "qwen-3.7-flash"),
        ("70 days mastering python from beginner to senior level plan", "qwen-3.7-flash"),
        ("Create a 70-day Python plan", "qwen-3.7-flash"),
        ("70-day roadmap for Python", "qwen-3.7-flash"),
        ("Give me a daily Python curriculum for 70 days", "qwen-3.7-flash"),
        ("Teach me Python over the next 70 days", "qwen-3.7-flash"),
        # Ordinary non-learning plans stay fast.
        ("Give me a 30-day workout plan", "qwen-3.7-flash"),
        ("Create a 12-week business plan", "qwen-3.7-flash"),
        (
            "Create a 4-column markdown table with a Main tradeoff column, then show a code block",
            "qwen-3.7-flash",
        ),
        ("I studied Python for 70 days and now plan to apply for jobs", "qwen-3.7-flash"),
        # Comparison cues → smart-chat (previously classifier-only web search
        # with no model upgrade; a weak model answered "X vs Y" questions).
        ("kenya vs ethiopia", "smart-chat"),
        ("react versus vue for a production app", "smart-chat"),
        # Bare coding asks without a fence → smart-chat (previously stayed
        # free-chat because there was no ``` fence and no smart keyword).
        ("write a function to merge two sorted lists", "smart-chat"),
        ("write a script that backs up my db", "smart-chat"),
        ("implement a rate limiter in python", "smart-chat"),
        ("code a rest api for todos", "smart-chat"),
        ("solve this leetcode problem", "smart-chat"),
        # Long message (>=800 chars → smart-chat)
        ("a" * 801, "smart-chat"),
        ("a" * 799, "qwen-3.7-flash"),
        # Any code fence → smart-chat, regardless of language tag (or lack of
        # one). BUG FIX: this used to only match a fixed language allowlist,
        # so a bare fence or an unlisted language (bash, shell, C, HTML, ...)
        # silently stayed on free-chat even with real pasted code.
        ("check this:\n```python\nprint(1)\n```", "smart-chat"),
        ("check this out:\n```\nprint(1)\n```", "smart-chat"),
        ("run this:\n```bash\necho hi\n```", "smart-chat"),
        ("what's wrong here:\n```html\n<div></div>\n```", "smart-chat"),
        # Math / structured turns → the low-latency strong math model (a weak
        # fast model disagreed with verified results, while R1 repeatedly
        # returned empty visible streams in live QA).
        ("solve 2x + 3 = 7", "glm-5.2"),
        ("graph y = x^2", "glm-5.2"),
        ("2x+3=7", "glm-5.2"),
        ("find the area of a circle radius 4", "glm-5.2"),
        ("integrate x^2 from 0 to 1", "glm-5.2"),
        ("standard deviation of 1, 2, 3, 4, 5", "glm-5.2"),
        # Verified closed-form arithmetic stays free-chat — R1 used to dump a
        # live Reasoning essay ("the user just wrote 4!") on these.
        ("4!", "qwen-3.7-flash"),
        ("what is 1+1", "qwen-3.7-flash"),
        ("3+0", "qwen-3.7-flash"),
        ("3 + 0", "qwen-3.7-flash"),
        ("7*8", "qwen-3.7-flash"),
        ("8-8*2", "qwen-3.7-flash"),
        # Arithmetic next to a hard question is not a fast-path whole message.
        ("what is 1+1 and also graph y = x^2", "glm-5.2"),
        # A recognized physics template stays on the fast model; the verifier
        # owns the number. Homework the templates miss still goes to smart-chat.
        (
            "a 2kg block slides down a 30° frictionless incline, find its acceleration",
            "qwen-3.7-flash",
        ),
        ("calculate the momentum of a 5kg object moving at 12 m/s", "qwen-3.7-flash"),
        ("what is the escape velocity of earth", "qwen-3.7-flash"),
        ("a ball is dropped from 20 m, how long to hit the ground", "qwen-3.7-flash"),
        ("equations of motion for a pendulum", "smart-chat"),
        (
            "a block slides down a 90° frictionless incline, find its acceleration",
            "smart-chat",
        ),
        ("physics", "qwen-3.7-flash"),
        ("the project has momentum now", "qwen-3.7-flash"),
        # Plain prose with no math cue stays on the fast alias.
        ("what's for dinner tonight", "qwen-3.7-flash"),
        ("What is a Python list?", "qwen-3.7-flash"),
        ("thanks, that helped", "qwen-3.7-flash"),
        # Hard reasoning with no trigger word (R4.3).
        (
            "plan a zero-downtime migration of a monolith Postgres schema to sharded tables",
            "smart-chat",
        ),
        (
            "All cats are mammals. Some mammals are black. Does it follow that some cats "
            "are black? Explain carefully.",
            "smart-chat",
        ),
        ("plan my week", "qwen-3.7-flash"),
        ("drive carefully, it's icy", "qwen-3.7-flash"),
        # Code review and code writing with no fence (R4.6).
        (
            "can you review my function that reverses a linked list, it keeps looping forever",
            "smart-chat",
        ),
        ("write a python function to reverse a string", "smart-chat"),
        ("can you review my cover letter", "qwen-3.7-flash"),
        ("my promo code doesn't work", "qwen-3.7-flash"),
        # Pasted data under 800 characters (R4.8).
        (
            'find the duplicate ids: [{"id": 4, "name": "Ana"}, {"id": 9, "name": "Ben"}, '
            '{"id": 4, "name": "Cy"}, {"id": 12, "name": "Di"}, {"id": 9, "name": "Ed"}, '
            '{"id": 15, "name": "Flo"}, {"id": 21, "name": "Gus"}, {"id": 15, "name": "Hal"}]',
            "smart-chat",
        ),
        ("my scores were [90, 85, 77], is that good?", "qwen-3.7-flash"),
        # A matrix stays on the maths lane; writing about a migration stays everyday.
        ("determinant of [[1,2,3],[0,1,4],[5,6,0]]", "glm-5.2"),
        (
            "write a tweet announcing that we finished migrating our whole backend to "
            "postgres, zero downtime",
            "qwen-3.7-flash",
        ),
    ],
)
def test_route_chat_model(content: str, expected: str) -> None:
    assert route_chat_model(content) == expected


@pytest.mark.parametrize(
    "content,prior_user,expected",
    [
        ("What would be the solution if the equation were 3x^2 + 5 = 8?", None, False),
        ("what's for dinner tonight", None, False),
        ("prove the quadratic formula", None, True),
        ("debug this algorithm", None, True),
        ("why", "prove the quadratic formula", True),
        ("why", "What would be the solution if the equation were 3x^2 + 5 = 8?", False),
    ],
)
def test_message_needs_thinking(content: str, prior_user: str | None, expected: bool) -> None:
    assert message_needs_thinking(content, prior_user=prior_user) is expected


def test_verified_physics_stays_smart_when_math_tools_are_off() -> None:
    content = "calculate the momentum of a 5kg object moving at 12 m/s"
    pool = [model.id for model in model_catalog.selectable_models()]
    assert (
        resolve_alias_in_pool(
            "auto",
            content,
            pool,
            Settings(math_tools_enabled=False),
        )
        == "smart-chat"
    )


@pytest.mark.parametrize(
    "content,prior_user,expected",
    [
        ("Now fix it", None, "qwen-3.7-flash"),
        ("Now fix it", "debug this algorithm", "smart-chat"),
        ("add tests", "debug this algorithm", "smart-chat"),
        ("check if it is fixed", "debug this algorithm", "smart-chat"),
        ("Handle the edge cases", "debug this algorithm", "smart-chat"),
        ("Can you verify the patch?", "debug this algorithm", "smart-chat"),
        ("please review this", "debug this algorithm", "smart-chat"),
        ("check the weather", "debug this algorithm", "qwen-3.7-flash"),
        ("handle dinner tonight", "debug this algorithm", "qwen-3.7-flash"),
        ("thanks", "debug this algorithm", "qwen-3.7-flash"),
        ("what's for dinner tonight", "debug this algorithm", "qwen-3.7-flash"),
        ("explain photosynthesis", "debug this algorithm", "qwen-3.7-flash"),
        ("fix dinner", "debug this algorithm", "qwen-3.7-flash"),
        ("add milk to my grocery list", "debug this algorithm", "qwen-3.7-flash"),
    ],
)
def test_route_chat_model_inherits_smart_on_short_followup(
    content: str, prior_user: str | None, expected: str
) -> None:
    assert route_chat_model(content, prior_user=prior_user) == expected


def test_route_chat_model_inherits_smart_from_prior_turn_model() -> None:
    """A follow-up of a follow-up must keep Pro when the last user row stored it.

    Re-scoring ``add tests`` in isolation is Flash, so the next ``fix it``
    would drop off the strong tier without the persisted model.
    """
    assert (
        route_chat_model("fix it", prior_user="add tests", prior_model="smart-chat") == "smart-chat"
    )
    assert route_chat_model("fix it", prior_user="add tests") == "qwen-3.7-flash"


def test_route_chat_model_keeps_math_followup_on_low_latency_strong_model() -> None:
    prior = "solve 3x^2 + x^0 = 3"
    assert route_chat_model("how?", prior_user=prior) == "glm-5.2"
    assert route_chat_model("Why is x = -1 rejected?", prior_user=prior) == "glm-5.2"
    assert route_chat_model("How did you factor that?", prior_user=prior) == "glm-5.2"
    assert (
        route_chat_model("show the next step", prior_user="try again", prior_model="glm-5.2")
        == "glm-5.2"
    )


@pytest.mark.parametrize(
    "reaction",
    ["A", "red", "I'm confused", "why?", "next", "Bad bdbd head hdjjd jdjdd"],
)
def test_route_chat_model_keeps_active_tutor_turns_on_low_latency_lane(reaction: str) -> None:
    assert route_chat_model(reaction, lesson_active=True) == "qwen-3.7-flash"


def test_route_chat_model_does_not_treat_short_text_as_a_lesson_without_state() -> None:
    assert route_chat_model("red") == "qwen-3.7-flash"


def test_last_user_turn_returns_newest_user_line() -> None:
    from types import SimpleNamespace

    from app.modules.chat.model_routing.route import last_user_turn

    recent = [
        SimpleNamespace(role="user", content="debug this algorithm", model="smart-chat"),
        SimpleNamespace(role="assistant", content="here's a patch"),
        SimpleNamespace(role="user", content=""),
        SimpleNamespace(role="assistant", content="ok"),
    ]
    assert last_user_turn(recent) == ("debug this algorithm", "smart-chat")
    assert last_user_turn([]) == (None, None)


@pytest.mark.wall_clock
def test_code_fence_detection_is_linear_time_not_quadratic():
    """SECURITY FIX (CodeQL: polynomial regex on uncontrolled data). The
    first version's fence pattern used `\\s*` for leading whitespace, which
    overlaps with what `(?:^|\\n)` already matches — a message that's mostly
    newlines with no closing fence let the engine retry the same run of
    `\\n`s from every line-start position, going quadratic in input length.
    A user-controlled chat message hitting this path is exactly "uncontrolled
    data" — a large adversarial input here must stay fast, not blow up.

    Exercises the compiled pattern directly (not through route_chat_model)
    since route_chat_model short-circuits on the separate long-message
    length check well before an adversarial 200k-char input would ever
    reach the fence regex.
    """
    from app.modules.chat.model_routing.route import _CODE_FENCE

    # No closing fence anywhere — the worst case for a backtracking engine
    # that overlaps whitespace-skipping with the newline it already matched.
    adversarial = "\n" * 200_000
    started = time.perf_counter()
    _CODE_FENCE.search(adversarial)
    elapsed = time.perf_counter() - started
    # Generous ceiling for a slow CI runner; a quadratic implementation on
    # 200k newlines would take many seconds to minutes, not under a second.
    assert elapsed < 2.0


def test_is_reasoning_alias() -> None:
    from app.models.model_catalog import is_reasoning_alias, quota_multiplier

    assert is_reasoning_alias("smart-chat") is True
    assert is_reasoning_alias("glm-5.2") is True
    assert is_reasoning_alias("free-chat") is False
    assert quota_multiplier("free-chat") == 1.0
    assert quota_multiplier("smart-chat") == 3.5
    assert quota_multiplier("glm-5.2") == 3.5


def test_weighted_reserve_tokens_applies_quota_multiplier() -> None:
    from unittest.mock import patch

    from app.core.config import Settings
    from app.modules.chat.turn_resources import weighted_reserve_tokens

    settings = Settings()
    with patch("app.modules.chat.turn_resources.estimate_tokens", return_value=100):
        free = weighted_reserve_tokens(
            content="hello",
            model="free-chat",
            settings=settings,
            max_output=50,
        )
        smart = weighted_reserve_tokens(
            content="hello",
            model="smart-chat",
            settings=settings,
            max_output=50,
        )
    assert free == 150
    assert smart == 525


def test_prompt_weighted_reserve_tokens_uses_full_prompt() -> None:
    from unittest.mock import patch

    from app.core.config import Settings
    from app.modules.chat.turn_resources import prompt_weighted_reserve_tokens

    settings = Settings()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    with patch("app.modules.chat.turn_resources.estimate_tokens", return_value=40):
        assert (
            prompt_weighted_reserve_tokens(
                messages,
                model="free-chat",
                settings=settings,
                max_output=20,
            )
            == 100
        )


@pytest.mark.parametrize(
    "alias,content,expected",
    [
        # auto resolves via route_chat_model
        ("auto", "hello", "qwen-3.7-flash"),
        ("auto", "explain gravity", "qwen-3.7-flash"),
        ("auto", "debug this crash", "smart-chat"),
        # explicit aliases pass through
        ("free-chat", "explain gravity", "free-chat"),
        ("smart-chat", "hi", "smart-chat"),
        ("gpt-6-luna", "anything", "gpt-6-luna"),
    ],
)
def test_resolve_alias(alias: str, content: str, expected: str) -> None:
    pool = [model.id for model in model_catalog.selectable_models()]
    assert resolve_alias_in_pool(alias, content, pool) == expected


def test_auto_hard_question_picks_strongest_when_smart_tier_absent() -> None:
    """Free pool has no smart/max model. Auto used to throw away the
    escalation signal and pick the cheapest fast alias (free-chat). Pick
    the strongest remaining model instead (currently glm-5.3-flash, standard)."""
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    pool = plan_service.free_pool(settings)
    resolved = resolve_alias_in_pool("auto", "prove p = np", pool, settings)
    assert resolved in pool
    assert model_catalog.tier_rank(model_catalog.get(resolved)) == max(
        model_catalog.tier_rank(model_catalog.get(mid)) for mid in pool
    )
    assert resolved != "free-chat"


def test_pick_smart_from_pool_prefers_strongest_not_cheapest() -> None:
    """With several smart models, pick the strongest — not the cheapest
    (smart-chat would win on price)."""
    pool = ["smart-chat", "glm-5.2"]
    assert plan.pick_smart_from_pool(pool) == "glm-5.2"
    cheap = model_catalog.price_sort_key(model_catalog.get("smart-chat"))
    dear = model_catalog.price_sort_key(model_catalog.get("glm-5.2"))
    assert cheap < dear


def test_explicit_weak_pick_does_not_escalate() -> None:
    """An explicit picker alias is a promise — even a hard question stays."""
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    pool = ["free-chat", "smart-chat"]
    assert (
        resolve_alias_in_pool(
            "free-chat",
            "prove this algorithm is O(n log n) and derive the recurrence",
            pool,
            settings,
        )
        == "free-chat"
    )


_VERIFIED_PHYSICS = "calculate the momentum of a 5kg object moving at 12 m/s"


def test_physics_route_declines_when_the_solver_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A solver bug is a decline to the strong model, never a failed turn."""
    import app.modules.physics as physics

    def broken(_intent: object) -> object:
        raise ZeroDivisionError("solver bug")

    monkeypatch.setattr(physics, "solve_physics", broken)
    routing_physics._physics_solves.cache_clear()
    try:
        assert route_chat_model(_VERIFIED_PHYSICS) == "smart-chat"
    finally:
        routing_physics._physics_solves.cache_clear()
    assert "physics routing solve failed" in caplog.text


def test_physics_route_solves_each_line_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.physics as physics

    calls = 0
    real = physics.solve_physics

    def counting(intent: PhysicsIntent) -> PhysicsResult:
        nonlocal calls
        calls += 1
        return real(intent)

    monkeypatch.setattr(physics, "solve_physics", counting)
    routing_physics._physics_solves.cache_clear()
    try:
        for _ in range(3):
            assert route_chat_model(_VERIFIED_PHYSICS) == "qwen-3.7-flash"
            assert (
                route_chat_model(
                    "and its kinetic energy?",
                    prior_user=_VERIFIED_PHYSICS,
                    prior_model="smart-chat",
                )
                is not None
            )
    finally:
        routing_physics._physics_solves.cache_clear()
    assert calls == 1
