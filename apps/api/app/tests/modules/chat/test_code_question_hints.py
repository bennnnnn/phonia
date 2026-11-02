"""Pasted code to explain or fix gets a line-by-line contract written in code ink.

"Explain this code line by line" used to get bullets that mixed `$2$` maths into
the code's values, and a pasted Java loop was read as algebra (`i <= 3`), which
pulled in the whole `$...$` maths pack.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.prompt_builder import build_prompt_messages
from app.modules.chat.prompt_constants import (
    CODE_INK_REMINDER,
    FORMAT_CONTRACT,
    MATH_FENCE_SAFETY_HINT,
    SHORT_RESPONSE_FORMAT_HINT,
    TEACHING_HINT,
    WALKTHROUGH_HINT,
)
from app.modules.chat.prompt_constants.coding import CODE_DEBUG_HINT, CODE_EXPLAIN_HINT
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.conversation import chats_repository, messages_repository
from app.modules.math.reply_policy import MATH_INTENT_HINT
from app.modules.turn_reading.coding import code_question_kind, has_code_syntax, is_programming_turn
from app.services.subjects.dispatch import detect_subject
from app.tests.modules.chat.chat_test_support import system_prompt

TRACE_LOOP = (
    "Explain this code line by line, then show the value of total after each iteration:\n"
    "total = 0\nfor n in [2, 4, 6]:\n    total += n\nprint(total)"
)
ONE_LINE_LOOP = (
    "Explain this code line by line, then show the value of total after each iteration: "
    "total = 0 for n in [2, 4, 6]: total += n print(total)"
)
INDEX_ERROR = (
    "Why does this code fail, and how would you fix it? numbers = [1, 2, 3] print(numbers[3])"
)
JAVA_LOOP = (
    "What does this Java code print? int sum = 0; for (int i = 1; i <= 3; i++) "
    "{ sum += i; } System.out.println(sum);"
)


def _hints(text: str) -> list[str]:
    return _style_format_hints(
        query_text=text,
        is_day_plan=False,
        minimal_personal_context=False,
        image_search_enabled=True,
    )


@pytest.mark.parametrize(
    "text, kind",
    [
        (TRACE_LOOP, "explain"),
        (ONE_LINE_LOOP, "explain"),
        ("what will this print? for i in range(3): print(i)", "explain"),
        (JAVA_LOOP, "explain"),
        (
            "Walk me through this JavaScript: const nums = [1, 2, 3]; "
            "const doubled = nums.map(n => n * 2); console.log(doubled);",
            "explain",
        ),
        ("```python\nx = [1, 2]\ny = x\ny.append(3)\n```\nwhat does this do?", "explain"),
        (INDEX_ERROR, "debug"),
        ("```python\nx = [1, 2]\nprint(x[5])\n```\nwhat's wrong with this", "debug"),
        (
            "I get this error, what's wrong?\nTraceback (most recent call last):\n"
            '  File "app.py", line 3, in <module>\n    print(user["name"])\n'
            "KeyError: 'name'",
            "debug",
        ),
        (
            "why does this return undefined? function add(a, b) { a + b } console.log(add(2, 3))",
            "debug",
        ),
        ("Explain why this fails: nums = [3, 1] nums.sort() print(nums[2])", "debug"),
    ],
)
def test_code_question_kind_reads_pasted_code(text: str, kind: str) -> None:
    assert code_question_kind(text) == kind


@pytest.mark.parametrize(
    "text",
    [
        "explain the code of conduct",
        "line by line poem analysis of The Road Not Taken",
        "fix my sleep schedule",
        "why does my car fail inspection",
        "where is the error in my code",
        "explain recursion",
        "explain two sum in python",
        "write a python function to reverse a string",
        "explain how to solve 2x + 5 = 17",
        "If f(x) = 2x + 1, explain what f(3) is",
        "Explain why x = 4 solves 3x - 2 = 10",
        "let x = 5, explain how to find 2x + 3",
        "what is the derivative of x^3 sin x",
    ],
)
def test_code_question_kind_skips_lookalikes(text: str) -> None:
    assert code_question_kind(text) is None


@pytest.mark.parametrize(
    "text, subject",
    [
        ("solve 2x + 5 = 17", "math"),
        ("let x = 5, solve 2y + x = 15", "math"),
        ("a ball is dropped from 20 m. how long until it hits the ground?", "physics"),
        (JAVA_LOOP, None),
        ("Walk me through this: const nums = [1, 2]; console.log(nums.map(n => n * 2));", None),
        ("```python\nprint(2 ** 10)\n```\nwhat does this print?", None),
    ],
)
def test_pasted_code_is_not_a_subject_problem(text: str, subject: str | None) -> None:
    assert detect_subject(text) == subject
    assert has_code_syntax(text) is (subject is None)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("what is recursion", True),
        ("write a python function to reverse a string", True),
        ("how do I remove duplicates from a list in python?", True),
        ("compare python and javascript", True),
        (INDEX_ERROR, True),
        ("what is a capybara", False),
        ("tell me about Java island", False),
        ("what is a ball python", False),
        ("tell me about the Library of Alexandria", False),
        ("who is Haile Gebrselassie", False),
    ],
)
def test_is_programming_turn(text: str, expected: bool) -> None:
    assert is_programming_turn(text) is expected


@pytest.mark.parametrize("text", [TRACE_LOOP, ONE_LINE_LOOP])
def test_code_explanation_gets_the_line_by_line_contract(text: str) -> None:
    parts = _hints(text)
    assert CODE_EXPLAIN_HINT in parts
    assert TEACHING_HINT not in parts and WALKTHROUGH_HINT not in parts


def test_pasted_code_never_gets_the_math_pack() -> None:
    # `i <= 3` and `sum += i` once read as algebra and pulled in the `$...$` rules.
    parts = _hints(JAVA_LOOP)
    assert CODE_EXPLAIN_HINT in parts
    assert MATH_INTENT_HINT not in parts


def test_debug_question_gets_the_fix_contract() -> None:
    parts = _hints(INDEX_ERROR)
    assert CODE_DEBUG_HINT in parts
    assert CODE_EXPLAIN_HINT not in parts


def test_pasted_code_beats_walk_me_through() -> None:
    parts = _hints("walk me through what this code does: for i in range(3): print(i * 2)")
    assert CODE_EXPLAIN_HINT in parts
    assert WALKTHROUGH_HINT not in parts


def test_code_contract_is_not_crushed_to_plain_text() -> None:
    parts = _hints(TRACE_LOOP)
    assert CODE_EXPLAIN_HINT in parts
    assert SHORT_RESPONSE_FORMAT_HINT not in parts


def test_a_length_cap_wins_over_the_code_contract() -> None:
    parts = _hints("explain this code in one sentence: print(sum([1, 2, 3]))")
    assert CODE_EXPLAIN_HINT not in parts


def test_code_contract_says_no_dollar_math_and_code_ink() -> None:
    for hint in (CODE_EXPLAIN_HINT, CODE_DEBUG_HINT):
        assert "never write `$...$`" in hint
        assert "`inline code`" in hint
    assert "**Line 1:** `total = 0`" in CODE_EXPLAIN_HINT
    assert "```steps" in CODE_EXPLAIN_HINT
    assert "**Output:**" in CODE_EXPLAIN_HINT
    assert "### Why it fails" in CODE_DEBUG_HINT
    assert "### The fix" in CODE_DEBUG_HINT


def test_general_rules_keep_code_values_out_of_math() -> None:
    assert "never `$...$` math" in FORMAT_CONTRACT
    assert "names in the same ink as the prose" not in FORMAT_CONTRACT
    assert "never bold or backtick ordinary words" in FORMAT_CONTRACT
    assert "Code is not math" in MATH_FENCE_SAFETY_HINT


def _user() -> User:
    user = MagicMock()
    user.id = uuid4()
    user.name = "Bini"
    user.email = "bini@example.com"
    user.location = None
    user.response_tone = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = None
    return cast(User, user)


@pytest.mark.asyncio
async def test_code_ink_reminder_sits_next_to_the_question() -> None:
    current = SimpleNamespace(id=uuid4(), role="user", content=TRACE_LOOP)
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch("app.modules.memory.retrieval.get_memory_block", AsyncMock(return_value="")),
        patch("app.modules.todos.build_todos_system_section", AsyncMock(return_value="")),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[current])),
    ):
        messages = await build_prompt_messages(
            _user(),
            uuid4(),
            Settings(attachment_rag_enabled=False, chat_history_rag_enabled=False),
            query_text=TRACE_LOOP,
            rich_context=False,
            current_user_message_id=current.id,
        )
    assert messages[-1]["role"] == "user"
    assert messages[-2] == {"role": "system", "content": CODE_INK_REMINDER}
    assert CODE_EXPLAIN_HINT in system_prompt(messages)


# "Run this python code: print(1+1)" got a bare "2", as if Recall had run it.
@pytest.mark.parametrize(
    "text",
    [
        "run this python code: print(1+1)",
        "can you execute this: console.log(2 + 3)",
        'compile and run: int main() { printf("hi"); }',
        "run this code\n```python\nnums = [1, 2]\nprint(len(nums))\n```",
    ],
)
def test_a_request_to_run_code_says_recall_cannot(text: str) -> None:
    from app.modules.chat.prompt_constants.coding import CODE_RUN_HINT

    assert code_question_kind(text) == "run"
    hints = _style_format_hints(query_text=text, is_day_plan=False, minimal_personal_context=False)
    assert CODE_RUN_HINT in hints
    assert "You cannot run or execute code" in CODE_RUN_HINT


@pytest.mark.parametrize(
    "text, kind",
    [
        ("why does this not run? print(x", "debug"),
        ("what does this print? print(3 * 3)", "explain"),
        ("run the numbers again: 2 + 2", None),
        ("I run every morning, then print(1) my notes", None),
    ],
)
def test_run_is_read_only_for_a_request_to_run(text: str, kind: str | None) -> None:
    assert code_question_kind(text) == kind
