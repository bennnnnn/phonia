"""Check my work: the student's lines graded by SymPy, the slip named."""

from __future__ import annotations

import pytest
from sympy import Symbol

from app.core.config import Settings
from app.modules.math import tools as mt
from app.modules.math.solve.work_check import check_work
from app.modules.math.solve.work_lines import parse_line
from app.modules.math.solve.work_slips import diagnose
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.work_request import parse_work_request


def _reply(text: str, *, image: bool = False) -> str | None:
    intent = mt.extract_math_intent(text)
    assert intent is not None and intent.kind == "work_check"
    block = mt._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    return maybe_direct_math_reply(block, text, has_image_attachment=image)


# --- reading the request -------------------------------------------------------


@pytest.mark.parametrize(
    "text, lines",
    [
        ("Check my work:\n2x + 3 = 11\n2x = 14\nx = 7", ("2x + 3 = 11", "2x = 14", "x = 7")),
        ("is this right? 3x - 5 = 10, 3x = 5, x = 5/3", ("3x - 5 = 10", "3x = 5", "x = 5/3")),
        ("I solved 2x+3=11 and got x=7, is that right?", ("2x+3=11", "x=7")),
        ("is this right? 2x+3=11 then 2x=8 then x=4", ("2x+3=11", "2x=8", "x=4")),
        (
            "check my work\n1. 2x + 3 = 11\n2. 2x = 8 (subtract 3 from both sides)\n3. x = 4",
            ("2x + 3 = 11", "2x = 8", "x = 4"),
        ),
        ("check my work: x^2 = 16 so x = \u00b14", ("x^2 = 16", "x = 4 or x = -4")),
        ("check my work: x^2 = 16, x = 4, -4", ("x^2 = 16", "x = 4 or x = -4")),
        ("check my work: x^2 = 9, x = 3 or x = -3", ("x^2 = 9", "x = 3 or x = -3")),
        ("check my work: \u22122x \u2265 6 \u2192 x \u2264 \u22123", ("-2x >= 6", "x <= -3")),
        ("where did i go wrong\nsolve for x: 4(x-2)=12\n4x-8=12", ("4(x-2)=12", "4x-8=12")),
        # The answer before the equation.
        ("I got x = 4 for 3x - 2 = 10, is that right?", ("3x - 2 = 10", "x = 4")),
        ("I found x = -2 for 5x + 10 = 0. Am I right?", ("5x + 10 = 0", "x = -2")),
        ("my answer is x = 3 for 2x + 1 = 7, is this correct?", ("2x + 1 = 7", "x = 3")),
    ],
)
def test_work_request_reads_the_students_lines(text: str, lines: tuple[str, ...]) -> None:
    request = parse_work_request(text)
    assert request is not None
    assert request.lines == lines
    assert request.variable == "x"
    assert request.cued


@pytest.mark.parametrize(
    "text",
    [
        "Don't finish it for me. 5x+2=17\n5x=15",
        "check my work but don\u2019t give me the answer: 2x+3=11, 2x=14",
        "just a hint please\n2x + 3 = 11\n2x = 14",
    ],
)
def test_work_request_hint_cues(text: str) -> None:
    request = parse_work_request(text)
    assert request is not None and request.hint_only


def test_work_request_bare_worked_column_needs_no_cue() -> None:
    request = parse_work_request("2x+3=11\n2x=8\nx=4")
    assert request is not None
    assert request.lines == ("2x+3=11", "2x=8", "x=4")
    assert not request.cued


@pytest.mark.parametrize(
    "text",
    [
        # Prose, and one-line problems, stay on their usual paths.
        "explain why y=mx+b",
        "solve 2x+3=11",
        "check my work: 2x+3=11",
        "the answer key says x=5 but i got 6",
        # Two unknowns is a system, not a chain.
        "x+y=3\nx-y=1",
        "check my work: y = mx + b, y = 3",
        # Without a cue the column must run from a problem to an answer.
        "2x+3=11\n3x-1=5",
        "x=4\n2x+3=11",
        # No unknown to solve for.
        "is this right? 2+2=4, 3+3=6",
        # A relation tangled in prose is not graded on a guess, and a note
        # holding another relation is not dropped as a comment.
        "check my work: I think 2x + 3 = 11 means 2x = 8 right",
        "check my work: 2x + 3 = 11, 2x = 8 hmm x = 5",
        # Inequalities joined by "and" are one answer; not split into lines.
        "check my work: x^2 < 4, -2 < x and x < 2",
        "check my work\n" + "2x = 8\n" * 700,
    ],
)
def test_work_request_declines(text: str) -> None:
    assert parse_work_request(text) is None


def test_prose_equation_mentions_keep_their_extraction() -> None:
    intent = mt.extract_math_intent("solve 2x+3=11")
    assert intent is not None and intent.kind == "equation"


def test_gate_opens_for_student_work_the_old_gate_missed() -> None:
    text = "where did i go wrong\n4(x-2)=12\n4x-2=12\n4x=14\nx=3.5"
    assert mt.needs_symbolic_math(text)


# --- grading -------------------------------------------------------------------


@pytest.mark.parametrize(
    "lines, kind, fixed",
    [
        (["2x + 3 = 11", "2x = 14", "x = 7"], "moved_without_sign_change", "2 x = 8"),
        (["3x - 5 = 10", "3x = 5"], "moved_without_sign_change", "3 x = 15"),
        (["5x = 3x + 8", "8x = 8"], "moved_without_sign_change", "2 x = 8"),
        (["2x + 3 = 11", "2x = 11"], "moved_one_side", "2 x = 8"),
        (["2x + 3 = 11", "2x = 7"], "move_arithmetic", "2 x = 8"),
        (["2x = 8", "x = 6"], "subtracted_coefficient", "x = 4"),
        (["2x = 8", "x = 16"], "scaled_the_wrong_way", "x = 4"),
        (["x/3 = 4", "x = 4/3"], "scaled_the_wrong_way", "x = 12"),
        (["2x = 8", "x = 8"], "scaled_one_side", "x = 4"),
        (["2x = 8", "x = 5"], "scaled_arithmetic", "x = 4"),
        (["-2x > 6", "x > -3"], "no_flip", "x < -3"),
        (["-2x > 6", "x > 3"], "scaled_sign", "x < -3"),
        (["2x > 6", "x < 3"], "wrong_flip", "x > 3"),
        (["3 < x", "x < 3"], "swap_without_flip", "x > 3"),
        (["4(x-2) = 12", "4x - 2 = 12"], "partial_distribution", "4 x - 8 = 12"),
        (["-2(x - 3) = 4", "-2x - 6 = 4"], "distribution_sign", "6 - 2 x = 4"),
        (["3(x + 1) = 9", "3x + 4 = 9"], "distribution", "3 x + 3 = 9"),
        (["2x + 4 = 10", "x + 4 = 5"], "divided_some_terms", "x + 2 = 5"),
        (["3x + 2x = 10", "6x = 10"], "simplified_wrong", "5 x = 10"),
        (
            ["x^2 - 5x + 6 = 0", "(x-2)(x-3) = 0", "x = -2 or x = -3"],
            "factor_root_sign",
            r"x = 2 \text{ or } x = 3",
        ),
        (["x^2 = 9", "x = 3"], "lost_negative_root", None),
        (["x^2 = 4x", "x = 4"], "lost_solution", None),
        (["x = 5", "x^2 = 25", "x = 5 or x = -5"], "extra_solution", None),
        (["2x + 3 = 11", "x = 7"], "answer_does_not_check", None),
    ],
)
def test_work_check_names_the_slip(lines: list[str], kind: str, fixed: str | None) -> None:
    check = check_work(lines, "x")
    assert check is not None
    assert check.mistake is not None
    assert check.mistake.kind == kind
    assert check.mistake.fixed_tex == fixed
    assert check.verdicts[check.mistake.line - 1] == "wrong"


@pytest.mark.parametrize(
    "before, after",
    [
        ("2x + 3 = 11", "2x = 14"),
        ("-2x > 6", "x > -3"),
        ("-2x > 6", "x > 3"),
        ("4(x-2) = 12", "4x - 2 = 12"),
        ("2x + 4 = 10", "x + 4 = 5"),
        ("x/3 = 4", "x = 4/3"),
        ("(x-2)(x-3) = 0", "x = -2 or x = -3"),
    ],
)
def test_every_proposed_fix_has_the_last_good_lines_solutions(before: str, after: str) -> None:
    x = Symbol("x")
    prev, cur = parse_line(before, x), parse_line(after, x)
    assert prev is not None and cur is not None
    mistake, fixed = diagnose(prev, cur, x, 2)
    assert fixed is not None and mistake.fixed_tex == fixed.tex
    assert fixed.solutions == prev.solutions


def test_lines_after_the_mistake_are_marked_carried_or_off() -> None:
    check = check_work(["2x + 3 = 11", "2x = 14", "x = 7", "x = 9"], "x")
    assert check is not None
    assert check.verdicts == ("given", "wrong", "carried", "off")


def test_answer_before_the_equation_is_checked() -> None:
    reply = _reply("I got x = 4 for 3x - 2 = 10, is that right?")
    assert reply is not None and "x = 4" in reply.replace("$", "")


def test_correct_finished_work_is_confirmed_with_a_substitution_check() -> None:
    check = check_work(["2x + 3 = 11", "2x = 8", "x = 4"], "x")
    assert check is not None
    assert check.mistake is None and check.finished
    assert check.verdicts == ("given", "ok", "ok")
    assert check.answer == "x = 4"
    assert check.check == "2 (4) + 3 = 11"


def test_correct_unfinished_work_gets_the_remaining_steps() -> None:
    check = check_work(["5x + 2 = 17", "5x = 15"], "x")
    assert check is not None
    assert check.mistake is None and not check.finished
    assert check.steps and check.steps[0].label == "Divide both sides by 5"


def test_decimal_answer_matches_the_exact_solution() -> None:
    check = check_work(["4x = 14", "x = 3.5"], "x")
    assert check is not None and check.mistake is None and check.finished


def test_quadratic_answer_with_both_roots_is_correct() -> None:
    check = check_work(["x^2 - 5x + 6 = 0", "(x-2)(x-3) = 0", "x = 2 or x = 3"], "x")
    assert check is not None and check.mistake is None and check.finished
    assert check.answer == r"x = 2 \text{ or } x = 3"


@pytest.mark.parametrize(
    "lines",
    [
        ["x^3 = 8", "x = 2"],  # cubic: out of scope
        ["1/x = 2", "x = 1/2"],  # rational
        ["sqrt(x) = 3", "x = 9"],  # radical
        ["2x = 2x", "0 = 0"],  # identity: nothing to grade against
        ["x = x + 1", "0 = 1"],  # no solution
    ],
)
def test_work_check_declines_out_of_scope(lines: list[str]) -> None:
    assert check_work(lines, "x") is None


# --- replies -------------------------------------------------------------------


def test_reply_marks_lines_explains_and_fixes() -> None:
    reply = _reply("Check my work:\n2x + 3 = 11\n2x = 14\nx = 7")
    assert reply is not None
    # The student's lines, graded, are the Given; the slip, then the fix as numbered moves.
    assert reply.startswith("**Given**  \n$2x + 3 = 11$ — the problem  \n")
    assert "$2x = 14$ — \u2717  \n" in reply
    assert "$x = 7$ — follows, but carries the line 2 slip" in reply
    assert "Line 2: A term changes sign" in reply
    assert "$11 - 3 = 8$" in reply
    assert "Fixed from line 2:" in reply
    assert (
        "**1. Subtract $3$ from both sides** — Subtraction property of equality  \n$2 x = 8$"
        in reply
    )
    assert "**Steps**" not in reply
    assert reply.rstrip().endswith("```answer\nx = 4\n```")


def test_hint_reply_keeps_the_fix_and_answer_back() -> None:
    reply = _reply("Check my work, don't give me the answer:\n2x + 3 = 11\n2x = 14\nx = 7")
    assert reply is not None
    assert "$2x = 14$ — \u2717" in reply
    assert "Hint: When $+3$ crosses to the other side" in reply
    for leaked in ("```answer", "x = 4", "2 x = 8", "11 - 3"):
        assert leaked not in reply


def test_hint_reply_for_unfinished_correct_work_names_only_the_next_move() -> None:
    reply = _reply("Don't finish it for me. 5x+2=17\n5x=15")
    assert reply is not None
    assert "Next move: divide both sides by 5." in reply
    assert "```answer" not in reply and "x = 3" not in reply


def test_hint_mode_block_carries_no_answer_for_the_model() -> None:
    intent = mt.extract_math_intent("just a hint\n2x + 3 = 11\n2x = 14")
    assert intent is not None
    block = mt._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is None and block.canonical_fence is None
    assert "x = 4" not in block.text and "2 x = 8" not in block.text
    assert "hint only" in block.text


def test_correct_work_reply_confirms_and_shows_the_answer() -> None:
    reply = _reply("2x+3=11\n2x=8\nx=4")
    assert reply is not None
    assert reply.count("\u2713") == 2
    assert "Every step checks out." in reply
    # They asked for a check: it is a numbered move, not a "— check" note.
    assert "**1. Check** — Put the answer back into the equation  \n$2 (4) + 3 = 11$" in reply
    assert "**Steps**" not in reply
    assert "```answer\nx = 4\n```" in reply


def test_photo_attached_keeps_the_model_path() -> None:
    assert _reply("Check my work:\n2x + 3 = 11\n2x = 14", image=True) is None


def test_out_of_scope_work_builds_no_verified_block() -> None:
    intent = mt.extract_math_intent("check my work\nx^3 = 8\nx = 2")
    assert intent is not None and intent.kind == "work_check"
    assert mt._build_verified_block(intent, Settings(math_tools_enabled=True)) is None
