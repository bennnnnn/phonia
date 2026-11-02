"""Verified fraction procedure branch."""

from __future__ import annotations

import re
from dataclasses import replace

from app.modules.math.schemas import FractionWorkSpec, MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school.teaching import _attach_picture
from app.services.workout import math_line

# ``2 1/2 + 1 3/4`` as the extractor writes it back.
_WRITTEN_BINARY = re.compile(r"(?P<a>(?:\d+ )?\d+/\d+) \S+(?: by)? (?P<b>(?:\d+ )?\d+/\d+)")


def _block_fraction(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math.solve.fractions import build_fraction_work

    fraction_work = build_fraction_work(intent)
    if fraction_work is not None:
        from app.modules.math.solve.teaching_elementary import fraction_bar_spec

        lines.append("Verified fraction procedure:")
        lines.extend(step.explanation for step in fraction_work.steps)
        mixed = _mixed_number_block(intent, fraction_work, lines)
        if mixed is not None:
            return mixed
        block = finish_with_answer(lines, fraction_work.answer)
        block = replace(block, canonical_fences=[fraction_work.model_dump()])
        bars = fraction_bar_spec(
            fraction_work.operation, fraction_work.operands, fraction_work.answer
        )
        if bars is None:
            return block
        return _attach_picture(block, bars, intent, direct=False)
    return None


def _mixed_number_block(
    intent: MathIntent, work: FractionWorkSpec, lines: list[str]
) -> VerifiedMathBlock | None:
    """Mixed numbers: one line from them to the working, then an answer read both ways.

    ``2 1/2 + 1 3/4`` -> ``2\\frac{1}{2} + 1\\frac{3}{4} = \\frac{5}{2} + \\frac{7}{4} = ...``,
    answer ``\\frac{17}{4} = 4\\frac{1}{4}``.
    """
    from app.modules.math.solve.fractions import fraction_working, mixed_number_tex

    written = _WRITTEN_BINARY.fullmatch(intent.expr or "")
    if written is None or " " not in written["a"] + written["b"]:
        return None
    working = fraction_working(work, (written["a"], written["b"]))
    if working is None:
        return None
    answer = work.answer
    numerator, denominator = work.exact_numerator, work.exact_denominator
    if numerator is not None and denominator is not None and numerator > denominator > 1:
        answer = f"{work.answer} = {mixed_number_tex(numerator, denominator)}"
    lines.append(f"Working: ${working}$")
    block = finish_with_answer(lines, answer)
    return replace(block, worked_reply=f"{math_line(working)}\n\n```answer\n{answer}\n```\n")
