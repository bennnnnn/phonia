"""Math-owned answer and diagram transport.

These builders used to live in the subject-neutral solve module. They record
math canonical fences and teaching traces; physics and chemistry do not use them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.solving import VerifiedMathBlock

if TYPE_CHECKING:
    from app.modules.math.solve.key_steps import KeyStep


def _answer_canonical(content: str) -> dict[str, str]:
    return {"type": "answer", "content": content}


def finish_with_answer(
    lines: list[str],
    answer: str,
    *,
    preface: str | None = None,
    allow_direct: bool = True,
    key_steps: tuple[KeyStep, ...] | list[KeyStep] = (),
    given_latex: str | None = None,
    check_latex: str | None = None,
    alternate_method_note: str | None = None,
) -> VerifiedMathBlock:
    """Record the verified answer for post-stream attach; do not put a fence in the hint."""
    if preface:
        lines.append(preface)
    lines.append(f"Verified result: {answer}")
    return VerifiedMathBlock(
        text="\n".join(lines),
        subject="math",
        canonical_fence=_answer_canonical(answer),
        canonical_answer=answer,
        allow_direct=allow_direct,
        key_steps=tuple(key_steps),
        given_latex=given_latex,
        check_latex=check_latex,
        alternate_method_note=alternate_method_note,
    )


def _diagram_block(
    lines: list[str],
    spec: Any,
    answer: str | None = None,
    *,
    display_answer: str | None = None,
) -> VerifiedMathBlock:
    """Diagram JSON on canonical_fence; optional numeric answer for post-stream attach."""
    if answer:
        lines.append(f"Verified result: {answer}")
    dump = spec.model_dump() if hasattr(spec, "model_dump") else spec
    return VerifiedMathBlock(
        text="\n".join(lines),
        subject="math",
        canonical_fence=dump,
        canonical_answer=answer,
        display_answer=display_answer,
    )
