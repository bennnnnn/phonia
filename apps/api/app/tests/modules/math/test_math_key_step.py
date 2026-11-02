"""Verified equation lessons from structured ``key_steps``.

``solve x^2 - 5x + 6 = 0`` used to return a bare chip (or a one-line
factorization). The working is now a server-rendered Given / one-transformation
trace so it cannot drift from the chip. Only an explicit “just the answer” opts
out.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools import (
    _build_verified_block,
    extract_math_intent,
    maybe_direct_math_reply,
    wants_math_explanation,
)
from app.modules.math.tools.lesson import format_equation_lesson_reply
from app.tests.modules.math.card_support import card_with_working


def _block(text: str):
    intent = extract_math_intent(text)
    assert intent is not None, f"no intent for {text!r}"
    return _build_verified_block(intent, Settings(math_tools_enabled=True))


def test_show_steps_phrase_is_an_explanation_request() -> None:
    assert wants_math_explanation("Show steps: 2x + 3 = 11") is True
    assert wants_math_explanation("Hint only: x^2 + 2 = 6") is False


def test_seven_times_eight_is_a_bare_chip() -> None:
    text = "7*8"
    reply = maybe_direct_math_reply(_block(text), text)
    assert reply == card_with_working("7 × 8 = 56", text)
    assert "Given" not in reply


def test_linear_lesson_shows_each_move_on_both_sides() -> None:
    """4x + 4 = 0 keeps the operation, the both-sides line, and the result."""
    reply = maybe_direct_math_reply(_block("4x+4=0"), "4x+4=0")

    assert reply is not None
    before, _, _ = reply.partition("```answer")
    assert "$x = ?$" in before
    assert "**1. Subtract 4 from both sides**" in before
    assert "$4 x + 4 - 4 = 0 - 4$" in before
    assert "$4 x = -4$" in before
    assert "**2. Divide both sides by 4**" in before
    assert r"\frac{4 x}{4}" in before
    assert r"\frac{-4}{4}" in before
    assert "$x = -1$" in before
    assert "**Steps**" not in before
    assert "Simplify" not in before
    assert before.index("Subtract 4") < before.index("4 x = -4")
    assert before.index("4 x = -4") < before.index("Divide both sides by 4")
    assert before.index("Divide both sides by 4") < before.index("$x = -1$")
    assert reply.strip().endswith("```")


def test_show_steps_linear_lesson() -> None:
    text = "Show steps: 2x + 3 = 11"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert "**Given**" in reply
    assert "**1. Subtract 3 from both sides**" in reply
    assert "$2 x + 3 - 3 = 11 - 3$" in reply
    assert "$2 x = 8$" in reply
    assert "**2. Divide both sides by 2**" in reply
    assert reply.index("Subtract") < reply.index("Divide")
    assert "```answer" in reply
    assert "x = 4" in reply
    assert reply.strip().endswith("```")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Show steps: 2x + 3 = 11",
        "Just the answer: x^2 + 2 = 6",
    ],
)
async def test_lesson_prefix_reaches_verified_math_routing(text: str) -> None:
    """Response metadata must not hide an otherwise closed equation from the gate."""
    from app.modules.math.tools import build_math_augmentation

    _note, verified = await build_math_augmentation(
        text,
        Settings(math_tools_enabled=True),
    )

    assert verified is not None
    assert verified.canonical_answer


def test_one_op_linear_still_shows_its_verified_working() -> None:
    text = "x+7=12"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert "**Given**" in reply
    assert "**1. Subtract 7 from both sides**" in reply
    assert "$x + 7 - 7 = 12 - 7$" in reply
    assert "x = 5" in reply


def test_two_op_linear_is_a_lesson() -> None:
    text = "2x + 7 = 19"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert "**1. Subtract 7 from both sides**" in reply
    assert "**2. Divide both sides by 2**" in reply
    assert reply.index("Subtract") < reply.index("Divide")
    assert "```answer" in reply
    assert "x = 6" in reply
    # The last move ends on the solved line, which the chip then states once.
    before_chip, _, _after = reply.partition("```answer")
    assert before_chip.count("x = 6") == 1
    assert r"\frac{2 x}{2} = \frac{12}{2}" in before_chip


def test_pure_power_takes_the_square_root() -> None:
    text = "x^2 + 2 = 6"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert "**Given**" in reply
    lines = reply.splitlines()
    given_line = lines[lines.index("**Given**  ") + 1]
    assert given_line.startswith("$")
    assert "Take the square root of both sides" in reply
    assert r"\sqrt{4}" in reply
    assert r"x = \pm 2" in reply
    before, _, _ = reply.partition("```answer")
    assert before.index(r"x = \pm \sqrt{4}") < before.index(r"x = \pm 2")
    assert r"\sqrt{x" not in reply
    assert "lvert" not in reply
    assert "```answer" in reply
    assert r"\pm 2" in reply
    # A check is added only when the user asks for one.
    assert "Check**" not in reply
    asked = maybe_direct_math_reply(_block(text), f"{text} and check")
    assert asked is not None and "**3. Check**" in asked


def test_rational_equation_clears_the_denominator_and_finishes_at_the_chip() -> None:
    text = "(x+1)/(x-1)=3"
    block = _block(text)
    reply = maybe_direct_math_reply(block, text)

    assert reply is not None
    assert "Multiply both sides by $x - 1$" in reply
    assert r"3 \left(x - 1\right)" in reply
    assert r"x \ne 1" in reply
    assert block.key_steps[-1].formula == block.canonical_answer == "x = 2"


def test_high_degree_denominator_is_not_enumerated() -> None:
    from sympy import Symbol

    from app.modules.math.solve.key_steps import equation_key_steps

    x = Symbol("x")
    steps = equation_key_steps(x / (x**20 + 1), 0, "x")
    assert steps
    joined = " ".join(step.formula for step in steps)
    assert r"\text{denominator} \ne 0" in joined
    assert joined.count(r"\ne") == 1


def test_absolute_value_equation_gets_a_complete_lesson() -> None:
    text = "|x-2|=5"
    block = _block(text)
    reply = maybe_direct_math_reply(block, text)

    assert reply is not None
    assert "Split the absolute-value equation" in reply
    assert r"x - 2 = 5 \quad\text{or}\quad x - 2 = -5" in reply
    assert block.key_steps[-1].formula == block.canonical_answer == r"x = -3 \text{ or } x = 7"


def test_absolute_value_of_x_uses_the_plus_minus_chip() -> None:
    block = _block("|x|=5")
    assert block is not None
    assert block.key_steps[-1].formula == block.canonical_answer == r"x = \pm 5"


def test_complex_modulus_does_not_split_like_a_real_absolute_value() -> None:
    from sympy import I, Symbol

    from app.modules.math.solve.key_steps import equation_key_steps

    steps = equation_key_steps(abs(Symbol("x") + I), 5, "x")
    assert steps == []


def test_complex_pure_power_shows_the_root_before_simplifying() -> None:
    text = "x^2 + 1 = 0"
    block = _block(text)
    reply = maybe_direct_math_reply(block, text)

    assert reply is not None
    assert r"x = \pm \sqrt{-1}" in reply
    assert block.key_steps[-1].label == "Simplify"
    assert block.key_steps[-1].formula == block.canonical_answer == r"x = \pm i"


def test_negative_rational_root_matches_the_chip() -> None:
    text = "2x^2 + 1 = 0"
    block = _block(text)
    assert block is not None
    assert block.key_steps[-1].formula == block.canonical_answer
    assert r"\frac{\sqrt{2}}{2} i" in block.canonical_answer
    assert r"i}{2}" not in block.key_steps[-1].formula


def test_square_root_of_a_fraction_simplifies_before_the_chip() -> None:
    text = "3x^2 + 3 = 5"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    before, _, _ = reply.partition("```answer")
    assert r"\sqrt{\frac{2}{3}}" in before
    assert r"\frac{\sqrt{6}}{3}" in before
    assert before.index(r"\sqrt{\frac{2}{3}}") < before.index(r"\frac{\sqrt{6}}{3}")
    assert r"\frac{\sqrt{6}}{3}" in reply


def test_perfect_square_finishes_with_the_same_value_as_the_chip() -> None:
    text = "3x^2 = 3"
    block = _block(text)
    reply = maybe_direct_math_reply(block, text)

    assert reply is not None
    assert block.key_steps[-2].formula == r"x = \pm \sqrt{1}"
    assert block.key_steps[-1].formula == block.canonical_answer == r"x = \pm 1"
    assert reply.index(r"x = \pm \sqrt{1}") < reply.index(r"x = \pm 1")


def test_just_the_answer_keeps_the_chip() -> None:
    text = "Just the answer: x^2 + 2 = 6"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert "Given" not in reply
    assert reply.startswith("```answer")
    assert r"\pm 2" in reply


def test_factorable_quadratic_is_a_factor_trace() -> None:
    text = "solve x^2 - 5x + 6 = 0"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert reply.startswith("**Given**")
    assert "Factor the left side" in reply
    assert "Factors as" not in reply
    assert "x - 2" in reply and "x - 3" in reply
    assert "```answer" in reply
    assert "quadratic formula" in reply.lower()
    block = _block(text)
    assert block.key_steps[-1].formula == block.canonical_answer


def test_symmetric_factor_trace_finishes_with_compact_chip_value() -> None:
    block = _block("x^2 - 1 = 0")
    assert block.key_steps[-1].formula == block.canonical_answer == r"x = \pm 1"


def test_bare_how_uses_the_verified_trace_and_explains_each_transformation() -> None:
    block = _block("3x^2 + 3 = 5")
    reply = maybe_direct_math_reply(block, "how?")

    assert reply is not None
    assert "**Given**" in reply
    assert "Subtract 3 from both sides" in reply
    assert "Take the square root of both sides" in reply
    assert "—" in reply.split("```answer")[0]
    assert block.canonical_answer in reply


def test_irreducible_quadratic_uses_the_formula() -> None:
    text = "solve x^2 - 2x - 1 = 0"
    block = _block(text)
    reply = maybe_direct_math_reply(block, text)

    assert reply is not None
    assert "Quadratic formula" in reply
    assert r"\pm" in reply
    assert r"\sqrt{2}" in reply or r"\sqrt{2}" in reply.replace(" ", "")
    assert "1" in reply
    assert "```answer" in reply
    assert block.key_steps[-1].label == "Simplify"
    assert block.key_steps[-1].formula == block.canonical_answer


def test_complex_quadratic_final_step_uses_the_canonical_conjugate_pair() -> None:
    block = _block("x^2 + x + 1 = 0")

    assert block.key_steps[-1].formula == block.canonical_answer
    assert r"\pm" in block.key_steps[-1].formula


def test_joke_request_still_keeps_the_model() -> None:
    text = "solve 2x + 3 = 11 and tell me a joke"
    assert maybe_direct_math_reply(_block(text), text) is None


def test_linear_lesson_numbers_the_move_and_its_result() -> None:
    """Each move keeps the both-sides line and the simplified equation."""
    text = "3x - 3 = 0"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    before_chip, _, _ = reply.partition("```answer")
    assert "**1. Add 3 to both sides**" in before_chip
    assert "$3 x - 3 + 3 = 0 + 3$" in before_chip
    assert "$3 x = 3$" in before_chip
    assert "**2. Divide both sides by 3**" in before_chip
    assert r"\frac{3 x}{3} = \frac{3}{3}" in before_chip
    assert "$x = 1$" in before_chip
    assert before_chip.index("Divide both sides by 3") < before_chip.index("**Answer**")
    assert r"\cancel" not in before_chip
    assert "Simplify" not in before_chip
    assert "cancels" not in before_chip
    assert "undoes" not in before_chip
    assert before_chip.startswith("**Given**  \n$3 x - 3 = 0$")
    assert "x = 1" in reply


def test_explain_keeps_the_why_sentence() -> None:
    text = "explain 3x - 3 = 0"
    reply = maybe_direct_math_reply(_block(text), text)

    assert reply is not None
    assert "Add 3 to both sides" in reply
    assert "—" in reply.split("```answer")[0]
    assert r"\cancel{3}" in reply


def test_format_omits_reasons_unless_asked() -> None:
    verified = _block("3x - 3 = 0")
    short = format_equation_lesson_reply(verified, include_reasons=False)
    long = format_equation_lesson_reply(verified, include_reasons=True)
    # Notes name every move; only the asked-for version adds the reason.
    assert "undoes" not in short.split("```answer")[0]
    assert "undoes" in long.split("```answer")[0]


def test_glued_plain_power_is_an_exponent() -> None:
    """`3x2+4=4` is `3x^2+4=4`. Splitting `x2` into `x*2` solved `6x+4=4`."""
    from app.modules.math.solve.parse import _normalize_expr

    assert _normalize_expr("3x2+4") == "3*x**2+4"
    assert _normalize_expr("x^2") == "x**2"
    assert _normalize_expr("2x") == "2*x"
    assert _normalize_expr("x0+1") == "x0+1"
    assert _normalize_expr("x1+1") == "x1+1"
    assert _normalize_expr("sin2") == "sin2"
    assert _normalize_expr("log2(8)") == "(ln(8)/ln(2))"
    assert _normalize_expr("x2^3") == "x2**3"

    block = _block("3x2+4=4")
    assert block is not None
    assert block.given_latex is not None
    assert "x^{2}" in block.given_latex
    assert "6" not in block.given_latex
    assert block.canonical_answer is not None
    assert "0" in block.canonical_answer


def test_scanner_caption_solves_the_confirmed_line() -> None:
    text = "Solve the math problem in this image step by step.\n\nI read this as: x^2 - 5x + 6 = 0"
    block = _block(text)
    assert block is not None
    assert block.canonical_answer is not None
    assert "2" in block.canonical_answer
    assert "3" in block.canonical_answer

    glued = "Solve the math problem in this image step by step.\n\nI read this as: 3x2+4=4"
    block = _block(glued)
    assert block is not None
    assert block.given_latex is not None
    assert "x^{2}" in block.given_latex
    assert "6" not in block.given_latex


def test_confirmed_scan_of_glued_power_uses_the_solver() -> None:
    from app.modules.math.ocr import extract_from_confirmed_reading
    from app.modules.math.tools.image_intent import intent_from_image_extract

    extracted = extract_from_confirmed_reading("3x2+4=4")
    assert extracted is not None
    intent = intent_from_image_extract(extracted)
    assert intent is not None
    block = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.given_latex is not None
    assert "x^{2}" in block.given_latex
    assert "6" not in block.given_latex


def test_file_caption_period_still_verifies() -> None:
    text = "Solve the math problem in this file.\n\n3x^2 + 4 = 4"
    block = _block(text)
    assert block is not None
    assert block.given_latex is not None
    assert "x^{2}" in block.given_latex
    assert ". " not in (block.given_latex or "")
    assert block.canonical_answer is not None
    assert "0" in block.canonical_answer


def test_file_excerpt_with_caption_and_trailing_prose_solves() -> None:
    shown = "[File: quiz.pdf]\nx^2 - 5x + 6 = 0\nShow your work."
    block = _block(shown)
    assert block is not None
    assert block.canonical_answer is not None
    assert "2" in block.canonical_answer
    assert "3" in block.canonical_answer

    caption = "Summarize this file.\n\n[File: /attachments/abc/file]\n2x+3=7"
    block = _block(caption)
    assert block is not None
    assert block.canonical_answer is not None
    assert "2" in block.canonical_answer


def test_file_marker_bare_equation_reaches_sympy() -> None:
    from app.modules.math.tools import needs_symbolic_math

    text = "[File: quiz.pdf]\nx^2 - 5x + 6 = 0"
    assert needs_symbolic_math(text) is True
    block = _block(text)
    assert block is not None
    assert block.canonical_answer is not None
    assert "2" in block.canonical_answer
    assert "3" in block.canonical_answer


def test_divide_cancels_the_variable_coeff_not_the_constant() -> None:
    from sympy import Symbol

    from app.modules.math.solve.key_steps import equation_key_steps

    x = Symbol("x")
    steps = equation_key_steps(2 * x + 3, 11, "x")
    divide = next(step for step in steps if step.label.startswith("Divide"))
    assert r"\cancel{2}" in divide.formula
    assert r"\frac{8}{2}" in divide.formula
    assert r"\cancel{8}" not in divide.formula


@pytest.mark.parametrize(
    ("degree", "factored", "final"),
    [
        (2, r"\left(- a + x\right) \left(x - 1\right) = 0", r"x = 1 \text{ or } x = a"),
        (
            3,
            r"x \left(- a + x\right) \left(x - 1\right) = 0",
            r"x = 0 \text{ or } x = 1 \text{ or } x = a",
        ),
    ],
)
def test_parametric_factor_sorts_without_a_dict_root(monkeypatch, degree, factored, final) -> None:
    """``x - a`` has no number to order by, so it sorts as 0 (ES-39).

    Solving it for every symbol gave SymPy's dict, and ``float`` raised a TypeError that the
    silent ``except`` took for a decline; strict declines raised it.
    """
    from sympy import Symbol

    from app.modules.math.solve.key_steps import _factor_order, equation_key_steps

    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1")
    x, a = Symbol("x"), Symbol("a")
    lhs = (x**2 - (a + 1) * x + a) * (x if degree == 3 else 1)
    steps = equation_key_steps(lhs.expand(), 0, "x")
    assert steps[0].formula == factored
    assert steps[-1].formula == final
    assert _factor_order(x - a, x) == (True, 0.0)
    assert _factor_order(x - 3, x) == (True, 3.0)
    assert _factor_order(x, x) == (False, 0.0)


def test_factor_order_reads_no_root_from_a_dict(monkeypatch) -> None:
    """``solve(P - I V, P)`` with a real P is ``{P: 0}``, not a list (ES-39).

    Indexing it raised a KeyError that the decline took for SymPy failing; strict declines
    raised it. The factor sorts as 0, as the decline did.
    """
    from sympy import I, Symbol

    from app.modules.math.solve.key_steps import _factor_order, equation_key_steps

    monkeypatch.setenv("RECALL_STRICT_DECLINES", "1")
    p, v = Symbol("P", real=True), Symbol("V", real=True)
    assert _factor_order(p - I * v, p) == (True, 0.0)
    assert equation_key_steps(p, I * v, "P") == []
