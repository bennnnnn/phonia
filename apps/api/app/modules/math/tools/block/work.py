"""Check-my-work block: the student's own lines, graded, and a reply to send.

The reply is rendered here rather than by the model, the same way equation
lessons are, so the verdict a student sees is exactly what SymPy checked. In
hint mode ("don't finish it for me") the reply names the line and the rule it
breaks as a question, and no corrected line or answer leaves this module.
"""

from __future__ import annotations

from app.core.config import Settings
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.work_check import WorkCheck, check_work
from app.modules.math.tools.block.canonical import _answer_canonical
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout


def _verified_block_work_check(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.work_lines:
        return None
    check = check_work(intent.work_lines, intent.variable)
    if check is None:
        return None
    hint_only = intent.work_hint_only
    lines.extend(_summary_lines(check, hint_only=hint_only))
    # A hint never carries the answer, unless the student already reached it.
    answer = check.answer if not hint_only or _correct_and_done(check) else None
    if answer:
        lines.append(f"Verified result: {answer}")
    return VerifiedMathBlock(
        text="\n".join(lines),
        canonical_fence=_answer_canonical(answer) if answer else None,
        canonical_answer=answer,
        direct_reply=format_work_check_reply(check, hint_only=hint_only),
    )


def _correct_and_done(check: WorkCheck) -> bool:
    return check.mistake is None and check.finished


def _verdict(check: WorkCheck, index: int) -> str:
    verdict = check.verdicts[index]
    if verdict == "given":
        return "the problem"
    if verdict == "ok":
        return "\u2713"
    if verdict == "carried" and check.mistake is not None:
        return f"follows, but carries the line {check.mistake.line} slip"
    return "\u2717"


def _graded_lines(check: WorkCheck) -> tuple[str, ...]:
    return tuple(math_line(tex, _verdict(check, index)) for index, tex in enumerate(check.lines))


def _numbered(check: WorkCheck) -> str:
    """The rest of the solve as numbered moves, the lesson layout."""
    from app.modules.math.tools.lesson import numbered_steps

    _formulas, numbered = numbered_steps(check.steps, given_latex="", answer=check.answer)
    return numbered


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _reply(given: tuple[str, ...], parts: list[str], answer: str | None) -> str:
    """Given, then sentences and numbered moves (never a **Steps** list), then Answer."""
    body = "\n\n".join(part for part in parts if part.strip())
    if answer is None:
        # A hint keeps the answer back, so the layout stops before Answer.
        return (
            render_workout(Workout(given=given), before_answer=body).removesuffix("\n\n**Answer**")
            + "\n"
        )
    return render_workout(Workout(given=given), answer, before_answer=body)


def format_work_check_reply(check: WorkCheck, *, hint_only: bool = False) -> str:
    """The student's lines, graded, under Given; the verdict, then the fix as numbered moves."""
    given = _graded_lines(check)
    mistake = check.mistake
    if mistake is None:
        if check.finished:
            parts = ["Every step checks out."]
            if check.check and not hint_only:
                rule = "Put the answer back into the equation"
                parts.append(f"**1. Check** — {rule}  \n${check.check}$")
            return _reply(given, parts, check.answer)
        if hint_only:
            nudge = "Everything so far is right."
            if check.steps:
                nudge += f" Next move: {_lower_first(check.steps[0].label)}."
            return _reply(given, [nudge], None)
        finish = ["Everything so far is right. To finish:", _numbered(check)]
        return _reply(given, finish, check.answer)
    if hint_only:
        return _reply(given, [f"Hint: {mistake.hint}"], None)
    parts = []
    if check.right_answer:
        parts.append(
            f"Your final answer is right, but line {mistake.line} does not follow "
            f"from line {mistake.line - 1}."
        )
    parts.append(f"Line {mistake.line}: {mistake.explanation}")
    if check.steps:
        parts.append(
            f"Fixed from line {mistake.line}:"
            if mistake.fixed_tex is not None
            else f"Starting again from line {mistake.line - 1}:"
        )
        parts.append(_numbered(check))
    return _reply(given, parts, check.answer)


def _summary_lines(check: WorkCheck, *, hint_only: bool) -> list[str]:
    """The model-facing record, for turns that keep the model (an attachment)."""
    out = ["Student work check (each line compared with line 1 by SymPy):"]
    for index, tex in enumerate(check.lines):
        verdict = check.verdicts[index]
        note = {
            "given": "the problem as the student wrote it",
            "ok": "correct",
            "wrong": "FIRST MISTAKE",
            "carried": "follows from the line before (carries the mistake)",
            "off": "also wrong",
        }[verdict]
        out.append(f"Line {index + 1}: {tex} ({note})")
    mistake = check.mistake
    if mistake is not None:
        detail = mistake.hint if hint_only else mistake.explanation
        out.append(f"Mistake in line {mistake.line} ({mistake.kind}): {detail}")
        if mistake.fixed_tex and not hint_only:
            out.append(f"Corrected line {mistake.line}: {mistake.fixed_tex}")
        if check.right_answer:
            out.append("The final answer is right; only the slip above is wrong.")
    elif not check.finished:
        out.append("Every line is correct so far; the work is not finished.")
    else:
        out.append("Every line is correct and the work is finished: tell the student so.")
    if hint_only and not _correct_and_done(check):
        out.append(
            "The student asked for a hint only: name the wrong line and ask about the rule it "
            "breaks. Do not state a corrected line or the solution."
        )
    return out
