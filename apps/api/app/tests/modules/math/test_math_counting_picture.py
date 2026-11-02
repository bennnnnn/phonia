"""Small whole-number facts are drawn as objects to count when the user asks how; big ones
keep the written method, and a plain sum gets its answer (2026-10-29: "what's 2+2" from an
adult got "2 fish and 2 more make 4 fish")."""

import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.math.schemas.teaching import CountingSpec
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation


async def _reply(query: str) -> str:
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    return reply


def _picture(reply: str) -> dict[str, object] | None:
    if not reply.startswith("```arithmetic\n"):
        return None
    body = reply.split("```arithmetic\n", 1)[1].split("\n```", 1)[0]
    data = json.loads(body)
    return data if data.get("type") == "counting" else None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "operation", "first", "second", "result", "sentence"),
    [
        ("explain 3-3", "subtract", 3, 3, 0, "Take away 3. None are left."),
        ("show the steps for 4-3", "subtract", 4, 3, 1, "1 ball is left."),
        ("explain 3+4", "add", 3, 4, 7, "3 balls and 4 more make 7 balls."),
        ("10+10 show steps", "add", 10, 10, 20, "make 20"),
        ("explain 3*4", "multiply", 3, 4, 12, "3 rows of 4"),
        ("explain 12 ÷ 3", "divide", 12, 3, 4, "shared into 3 equal groups is 4 in each group."),
        ("explain 9-4", "subtract", 9, 4, 5, "5 strawberries are left."),
        # The real minus and division signs the app prints.
        ("explain 3 \u2212 2", "subtract", 3, 2, 1, "1 apple is left."),
        ("explain 12 \u00f7 3", "divide", 12, 3, 4, "4 in each group."),
    ],
)
async def test_a_small_fact_is_drawn_as_objects_with_one_sentence(
    query: str, operation: str, first: int, second: int, result: int, sentence: str
) -> None:
    reply = await _reply(query)
    picture = _picture(reply)
    assert picture is not None
    assert (picture["operation"], picture["first"], picture["second"], picture["result"]) == (
        operation,
        first,
        second,
        result,
    )
    assert sentence in reply
    assert "```answer" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "11+2",
        "123+45",
        "7*8",
        "just the answer 3-3",
        # Asked plainly: the answer, no objects to count.
        "what's 2+2",
        "3+4",
        "3-3",
        "What if it were 3 \u2212 2?",
    ],
)
async def test_big_numbers_and_answer_only_get_no_picture(query: str) -> None:
    assert _picture(await _reply(query)) is None


def test_counting_spec_rejects_a_picture_that_shows_the_wrong_fact() -> None:
    with pytest.raises(ValidationError):
        CountingSpec(
            operation="subtract",
            first=3,
            second=4,
            result=1,
            object="🍎",
            answer="1",
            speech="x",
        )
    with pytest.raises(ValidationError):
        CountingSpec(
            operation="add", first=3, second=4, result=8, object="🍎", answer="8", speech="x"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["explain 3-3", "3*4 show steps", "explain 9-4"])
async def test_the_fence_rewriter_keeps_the_verified_picture_only(query: str) -> None:
    from dataclasses import replace

    from app.modules.math.fence import validate_math_fences
    from app.modules.math.response_intent import classify_math_response_intent

    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    scoped = replace(verified, response_intent=classify_math_response_intent(query))
    reply = maybe_direct_math_reply(verified, query) or ""
    shown = validate_math_fences(reply, verified=scoped)
    assert '"type":"counting"' in shown
    assert shown.count("```answer") == 1
    tampered = reply.replace('"result":', '"result":1', 1)
    assert '"type":"counting"' not in validate_math_fences(tampered, verified=scoped)


@pytest.mark.parametrize(
    ("text", "is_math"),
    [
        ("What if it were 3 \u2212 2?", True),
        ("what if it were bigger?", False),
        ("What if it rains tomorrow at 3?", False),
    ],
)
def test_a_what_if_sum_is_maths_and_a_what_if_question_is_not(text: str, is_math: bool) -> None:
    from app.modules.math.tools.prompt import needs_symbolic_math

    assert needs_symbolic_math(text) is is_math


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Show 8 + 7 using carrying",
        "9 - 4 using borrowing",
        "12 ÷ 3 using long division",
        "show 8+7 with column addition",
    ],
)
async def test_a_named_written_method_keeps_its_column_trace(query: str) -> None:
    reply = await _reply(query)
    assert _picture(reply) is None
    assert '"type":"arithmetic"' in reply


@pytest.mark.asyncio
async def test_a_picture_copied_into_a_plain_sum_is_dropped() -> None:
    from dataclasses import replace

    from app.modules.math.fence import validate_math_fences
    from app.modules.math.response_intent import classify_math_response_intent

    _, explained = await build_math_augmentation("explain 3-3", Settings(math_tools_enabled=True))
    _, plain = await build_math_augmentation("3-3", Settings(math_tools_enabled=True))
    assert explained is not None and plain is not None
    shown = maybe_direct_math_reply(explained, "explain 3-3") or ""
    assert '"type":"counting"' in shown
    # The model repeats the earlier card under a plain "3-3": it does not survive.
    scoped = replace(plain, response_intent=classify_math_response_intent("3-3"))
    assert '"type":"counting"' not in validate_math_fences(shown, verified=scoped)
