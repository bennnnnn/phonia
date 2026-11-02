"""The prompt is ordered for prompt caching, and states each reply policy once.

The first system message is the same text on every turn for one user, so a provider can
reuse it and the gateway can mark it. The turn's rules follow, then the history, then
what changes on every turn (the clock, memory, the schedule), so the next turn of the
chat repeats everything up to its history. A subject's reply policy that two places add
keeps only its copy closest to the user turn. The contracts repeated beside the user
turn on purpose stay repeated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from app.modules.chat.prompt_builder import inject_subject_block
from app.modules.chat.prompt_constants import (
    CLARIFICATION_HINT,
    FACT_GROUNDING_HINT,
    PERSONAL_DISCLOSURE_HINT,
    PHOTO_LOOKUP_HINT,
    SETTINGS_IN_APP_HINT,
    STYLE_HINTS,
    TONE_FORMAT_GUARD,
    UNCLEAR_MESSAGE_HINT,
    learning_plan_daily_contract,
)
from app.modules.chat.prompt_inject import append_after_history, conversation_turns
from app.modules.chat.prompt_repeats import REPLY_POLICIES, last_policy_parts, policies_once
from app.modules.chat.response_tone import EMOJI_HINTS, TONE_HINTS
from app.modules.chat.stream_pipeline import _prior_window
from app.modules.chat.tool_loop.results import ToolResults
from app.modules.chat.tool_loop.rounds import _hand_off
from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_REPLY_POLICY
from app.modules.physics.reply_policy import PHYSICS_REPLY_POLICY
from app.modules.web_search import WEB_SEARCH_HINT
from app.services.locale import locale_system_hint
from app.services.workout import MATH_WORKOUT_PROMPT_RULE
from app.tests.behavior import harness
from app.tests.behavior.cases import Case, Expect
from app.tests.behavior.sweep import frozen_clock
from app.tests.modules.chat.chat_test_support import system_prompt
from app.tests.modules.chat.test_prompt_golden import _DEFAULTS, render, resolve

_IDENTITY = "You are Recall, a helpful personal AI assistant."
_NINE = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
_SEVEN_PAST = datetime(2026, 10, 14, 6, 7, tzinfo=UTC)
_QUERY = "what should I cook tonight?"
# A rich turn in a chat with one earlier exchange: memory, schedule and clock all load.
_RICH: dict[str, Any] = {
    "history": [["user", "hi"], ["assistant", "Hey Bini!"], ["user", _QUERY]],
    "kwargs": {"query_text": _QUERY, "rich_context": True, "advice_memory": True, "current": 2},
}
# One user's chat: a meal, a follow-up, a definition, thanks, a detail request, a
# draft and its revision, then two facts.
_CHAT = (
    _QUERY,
    "how do I make it vegan?",
    "what is tempeh?",
    "thanks!",
    "explain in detail how fermentation works",
    "can you write an email to my landlord about the broken heater?",
    "make it shorter",
    "what is the capital of Peru?",
    "and of Chile?",
)
_LESSON = (
    ("user", "teach me python loops"),
    (
        "assistant",
        "## Lesson 1: for loops\n\nA `for` loop repeats code for each item.\n\n"
        '```quiz\n{"question": "What does range(3) give?"}\n```',
    ),
)


def _turn(query: str, **kwargs: Any) -> dict[str, Any]:
    """A golden case whose only message is ``query``."""
    return {"history": [["user", query]], "kwargs": {"query_text": query, "current": 0, **kwargs}}


async def _prompt_at(when: datetime, **case: Any) -> list[dict[str, str]]:
    with patch("app.tests.behavior.sweep.SWEEP_NOW", when):
        messages, _out = await render(resolve({**_RICH, **case}, _DEFAULTS))
    return messages


async def _real_prompt(text: str, history: Any = (), **case: Any) -> list[dict[str, Any]]:
    """The prompt the real turn path sends for ``text`` (the behavior harness, IO stubbed)."""
    captured: dict[str, list[dict[str, Any]]] = {}
    run_tool_loop = harness.run_tool_loop_path

    async def capture(*args: Any, **kwargs: Any) -> None:
        captured["messages"] = list(args[3].prompt_messages)
        await run_tool_loop(*args, **kwargs)

    with frozen_clock(), patch.object(harness, "run_tool_loop_path", capture):
        await harness.route_case(Case("cache", "x", text, Expect(), "", history=history, **case))
    return captured["messages"]


@pytest.mark.asyncio
async def test_the_marked_message_is_the_same_on_every_kind_of_turn_for_one_user() -> None:
    history: list[tuple[str, str]] = []
    prompts = []
    for text in _CHAT:
        prompts.append(await _real_prompt(text, tuple(history)))
        history += [("user", text), ("assistant", "Sure — here is an answer.")]
    prompts += [
        await _real_prompt("what does a capybara look like?"),
        await _real_prompt("next", _LESSON),
        await _real_prompt("solve 2x + 5 = 17 and explain why each step works"),
        await _real_prompt("coffee near me", location="Addis Ababa, Ethiopia"),
        await _real_prompt("I work at Uber as a data analyst"),
    ]
    stable = {prompt[0]["content"] for prompt in prompts}
    assert stable == {
        "\n\n".join(
            (
                _IDENTITY,
                TONE_HINTS["casual"],
                EMOJI_HINTS["some"],
                TONE_FORMAT_GUARD,
                UNCLEAR_MESSAGE_HINT,
                SETTINGS_IN_APP_HINT,
                locale_system_hint("en"),
            )
        )
    }
    # What the turns differ in (length, style, profile, place, clock) comes after it.
    assert all(prompt[1]["role"] == "system" for prompt in prompts)
    assert len({prompt[1]["content"] for prompt in prompts}) > len(prompts) // 2
    for text in ("Response length", "User's first name", "Current local time", "Addis Ababa"):
        assert all(text not in prompt[0]["content"] for prompt in prompts)
    # The clock comes after the history, never in the rules before it.
    for text in ("Current local time", "Digital clock now"):
        assert all(text not in prompt[1]["content"] for prompt in prompts)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        # A greeting (lightweight), a slim question, a rich memory turn, a draft that
        # carries the account email, a nearby ask with the device location, and a maths
        # follow-up that adds its policy.
        _turn("hi", lightweight=True),
        _turn("what is a capybara"),
        {"memory_block": "## Preferences\n- Vegetarian."},
        _turn("write an email to my boss asking for Friday off", rich_context=True),
        _turn("coffee near me", rich_context=True, prompt_location="Addis Ababa, Ethiopia"),
        {
            "history": [["user", "solve 2x + 5 = 17"], ["assistant", "x = 6"], ["user", "how?"]],
            "kwargs": {"query_text": "how?", "current": 2},
        },
    ],
)
async def test_their_own_instructions_and_language_are_part_of_the_same_text(
    case: dict[str, Any],
) -> None:
    user = {"custom_instructions": "Keep it upbeat.", "locale": "es", "job": "Designer"}
    messages = await _prompt_at(_NINE, user=user, **case)
    stable = messages[0]["content"]
    tone = f"{TONE_HINTS['casual']}\n\n{EMOJI_HINTS['some']}"
    assert stable.startswith(f"{_IDENTITY}\n\n{tone}\n\n{TONE_FORMAT_GUARD}")
    assert "Keep it upbeat." in stable
    assert stable.endswith(locale_system_hint("es"))
    reference = await _prompt_at(_SEVEN_PAST, user=user, memory_block="other memory")
    assert stable == reference[0]["content"]


@pytest.mark.asyncio
async def test_at_another_time_with_other_memory_only_the_context_after_the_history_changes() -> (
    None
):
    first = await _prompt_at(
        _NINE,
        memory_block="## Preferences\n- Vegetarian.",
        todos_section="Open reminders:\n- Pay rent (due Fri Oct 16)",
    )
    later = await _prompt_at(
        _SEVEN_PAST,
        memory_block="## Preferences\n- Vegetarian.\n- Allergic to peanuts.",
        todos_section="Open reminders:\n- Call the dentist (overdue by 2 days)",
    )
    # The stable message, the rules and the history: the prefix the provider reuses.
    assert first[:4] == later[:4]
    assert [message["role"] for message in first[2:4]] == ["user", "assistant"]
    # Then the turn's own context: its clock, memory and schedule, before the user turn.
    context, later_context = first[4]["content"], later[4]["content"]
    assert first[4]["role"] == "system" and context != later_context
    assert first[-1] == later[-1] == {"role": "user", "content": _QUERY}
    assert "9:00:00 AM" in context and "9:07:00 AM" in later_context
    for turn_only in ("Current local time", "Digital clock now", "Vegetarian", "Pay rent"):
        assert all(turn_only not in message["content"] for message in first[:4])
        assert turn_only in context


@pytest.mark.asyncio
async def test_the_users_own_text_first_then_the_turns_steadiest_parts_first() -> None:
    messages = await _prompt_at(
        _NINE,
        memory_block="## Preferences\n- Vegetarian.",
        todos_section="Open reminders:\n- Pay rent",
        user={"custom_instructions": "Keep it upbeat.", "locale": "es", "job": "Designer"},
        kwargs={**_RICH["kwargs"], "summary": "They planned a trip to Lalibela."},
    )
    stable, rules = messages[0]["content"], messages[1]["content"]
    users_own = (_IDENTITY, TONE_FORMAT_GUARD, UNCLEAR_MESSAGE_HINT, "Keep it upbeat.", "code: es")
    assert [stable.index(t) for t in users_own] == sorted(stable.index(t) for t in users_own)
    # The rules: length, style pack, lookups, profile, summary.
    turns = (
        STYLE_HINTS["balanced"],
        CLARIFICATION_HINT,
        FACT_GROUNDING_HINT,
        WEB_SEARCH_HINT,
        PHOTO_LOOKUP_HINT,
        "- Job: Designer",
        "Lalibela",
    )
    assert rules.startswith(STYLE_HINTS["balanced"])
    assert [rules.index(text) for text in turns] == sorted(rules.index(t) for t in turns)
    # After the history: the clock, memory and schedule.
    context = messages[-2]["content"]
    assert messages[-2]["role"] == "system"
    later = ("Current local time:", "Digital clock now", "Vegetarian", "Pay rent")
    assert [context.index(text) for text in later] == sorted(context.index(t) for t in later)
    # The user's latest message stays last.
    assert messages[-1] == {"role": "user", "content": _QUERY}


@pytest.mark.asyncio
async def test_the_disclosure_contract_keeps_its_repeat_closest_to_the_user_turn() -> None:
    query = "I work at Uber as a data analyst"
    messages = await _prompt_at(
        _NINE, history=[["user", query]], kwargs={"query_text": query, "current": 0}
    )
    # In the exclusive pack, and again last: a small model follows the nearer one.
    assert system_prompt(messages).count(PERSONAL_DISCLOSURE_HINT) == 2
    assert messages[-2]["content"].endswith(PERSONAL_DISCLOSURE_HINT)


@pytest.mark.asyncio
async def test_a_plan_contract_keeps_its_repeat_beside_the_user_turn() -> None:
    query = "make me a 7-day plan to learn SQL"
    messages = await _prompt_at(
        _NINE, history=[["user", query]], kwargs={"query_text": query, "current": 0}
    )
    contract = learning_plan_daily_contract(query)
    assert contract
    assert sum(message["content"].count(contract) for message in messages) == 2
    assert messages[-2] == {"role": "system", "content": contract}


_RULES = {"role": "system", "content": "rules"}
_EXCHANGE = [{"role": "user", "content": "solve 2x = 4"}, {"role": "assistant", "content": "x = 2"}]


def test_the_context_goes_after_the_history_and_never_splits_an_exchange() -> None:
    line = {"role": "user", "content": "how?"}
    block = {"role": "system", "content": "Current local time: 9:00 AM"}
    # Before the turn's own line when the prompt ends with it.
    assert append_after_history([_RULES, *_EXCHANGE, line], block["content"]) == [
        _RULES,
        *_EXCHANGE,
        block,
        line,
    ]
    # At the end when it does not: never between a question and its reply.
    assert append_after_history([_RULES, *_EXCHANGE], block["content"]) == [
        _RULES,
        *_EXCHANGE,
        block,
    ]


def test_readers_of_the_last_exchange_see_the_conversation_only() -> None:
    context = {"role": "system", "content": "Current local time: 9:00 AM"}
    line = {"role": "user", "content": "why?"}
    results = {"role": "system", "content": "Web search results"}
    prompt = [_RULES, *_EXCHANGE, context, line, results]
    assert conversation_turns(prompt) == [*_EXCHANGE, line]
    # Follow-up suggestions read the exchange before the line, its reply last.
    assert _prior_window(prompt) == _EXCHANGE


def test_only_a_reply_policy_is_left_out_where_it_comes_again() -> None:
    p = MATH_REPLY_POLICY
    stable, turn, nearby = last_policy_parts(["A", p, "B", "C"], ["C", p], ["C", "D"])
    assert (stable, turn, nearby) == (["A", "B", "C"], ["C", p], ["C", "D"])
    assert last_policy_parts(["A", "B"], []) == [["A", "B"], []]


def test_every_subject_reply_policy_is_kept_once() -> None:
    assert set(REPLY_POLICIES) == {MATH_REPLY_POLICY, PHYSICS_REPLY_POLICY}


@pytest.mark.parametrize("policy", [MATH_REPLY_POLICY, PHYSICS_REPLY_POLICY])
def test_a_solve_block_keeps_the_policy_and_the_system_prompt_drops_its_copy(policy: str) -> None:
    turn = f"Response length: fit.\n\nFORMAT\n\n{policy}\n\nCurrent local time: 9:00 AM"
    block = (
        f"[BEGIN VERIFIED]\nx = 6\n[END VERIFIED]\n\nReply guidance: data, not a lesson. {policy}"
    )
    prompt = [
        {"role": "system", "content": _IDENTITY},
        {"role": "system", "content": turn},
        {"role": "system", "content": block},
        {"role": "user", "content": "solve 2x + 5 = 17 and explain"},
    ]
    once = policies_once(prompt)
    assert once[1]["content"] == "Response length: fit.\n\nFORMAT\n\nCurrent local time: 9:00 AM"
    assert [once[0], *once[2:]] == [prompt[0], *prompt[2:]]
    # The prompt it was given is left as it was.
    assert prompt[1]["content"] == turn


def test_a_users_pasted_policy_is_their_text_and_does_not_count() -> None:
    pasted = f"My teacher gave me this rubric, does it make sense? {MATH_REPLY_POLICY}"
    prompt = [
        {"role": "system", "content": _IDENTITY},
        {"role": "system", "content": f"FORMAT\n\n{MATH_REPLY_POLICY}"},
        {"role": "user", "content": pasted},
        {"role": "assistant", "content": MATH_REPLY_POLICY},
    ]
    # No later system copy: the system prompt keeps its own, and no other message changes.
    assert policies_once(prompt) == prompt
    block = {"role": "system", "content": f"[BEGIN VERIFIED MATH]x = 6\n\n{MATH_REPLY_POLICY}"}
    once = policies_once([*prompt[:3], block, prompt[3]])
    assert [message["content"] for message in once] == [
        _IDENTITY,
        "FORMAT",
        pasted,
        block["content"],
        MATH_REPLY_POLICY,
    ]


def test_a_policy_left_alone_in_its_message_drops_the_message() -> None:
    prompt = [
        {"role": "system", "content": MATH_REPLY_POLICY},
        {
            "role": "system",
            "content": f"Unverified: no solver result.\n\n{MATH_REPLY_POLICY} Check it.",
        },
        {"role": "user", "content": "x"},
    ]
    assert policies_once(prompt) == prompt[1:]


def test_a_policy_joined_mid_sentence_leaves_the_sentence_whole() -> None:
    note = f"Math note: not verified.\n\n{MATH_REPLY_POLICY} Check it yourself."
    prompt = [
        {"role": "system", "content": note},
        {"role": "system", "content": MATH_REPLY_POLICY},
    ]
    assert policies_once(prompt)[0]["content"] == "Math note: not verified.\n\nCheck it yourself."


def test_injecting_a_solve_block_leaves_one_policy_in_the_prompt() -> None:
    prompt = [
        {"role": "system", "content": _IDENTITY},
        {"role": "system", "content": f"STYLE\n\n{MATH_REPLY_POLICY}"},
        {"role": "user", "content": "solve 2x + 5 = 17 and explain"},
    ]
    block = f"[BEGIN VERIFIED MATH]\nx = 6\n[END VERIFIED MATH]\n\n{MATH_REPLY_POLICY}"
    injected = inject_subject_block(prompt, block)
    assert [message["content"] for message in injected] == [
        _IDENTITY,
        "STYLE",
        block,
        "solve 2x + 5 = 17 and explain",
    ]
    # Without a solve block nothing is taken out.
    assert inject_subject_block(prompt, None) == prompt


def test_a_sympy_round_keeps_the_policy_after_its_results_only() -> None:
    pasted = f"integrate x e^x dx, my notes say: {MATH_REPLY_POLICY}"
    working: list[dict[str, Any]] = [
        {"role": "system", "content": f"STYLE\n\n{MATH_REPLY_POLICY}"},
        {"role": "system", "content": f"BLOCK\n\n{MATH_REPLY_POLICY}"},
        {"role": "user", "content": pasted},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "1", "function": {"name": "sympy", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "1", "content": "x e^x - e^x + C"},
    ]
    outcome = _hand_off(working, 3, ToolResults())
    contents = [message.get("content") for message in outcome.messages]
    assert contents[:3] == ["STYLE", "BLOCK", pasted]
    assert contents[-1] == MATH_REPLY_POLICY
    systems = [m["content"] for m in outcome.messages if m["role"] == "system"]
    assert sum(MATH_REPLY_POLICY in content for content in systems) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt, policy",
    [
        ("solve 2x + 5 = 17 and explain why each step works", MATH_REPLY_POLICY),
        (
            # A network the server does not read: the model writes the working.
            "A 4 ohm and a 6 ohm resistor are in series, and that pair is in parallel with a "
            "12 ohm resistor across a 12 V battery. Find the current from the battery.",
            PHYSICS_REPLY_POLICY,
        ),
    ],
)
async def test_a_model_written_stem_turn_states_its_policy_once(prompt: str, policy: str) -> None:
    """Through the real turn path: the subject pack and the solve block both carry it."""
    route = await harness.route_case(Case("policy-once", "stem", prompt, Expect(), ""))
    assert not route.instant
    assert route.system_prompt.count(policy) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    [
        "solve 2x + 5 = 17 and explain why each step works",
        # Both in the rules: the money turn's maths pack, closed by the policy.
        "I owe 5000 on my credit card at 22% apr and pay 200 a month, how long to pay off",
    ],
)
async def test_a_maths_turn_states_the_worked_solution_layout_once(prompt: str) -> None:
    """The maths pack and its reply policy both carried the layout rule (~460 tokens)."""
    route = await harness.route_case(Case("layout-once", "math", prompt, Expect(), ""))
    assert not route.instant
    assert MATH_INTENT_HINT in route.system_prompt
    assert route.system_prompt.count(MATH_WORKOUT_PROMPT_RULE) == 1
