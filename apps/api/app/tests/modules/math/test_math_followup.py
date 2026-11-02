"""A brief math explanation follows its adjacent exchange without importing stale topics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.prompt_builder import build_prompt_messages
from app.modules.chat.prompt_context import _PromptContextBlocks
from app.modules.chat.prompt_inject import conversation_turns
from app.modules.math.followup import (
    MATH_FOLLOWUP_HINT,
    is_math_followup,
    math_working_followup_problem,
    offered_equation_problem,
    open_math_problem,
    readable_standalone_answer,
    restated_math_problem,
)
from app.modules.math.reply_policy import MATH_REPLY_POLICY
from app.tests.modules.chat.chat_test_support import system_prompt

_EQUATION_ASK = "Solve 2x + 7 = 19"
_EQUATION_RESULT = "x = 6"
_TAYLOR_ASK = "Find the Taylor series of exp(x) at 1 order 2"
_TAYLOR_RESULT = r"\frac{e \left(x - 1\right)^{2}}{2} + e \left(x - 1\right) + e"


def _message(role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), role=role, content=content)


@pytest.mark.parametrize(
    ("text", "prior", "reopened"),
    [
        ("x", ["3x^2 + 3 = 5"], True),
        ("5", ["3x^2 + 3 = 5"], True),
        ("-2.5", ["3x^2 + 3 = 5"], True),
        ("$y$", ["2x + y = 7"], True),
        ("for x", ["3x^2 + 3 = 5"], True),
        (r"$\theta$", [r"$2\sin(\theta) = 1$"], True),
        ("x", [r"solve $2x+1\leq 7$"], True),
        # An earlier fragment on the same equation is walked past.
        ("5", ["3x^2 + 3 = 5", "x"], True),
        ("hi", ["3x^2 + 3 = 5"], False),
        ("2x + 1 = 7", ["3x^2 + 3 = 5"], False),
        # A message in between ends the equation.
        ("x", ["3x^2 + 3 = 5", "thanks, what about dinner?"], False),
        # Only an equation is in progress; a conversion has no unknown to name.
        ("5", ["convert 1 m to cm"], False),
        # A question or new input is a message of its own.
        ("What?", ["convert 1 m to cm"], False),
        ("What?", ["3x^2 + 3 = 5"], False),
        ("$[4,4]$", ["convert 1 m to cm"], False),
        ("[4,4]", ["3x^2 + 3 = 5"], False),
    ],
)
def test_open_math_problem_reopens_only_for_a_fragment(
    text: str, prior: list[str], reopened: bool
) -> None:
    assert open_math_problem(text, prior) == (prior[0] if reopened else None)


@pytest.mark.parametrize("text", ["$[4,4]$", "What?"])
@pytest.mark.asyncio
async def test_new_input_after_a_conversion_is_not_the_conversion_again(text: str) -> None:
    from app.modules.math.tools.prompt import build_math_augmentation

    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    _block, verified = await build_math_augmentation(
        text, settings, prior_user_messages=["convert 1 m to cm"]
    )
    assert verified is None


def _exchange(
    question: str = _EQUATION_ASK, result: str = _EQUATION_RESULT
) -> list[SimpleNamespace]:
    return [_message("user", question), _message("assistant", f"```answer\n{result}\n```")]


@pytest.mark.parametrize(
    "query",
    [
        "how",
        "How?",
        "why?",
        "please explain it",
        "can you show the steps?",
        "explain step by step",
        "prove it",
        "show the proof",
        "hint only",
        "give me a hint",
        "give examples",
        "explain with an example",
        "What?",
        "Do it again",
    ],
)
def test_short_referential_request_uses_immediate_math_exchange(query: str) -> None:
    assert is_math_followup(query, _exchange())


def test_how_after_a_stated_sum_continues_that_sum() -> None:
    question = "What is the result of 7 + 9?"
    recent = _exchange(question, "The sum of 7 + 9 is 16.")
    assert is_math_followup("How", recent)
    assert math_working_followup_problem("How", recent) == question


@pytest.mark.parametrize(
    "query",
    [
        "how",
        "How?",
        "why?",
        "please explain it",
        "can you show the steps?",
        "What?",
        "Do it again",
    ],
)
def test_working_followup_returns_the_adjacent_problem_for_verified_replay(query: str) -> None:
    recent = _exchange("3x^2 + 3 = 5", r"x = \pm \frac{\sqrt{6}}{3}")
    assert math_working_followup_problem(query, recent) == "3x^2 + 3 = 5"
    as_dicts = [{"role": item.role, "content": item.content} for item in recent]
    assert math_working_followup_problem(query, as_dicts) == "3x^2 + 3 = 5"


@pytest.mark.parametrize("query", ["hint only", "prove it", "give examples"])
def test_scoped_followups_do_not_replay_the_full_verified_working(query: str) -> None:
    assert is_math_followup(query, _exchange())
    assert math_working_followup_problem(query, _exchange()) is None


def test_referential_chain_keeps_the_original_verified_problem() -> None:
    recent = [
        *_exchange("456/56", r"8\text{ remainder }8"),
        _message("user", "What?"),
        _message("assistant", "Here is the verified long division."),
        _message("user", "Show me"),
        _message("assistant", "Here is the written method again."),
    ]
    assert math_working_followup_problem("Do it again", recent) == "456/56"


@pytest.mark.parametrize(
    "query",
    [
        "how is the weather?",
        "how do I cook rice?",
        "explain photosynthesis",
        "why is the sky blue?",
        "how, and book a table",
        "how and solve x=2",
        "give me examples of dogs",
        "hi",
        "thanks",
        "",
        None,
        "how " * 40,
    ],
)
def test_unrelated_or_additional_request_does_not_inherit_math(query: str | None) -> None:
    assert not is_math_followup(query, _exchange())


@pytest.mark.parametrize(
    "recent",
    [
        [],
        [_message("assistant", "5")],
        [_message("user", _EQUATION_ASK)],
        [
            *_exchange(),
            _message("user", "Tell me about dogs"),
            _message("assistant", "Dogs are mammals."),
        ],
        [*_exchange(), _message("user", "hi"), _message("assistant", "Hello")],
        [*_exchange(), _message("user", "how")],
        [_message("user", _EQUATION_ASK), _message("assistant", "")],
        [_message("assistant", "5"), _message("user", _EQUATION_ASK)],
    ],
)
def test_no_lookback_through_an_incomplete_or_unrelated_exchange(
    recent: list[SimpleNamespace],
) -> None:
    assert not is_math_followup("how", recent)


@pytest.mark.parametrize(
    "body", [_EQUATION_RESULT, _TAYLOR_RESULT, r"x = 2 \pi k,\quad k\in\mathbb{Z}"]
)
def test_standalone_answer_preserves_full_math_without_an_owned_fence(body: str) -> None:
    assert (
        readable_standalone_answer(f"```answer\n{body}\n```\n")
        == f"Previous result:\n\\[\n{body}\n\\]"
    )


@pytest.mark.parametrize(
    "content",
    [
        "```answer\n",
        "```answer\nx=2",
        "```answer\n\n```",
        "````answer\nx=2\n````",
        "```answer extra\nx=2\n```",
        "text\n```answer\nx=2\n```",
        "```answer\nx=2\n```\nextra",
        "```answer\n$x=2$\n```",
        '```answer\n{"type":"geometry","width":3}\n```',
        "```answer\n[1,2]\n```",
        "```answer\nx=2\n```\n```geometry\n{}\n```",
        "```answer\nx=2\n```\n```answer\ny=3\n```",
        "```python\n```answer\nx=2\n```\n```",
        "```geometry\n{}\n```",
        "```answer\n" + "x" * 4001 + "\n```",
    ],
)
def test_incomplete_mixed_or_payload_fences_are_not_retained_as_math(content: str) -> None:
    assert readable_standalone_answer(content) is None


async def _prompt(
    query: str,
    recent: list[SimpleNamespace],
    omit_message_ids: set[UUID] | None = None,
    current_user_message_id: UUID | None = None,
) -> list[dict[str, str]]:
    user = User(
        id=uuid4(),
        name="Test",
        email="test@example.com",
        locale="en",
        timezone="UTC",
    )
    blocks = _PromptContextBlocks(
        memory_block="",
        todos_section=None,
        recent_all=recent,
        attachment_rag_block="",
        chat=None,
    )
    with patch(
        "app.modules.chat.prompt_builder._load_context_blocks", AsyncMock(return_value=blocks)
    ):
        return await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False),
            query_text=query,
            rich_context=False,
            recent_messages=recent,
            omit_message_ids=omit_message_ids,
            current_user_message_id=current_user_message_id,
        )


def _context(prepared: list[dict[str, str]]) -> str:
    """The turn's context after the history, where a follow-up's policy goes."""
    return [m for m in prepared[2:] if m["role"] == "system"][-1]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,result", [(_EQUATION_ASK, _EQUATION_RESULT), (_TAYLOR_ASK, _TAYLOR_RESULT)]
)
async def test_actual_how_examples_keep_prior_result_and_final_scoped_policy(
    question: str, result: str
) -> None:
    recent = _exchange(question, result)
    prepared = await _prompt("how", recent)
    assert _context(prepared).endswith(f"{MATH_REPLY_POLICY}\n\n{MATH_FOLLOWUP_HINT}")
    # The math pack's own closing copy goes: the policy is stated once, last.
    assert system_prompt(prepared).count(MATH_REPLY_POLICY) == 1
    turns = conversation_turns(prepared)
    assert turns[-2] == {"role": "user", "content": question}
    assert turns[-1] == {"role": "assistant", "content": f"Previous result:\n\\[\n{result}\n\\]"}
    assert MATH_FOLLOWUP_HINT in system_prompt(prepared)
    assert recent[-1].content == f"```answer\n{result}\n```"
    history = [item for item in prepared if item["role"] != "system"]
    assert all("```answer" not in item["content"] for item in history)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["prove it", "hint only", "give examples"])
async def test_followup_policy_preserves_requested_proof_hint_and_examples(query: str) -> None:
    prepared = await _prompt(query, _exchange())
    policy = _context(prepared)
    assert policy.endswith(MATH_FOLLOWUP_HINT)
    assert MATH_FOLLOWUP_HINT in policy
    assert MATH_FOLLOWUP_HINT in policy


@pytest.mark.asyncio
async def test_previous_nonmath_exchange_does_not_gain_policy_from_older_math() -> None:
    recent = [
        *_exchange(),
        _message("user", "How are clouds made?"),
        _message("assistant", "Water vapor condenses."),
    ]
    prepared = await _prompt("how", recent)
    assert MATH_FOLLOWUP_HINT not in system_prompt(prepared)
    assert MATH_REPLY_POLICY not in system_prompt(prepared)
    assert prepared[3]["content"] == f"Answer: {_EQUATION_RESULT}\n"
    assert conversation_turns(prepared)[-1]["content"] == "Water vapor condenses."


@pytest.mark.asyncio
async def test_nonreferential_question_reads_the_answer_as_a_plain_line() -> None:
    prepared = await _prompt("how do I cook rice?", _exchange())
    assert MATH_FOLLOWUP_HINT not in system_prompt(prepared)
    assert conversation_turns(prepared)[-1]["content"] == f"Answer: {_EQUATION_RESULT}\n"


@pytest.mark.asyncio
async def test_followup_never_reintroduces_geometry_graph_or_tool_payloads() -> None:
    recent = [
        _message("user", "Find area of a rectangle 3 by 4"),
        _message(
            "assistant", 'Area is 12.\n```geometry\n{"width":3}\n```\n```graph\n{"points":[]}\n```'
        ),
    ]
    prepared = await _prompt("how", recent)
    assert _context(prepared).endswith(MATH_FOLLOWUP_HINT)
    reply = conversation_turns(prepared)[-1]["content"]
    assert reply.strip() == "Area is 12."
    assert "width" not in reply
    assert "points" not in reply


@pytest.mark.asyncio
async def test_regenerated_how_keeps_prior_result_and_persisted_current_user() -> None:
    recent = [*_exchange(), _message("user", "how"), _message("assistant", "Old explanation")]
    prepared = await _prompt("how", recent, omit_message_ids={recent[-1].id})
    assert _context(prepared).endswith(MATH_FOLLOWUP_HINT)
    assert conversation_turns(prepared)[-2] == {
        "role": "assistant",
        "content": f"Previous result:\n\\[\n{_EQUATION_RESULT}\n\\]",
    }
    assert prepared[-1] == {"role": "user", "content": "how"}
    assert all("Old explanation" not in item["content"] for item in prepared)


@pytest.mark.asyncio
async def test_unrelated_omission_does_not_strip_an_incomplete_current_user() -> None:
    older = _message("assistant", "Older answer")
    recent = [older, *_exchange(), _message("user", "how")]
    prepared = await _prompt("how", recent, omit_message_ids={older.id})
    assert MATH_FOLLOWUP_HINT not in system_prompt(prepared)
    assert conversation_turns(prepared)[-2]["content"] == f"Answer: {_EQUATION_RESULT}\n"
    assert prepared[-1] == {"role": "user", "content": "how"}


@pytest.mark.asyncio
async def test_explicit_current_user_id_keeps_the_previous_completed_math_exchange() -> None:
    recent = [*_exchange(), _message("user", "how")]
    prepared = await _prompt("how", recent, current_user_message_id=recent[-1].id)
    assert _context(prepared).endswith(MATH_FOLLOWUP_HINT)
    previous = conversation_turns(prepared)[-2]["content"]
    assert previous == f"Previous result:\n\\[\n{_EQUATION_RESULT}\n\\]"
    assert prepared[-1] == {"role": "user", "content": "how"}


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["missing", "different", "earlier"])
async def test_matching_query_without_current_turn_identity_is_not_sufficient(
    identity: str,
) -> None:
    recent = [*_exchange(), _message("user", "how")]
    message_id = (
        None if identity == "missing" else (uuid4() if identity == "different" else recent[0].id)
    )
    prepared = await _prompt("how", recent, current_user_message_id=message_id)
    assert MATH_FOLLOWUP_HINT not in system_prompt(prepared)
    assert conversation_turns(prepared)[-2]["content"] == f"Answer: {_EQUATION_RESULT}\n"


@pytest.mark.asyncio
async def test_current_turn_id_with_changed_content_does_not_hijack_previous_math() -> None:
    recent = [*_exchange(), _message("user", "how do I cook rice?")]
    prepared = await _prompt("how", recent, current_user_message_id=recent[-1].id)
    assert MATH_FOLLOWUP_HINT not in system_prompt(prepared)


def test_do_it_solves_the_equation_the_assistant_just_offered() -> None:
    offered = (
        "Sure! Here's another similar quadratic equation to solve:\n\n"
        "5x^2 \u2212 3 = \u22123\n\n"
        "Let me know if you'd like the step-by-step solution."
    )
    recent = [
        _message("user", "3x^2+4=4"),
        _message("assistant", "x = 0\n```answer\nx = 0\n```"),
        _message("user", "Create another one"),
        _message("assistant", offered),
    ]
    assert offered_equation_problem("Do it", recent) == "5x^2 - 3 = -3"
    assert offered_equation_problem("yes", recent) == "5x^2 - 3 = -3"
    # The finished lesson is not offered again.
    assert offered_equation_problem("Do it", recent[:2]) is None
    assert (
        offered_equation_problem(
            "Do it",
            [
                _message("user", "draw a dog"),
                _message("assistant", "Here is a dog."),
            ],
        )
        is None
    )
    assert (
        offered_equation_problem(
            "Do it",
            [
                _message("user", "solve"),
                _message("assistant", "3x^2+4=4\n3x^2=0\nx=0"),
            ],
        )
        is None
    )


def test_do_it_after_a_word_problem_does_not_solve_the_formula_in_its_hint() -> None:
    """``F = ma`` in a hint is the law the problem uses, not an equation to solve.

    "Do it" after the assistant set a sled problem answered a verified "no
    solution": the hint's only equation was solved for an x it did not have.
    """
    problem = (
        "**Problem:** A 5 kg sled is pulled across a frictionless ice surface by a "
        "horizontal rope that exerts a constant force of 20 N. The sled starts from rest.\n\n"
        "1. Find the sled's acceleration.\n2. Determine its speed after 3 seconds.\n"
        "3. Compute the distance it travels in those 3 seconds.\n\n"
        "*Hint:* Use $F = ma$ for (a), $v = at$ for (b), and $s = \\frac12 a t^2$ for (c)."
    )
    recent = [_message("user", "Give me a problem"), _message("assistant", problem)]
    for go_ahead in ("Do it", "Solve it", "yes"):
        assert offered_equation_problem(go_ahead, recent) is None


@pytest.mark.parametrize(
    ("query", "problem"),
    [
        ("what if it was 2x + 5 = 21?", "2x + 5 = 21"),
        ("what about 2x + 5 = 21", "2x + 5 = 21"),
        ("ok now try 3x - 4 = 11", "3x - 4 = 11"),
        # No equation after the lead, or an expression with no relation.
        ("what about it", None),
        ("what about 2x + 5", None),
        # A clock time and a word are not an equation in an unknown.
        ("what about lunch = 12", None),
    ],
)
def test_restated_math_problem_reads_the_new_equation(query: str, problem: str | None) -> None:
    assert restated_math_problem(query, _exchange()) == problem


def test_restated_math_problem_needs_an_adjacent_math_exchange() -> None:
    recent = [_message("user", "How are clouds made?"), _message("assistant", "Water vapor.")]
    assert restated_math_problem("what about 2x + 5 = 21", recent) is None
