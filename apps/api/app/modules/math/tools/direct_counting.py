"""A picture of objects to count for a small whole-number fact.

``3 - 3`` drawn as three apples with three crossed out says more to a young
learner than a one-column subtraction. Addition and subtraction use numbers up
to 10; multiplication and division use a few rows or groups, up to 30 objects.
Larger numbers keep the written method, which is the right tool there.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Literal

from app.modules.math.schemas import ArithmeticWorkSpec
from app.modules.math.schemas.teaching import CountingSpec
from app.services.solving import VerifiedMathBlock

# (emoji, one, many). The object is picked from the numbers, so the same
# question always shows the same picture.
_OBJECTS = (
    ("🍎", "apple", "apples"),
    ("⭐", "star", "stars"),
    ("⚽", "ball", "balls"),
    ("🍓", "strawberry", "strawberries"),
    ("🐟", "fish", "fish"),
)
_Operation = Literal["add", "subtract", "multiply", "divide"]
_OPERATIONS: dict[str, _Operation] = {
    "addition": "add",
    "subtraction": "subtract",
    "multiplication": "multiply",
    "division": "divide",
}
_MAX_ADD_SUBTRACT = 10
_MAX_OBJECTS = 30


def counting_picture(spec: ArithmeticWorkSpec) -> CountingSpec | None:
    """The counting picture for a two-number whole fact, or None when it is too big."""
    operation = _OPERATIONS.get(spec.operation)
    if operation is None or len(spec.operands) != 2:
        return None
    try:
        first, second = (int(operand) for operand in spec.operands)
        result = int(spec.answer)
    except ValueError:
        return None
    if min(first, second, result) < 0 or not _fits(operation, first, second, result):
        return None
    emoji, one, many = _OBJECTS[(first + second) % len(_OBJECTS)]

    def count(n: int) -> str:
        return f"{n} {one if n == 1 else many}"

    speech = {
        "add": f"{count(first)} and {second} more make {count(result)}.",
        "subtract": f"Start with {count(first)}. Take away {second}. {_left(result, count)}",
        "multiply": f"{first} rows of {count(second)} make {count(result)}.",
        "divide": f"{count(first)} shared into {second} equal groups is {result} in each group.",
    }[operation]
    try:
        return CountingSpec(
            operation=operation,
            first=first,
            second=second,
            result=result,
            object=emoji,
            answer=str(result),
            speech=speech,
        )
    except ValueError:
        return None


def _fits(operation: str, first: int, second: int, result: int) -> bool:
    if operation in {"add", "subtract"}:
        return first <= _MAX_ADD_SUBTRACT and second <= _MAX_ADD_SUBTRACT
    if operation == "multiply":
        return 1 <= first <= 10 and 1 <= second <= 10 and result <= _MAX_OBJECTS
    return 1 <= second <= 10 and first <= _MAX_OBJECTS and first == second * result


def _left(result: int, count: Callable[[int], str]) -> str:
    if result == 0:
        return "None are left."
    return f"{count(result)} {'is' if result == 1 else 'are'} left."


def verified_counting_fence(body: str, verified: VerifiedMathBlock | None) -> str | None:
    """Keep a counting picture only when it is the one the verified working draws, on a
    turn that asked how.

    The fence rewriter otherwise drops an arithmetic fence it did not produce. A plain
    sum gets no picture (2026-10-29), so one copied from an explained turn earlier in
    the chat is dropped too. A model-written or altered picture still does not pass.
    """
    from app.modules.math.tools.direct_arithmetic import arithmetic_work_spec

    if verified is None or verified.response_intent is None:
        return None
    if not verified.response_intent.wants_explanation:
        return None
    try:
        data = json.loads(body.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "counting":
        return None
    spec = arithmetic_work_spec(verified)
    picture = counting_picture(spec) if spec is not None else None
    if picture is None or picture.model_dump() != data:
        return None
    return f"```arithmetic\n{json.dumps(data, separators=(',', ':'), ensure_ascii=False)}\n```"
