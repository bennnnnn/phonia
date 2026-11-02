"""Server-rendered equation lessons from verified ``key_steps``."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.modules.math.response_intent import (
    MathResponseMode,
    classify_math_response_intent,
    strip_math_response_wrappers,
)
from app.modules.math.solve.key_steps import KeyStep
from app.modules.math.solve.step_rules import step_rule
from app.services.solving import VerifiedMathBlock
from app.services.times_sign import with_times
from app.services.workout import (
    GIVEN,
    REQUIRED,
    Workout,
    math_line,
    render_workout,
    split_equality_chain,
    text_line,
)


def wants_math_explanation(text: str) -> bool:
    """True when the user asked for language (steps / teaching), not just the value."""
    return classify_math_response_intent(text).wants_explanation


def wants_answer_only(text: str) -> bool:
    return classify_math_response_intent(text).mode == MathResponseMode.ANSWER_ONLY


_ANSWER_CHECK = re.compile(
    r"\b(?:check|verify|verified|verification|prove|proof|confirm|double[- ]check"
    r"|plug(?:ging)?\s+(?:it|that|the\s+answer|the\s+value)\s+back"
    r"|substitute\s+(?:it|that|the\s+answer)\s+back"
    r"|show\s+(?:me\s+)?(?:that\s+)?it\s+works)\b",
    re.IGNORECASE,
)


# "no check", "without checking", "skip the verification", "don't prove it".
_NO_ANSWER_CHECK = re.compile(
    r"\b(?:no|without|skip(?:ping)?|don'?t|do\s+not|never)\s+(?:the\s+|a\s+|any\s+)?"
    r"(?:check|checking|checks|verify|verifying|verification|proof|prove|proving)\b",
    re.IGNORECASE,
)


def wants_answer_check(text: str) -> bool:
    """True when the user asks to check, verify or prove the answer.

    Only then does the worked solution end with a substitution check. Grading
    the student's own answer ("is my answer right?") is check-my-work instead.
    """
    if classify_math_response_intent(text).mode == MathResponseMode.CHECK:
        return False
    if _NO_ANSWER_CHECK.search(text) is not None:
        return False
    return _ANSWER_CHECK.search(text) is not None


def wants_detailed_math_explanation(text: str) -> bool:
    """True for 'explain' / 'why' — not for 'show steps'."""
    return classify_math_response_intent(text).wants_detailed_explanation


def strip_teaching_signals(text: str) -> str:
    """Drop teaching/answer-only metadata so leftover-English still sees the math."""
    return strip_math_response_wrappers(text)


def lesson_math_text(text: str) -> str:
    """The math left after teaching words: "show steps for 2x+3<7" → "2x+3<7"."""
    stripped = strip_teaching_signals(text).strip().lstrip(":").strip()
    for filler in ("for ", "of ", "me "):
        if stripped.lower().startswith(filler):
            stripped = stripped[len(filler) :].lstrip()
    return stripped


def strip_lesson_prefixes(text: str) -> str:
    """Drop show-steps / just-the-answer wrappers before equation extraction."""
    return strip_math_response_wrappers(text)


def should_render_equation_lesson(verified: VerifiedMathBlock, user_text: str) -> bool:
    if not verified.key_steps or not (verified.canonical_answer or "").strip():
        return False
    if wants_answer_only(user_text):
        return False
    # A closed equation/system/inequality should teach. ``key_steps`` is a short,
    # server-rendered, SymPy-checked trace; hiding it reduced homework to a bare chip.
    # Calculus keeps its compact style unless the learner asks how/why/for steps.
    if verified.given_label == GIVEN:
        return True
    if wants_math_explanation(user_text):
        return True
    # One rule with its working shown (``x^{3 + 1} / (3 + 1)``), short of the
    # answer, teaches as much as two lines.
    answer = (verified.canonical_answer or "").replace(" ", "")
    single = len(verified.key_steps) == 1 and (
        answer.removesuffix("+C") not in verified.key_steps[0].formula.replace(" ", "")
    )
    return len(verified.key_steps) >= 2 or single


def format_equation_lesson_reply(
    verified: VerifiedMathBlock,
    *,
    include_check: bool = False,
    include_reasons: bool = False,
) -> str:
    """Numbered working for a verified equation.

    Given is the problem. Required is ``x = ?``. Each move is its own number: the
    instruction, the equation with that move written on both sides, then the
    simplified equation. A following ``Simplify`` row stays on that same step.
    """
    answer = (verified.display_answer or verified.canonical_answer or "").strip()
    if not verified.key_steps:
        return f"```answer\n{answer}\n```\n"
    workout, numbered = lesson_workout(
        verified, include_check=include_check, include_reasons=include_reasons
    )
    reply = render_workout(workout, answer, before_answer=numbered)
    fence = verified.canonical_fence
    if isinstance(fence, dict) and fence.get("type") == "number_line":
        # An inequality lesson keeps its solution set on the number line.
        reply += f"\n```graph\n{json.dumps(fence, separators=(',', ':'))}\n```\n"
    if verified.alternate_method_note:
        reply += f"\n{verified.alternate_method_note}\n"
    return reply


_DERIVATIVE_GIVEN = re.compile(r"^\\frac\{d\}\{d([A-Za-z])\}\\left\((.*)\\right\)$", re.DOTALL)
_ANSWER_VARIABLES = re.compile(r"(?:^|,\s*|\\text\{ or \}\s*)([A-Za-z])\s*(?:=|<|>|\\le|\\ge|\\ne)")
_RULE_REASON = re.compile(r"^\$[^$]+\$(?:\s+for\s+\$[^$]+\$)?$")
_RULE_NAMES = (
    "product rule",
    "quotient rule",
    "chain rule",
    "power rule",
    "integration by parts",
    "constant rule",
)
_MOVE_LABEL = re.compile(r"^(?:add|subtract|multiply|divide)\b", re.IGNORECASE)


def lesson_workout(
    verified: VerifiedMathBlock,
    *,
    include_check: bool = False,
    include_reasons: bool = False,
) -> tuple[Workout, str]:
    given, find, variable = _given_and_find(verified)
    answer = (verified.display_answer or verified.canonical_answer or "").strip()
    formulas, blocks = _numbered_blocks(
        verified.key_steps,
        given_latex=verified.given_latex or "",
        answer=answer,
        variable=variable,
        include_reasons=include_reasons,
    )
    if include_check and verified.check_latex:
        lines = tuple(line for line in verified.check_latex.split("\n") if line.strip())
        blocks.append(_NumberedStep("Check", lines))
    workout = Workout(given=given, find=find, formula=tuple(formulas))
    return workout, _render_numbered(blocks)


def numbered_steps(
    key_steps: tuple[KeyStep, ...] | list[KeyStep],
    *,
    given_latex: str,
    answer: str,
    variable: str = "x",
) -> tuple[list[str], str]:
    """A verified trace in the lesson layout: (rule formulas, the numbered moves)."""
    formulas, blocks = _numbered_blocks(
        key_steps, given_latex=given_latex, answer=answer, variable=variable, include_reasons=False
    )
    return formulas, _render_numbered(blocks)


def with_requested_check(reply: str, verified: VerifiedMathBlock, user_text: str) -> str:
    """A prebuilt reply gets its check only when the student asked for one."""
    check = (verified.check_latex or "").strip()
    parts = reply.split("\n\n")
    moves = [i for i, part in enumerate(parts) if re.match(r"\*\*\d+\. ", part)]
    if not check or not moves or not wants_answer_check(user_text):
        return reply
    lines = "  \n".join(
        f"${with_times(line.strip())}$" for line in check.split("\n") if line.strip()
    )
    parts.insert(moves[-1] + 1, f"**{len(moves) + 1}. Check**  \n{lines}")
    return "\n\n".join(parts)


def _given_and_find(verified: VerifiedMathBlock) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    given = (verified.given_latex or "").strip()
    if verified.given_label == REQUIRED:
        return (), (math_line(given),) if given else (), "x"
    derivative = _DERIVATIVE_GIVEN.match(given)
    if derivative is not None:
        variable, expression = derivative.group(1), derivative.group(2)
        return (
            (math_line(f"y = {expression}"),),
            (math_line(rf"\frac{{dy}}{{d{variable}}}"),),
            variable,
        )
    answer = f"{verified.display_answer or ''}, {verified.canonical_answer or ''}"
    variables: list[str] = []
    for name in _ANSWER_VARIABLES.findall(answer):
        if name not in variables:
            variables.append(name)
    variable = variables[0] if variables else "x"
    lines = tuple(math_line(part) for part in given.split(r", \quad ") if part.strip())
    # An equation is solved for a value. An inequality keeps the unknown alone.
    solving = "=" in (verified.canonical_answer or verified.display_answer or "")
    if variables and solving:
        find = tuple(math_line(f"{name} = ?") for name in variables)
    else:
        find = (math_line(", ".join(variables)),) if variables else ()
    return lines, find, variable


def _collect_formula(step: KeyStep, formulas: list[str], variable: str) -> None:
    lowered = step.label.lower()
    name = next((rule for rule in _RULE_NAMES if rule in lowered), None)
    if step.reason and _RULE_REASON.match(step.reason):
        # A rule's name heads its formula (``formula_sections``): "Product rule".
        line = text_line(step.reason, name[:1].upper() + name[1:] if name else None)
        same = [index for index, kept in enumerate(formulas) if kept.startswith(step.reason)]
        if not same:
            formulas.append(line)
        elif name and formulas[same[0]] == step.reason:
            # The rule was first met unnamed; name it now.
            formulas[same[0]] = line
    if lowered.startswith("chain rule"):
        line = math_line(r"\frac{d}{dx} f(g(x)) = f'(g(x))\,g'(x)", "Chain rule")
        if line not in formulas:
            formulas.append(line)
    if step.label == "Quadratic formula":
        for line in (
            math_line(r"\Delta = b^{2} - 4ac", "Discriminant"),
            math_line(rf"{variable} = \frac{{-b \pm \sqrt{{\Delta}}}}{{2a}}", "Quadratic formula"),
        ):
            if line not in formulas:
                formulas.append(line)


def _shows_move(step: KeyStep) -> bool:
    """``2x + 3 - 3 = 11 - 3`` writes the move on both sides; ``2x = 8`` is a state."""
    if not _MOVE_LABEL.match(step.label):
        return False
    formula = step.formula
    if r"\cancel" in formula:
        return True
    sides = formula.split(" = ")
    if len(sides) != 2:
        return False
    left, right = sides
    if re.match(r"^(.+?) \\cdot \(.+\)$", left) and re.match(r"^(.+?) \\cdot \(.+\)$", right):
        return True
    for operator in (" + ", " - "):
        cut = left.rfind(operator)
        if cut > 0 and right.endswith(left[cut:]):
            return True
    return False


def _state_key(tex: str) -> str:
    return re.sub(r"\s+", "", tex)


def _single_variable_answer(answer: str) -> bool:
    return re.fullmatch(r"[A-Za-z]\s*=\s*[^=,;\n]+", answer) is not None


@dataclass(frozen=True)
class _NumberedStep:
    label: str
    formulas: tuple[str, ...]
    reason: str | None = None


def _numbered_blocks(
    key_steps: tuple[KeyStep, ...] | list[KeyStep],
    *,
    given_latex: str,
    answer: str,
    variable: str,
    include_reasons: bool,
) -> tuple[list[str], list[_NumberedStep]]:
    """Each operation, then the simplified equation that follows it.

    A ``Simplify`` row is the second line of the move before it, not its own
    number. The last both-sides move keeps the solved value on that same step
    when the trace does not already record it.
    """
    formulas: list[str] = []
    blocks: list[_NumberedStep] = []
    shown = {_state_key(given_latex)} if given_latex.strip() else set()
    steps = [step for step in key_steps if step.formula.strip()]
    index = 0
    while index < len(steps):
        step = steps[index]
        _collect_formula(step, formulas, variable)
        # A "Result" row (a word problem's solved letter) finishes the move before it.
        if step.label in ("Simplify", "Result") and blocks:
            _attach_simplify(blocks, step, shown, include_reasons=include_reasons)
            index += 1
            continue
        lines = _step_formula_lines(step, include_reasons=include_reasons)
        index += 1
        if index < len(steps) and steps[index].label == "Simplify":
            _extend_new(lines, _step_formula_lines(steps[index], include_reasons=include_reasons))
            index += 1
        elif index == len(steps) and _shows_move(step) and _single_variable_answer(answer):
            _extend_new(lines, split_equality_chain(answer))
        if not any(_state_key(line) not in shown for line in lines):
            continue
        shown.update(_state_key(line) for line in lines)
        reason = step.reason if include_reasons else None
        if reason and _RULE_REASON.match(reason):
            reason = None
        blocks.append(_NumberedStep(step.label, tuple(lines), reason))
    return formulas, blocks


def _attach_simplify(
    blocks: list[_NumberedStep],
    step: KeyStep,
    shown: set[str],
    *,
    include_reasons: bool,
) -> None:
    previous = blocks[-1]
    merged = list(previous.formulas)
    extra = _step_formula_lines(step, include_reasons=include_reasons)
    _extend_new(merged, extra)
    blocks[-1] = _NumberedStep(previous.label, tuple(merged), previous.reason)
    shown.update(_state_key(line) for line in extra)


def _extend_new(lines: list[str], more: list[str]) -> None:
    seen = {_state_key(line) for line in lines}
    for part in more:
        text = part.strip()
        if not text or _state_key(text) in seen:
            continue
        lines.append(text)
        seen.add(_state_key(text))


def _step_formula_lines(step: KeyStep, *, include_reasons: bool) -> list[str]:
    tex = step.formula
    # The stored divide strikes the factor. The working shows the fraction
    # written out (``4x/4 = -4/4``). A why-question keeps the strike.
    if not include_reasons and _shows_move(step):
        tex = re.sub(r"\\cancel\{([^{}]*)\}", r"\1", tex)
    return [part for part in split_equality_chain(tex) if part.strip()]


def _render_numbered(blocks: list[_NumberedStep]) -> str:
    """One paragraph per step, so the phone can draw the number as a badge."""
    parts: list[str] = []
    for number, block in enumerate(blocks, start=1):
        heading = f"**{number}. {block.label}**"
        # The rule that allows the move, then any why-question reason after it.
        note = " · ".join(
            part
            for part in (step_rule(block.label, " ".join(block.formulas)), block.reason)
            if part
        )
        if note:
            heading += f" — {note}"
        lines = [heading, *(f"${with_times(formula)}$" for formula in block.formulas)]
        parts.append("  \n".join(lines))
    return "\n\n".join(parts)
