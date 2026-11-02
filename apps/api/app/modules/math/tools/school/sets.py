"""Set extractor and verified block."""

from __future__ import annotations

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.number_text import DECIMAL_LITERAL, finite_match_value
from app.services.text_match import word_index


def _parse_brace_set(text: str, start: int) -> tuple[list[float], int] | None:
    if start >= len(text) or text[start] != "{":
        return None
    close = text.find("}", start + 1)
    if close == -1:
        return None
    inner = text[start + 1 : close]
    if "{" in inner:
        return None
    values: list[float] = []
    last = 0
    for match in DECIMAL_LITERAL.finditer(inner):
        gap = inner[last : match.start()].strip()
        if gap not in {"", ","}:
            return None
        parsed = finite_match_value(match)
        if parsed is None:
            return None
        values.append(parsed)
        last = match.end()
    if not values or inner[last:].strip() not in {"", ","}:
        return None
    return values, close + 1


def _brace_sets(text: str) -> list[list[float]] | None:
    found: list[list[float]] = []
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            parsed = _parse_brace_set(text, i)
            if parsed is None:
                return None
            values, nxt = parsed
            found.append(values)
            spans.append((i, nxt))
            i = nxt
        else:
            i += 1
    if len(found) != 2:
        return None
    for match in DECIMAL_LITERAL.finditer(text):
        if not any(start < match.start() and match.end() < end for start, end in spans):
            return None
    return found


def _extract_set_intent(cleaned: str, lower: str) -> MathIntent | None:
    if word_index(lower, "union") != -1:
        op = "set_union"
    elif word_index(lower, "intersection") != -1:
        op = "set_intersection"
    elif word_index(lower, "difference") != -1:
        op = "set_difference"
    else:
        return None
    groups = _brace_sets(cleaned)
    if groups is None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op=op,
        vec_a=groups[0],
        vec_b=groups[1],
        operation="solve",
    )


def _block_sets(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.vec_a is None or intent.vec_b is None:
        return None
    if intent.school_op == "set_union":
        answer = math_school.set_union(intent.vec_a, intent.vec_b)
    elif intent.school_op == "set_intersection":
        answer = math_school.set_intersection(intent.vec_a, intent.vec_b)
    else:
        answer = math_school.set_difference(intent.vec_a, intent.vec_b)
    lines.append(f"{intent.school_op}: {answer}")
    return finish_with_answer(lines, answer)
