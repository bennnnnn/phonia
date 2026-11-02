"""Tests for math tools heuristics and prompt injection."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.math import tools as math_tools
from app.modules.math.schemas import MathImageExtract, MathIntent
from app.modules.math.tools.prompt import NOTHING_TO_GRAPH
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.prompt import build_physics_augmentation
from app.services.solving import VERIFIED_MATH_BEGIN
from app.tests.modules.math.prompt_support import augment_prompt_messages


def test_math_intent_has_no_dead_expression_kind() -> None:
    """Schema used to list kind=\"expression\" with no extractor or block
    builder — dead surface that invited half-implemented paths. Removed."""
    with pytest.raises(ValidationError):
        MathIntent.model_validate({"kind": "expression", "expr": "x+1"})


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Solve x^2 + 2 = 6", True),
        ("Show steps: 2x+3=11", True),
        ("Just the answer: x^2+2=6", True),
        ("What's the weather?", False),
        ("A rectangle is 8×5 cm. Find the diagonal angle.", True),
        ("Graph y = x^2", True),
        ("Draw a rectangle", True),
    ],
)
def test_needs_symbolic_math(text: str, expected: bool) -> None:
    assert math_tools.needs_symbolic_math(text) is expected


def test_needs_symbolic_math_rejects_oversize_before_prefix_stripping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.math.tools import lesson

    def fail_if_called(_text: str) -> str:
        raise AssertionError("oversize input reached lesson-prefix stripping")

    monkeypatch.setattr(lesson, "strip_lesson_prefixes", fail_if_called)
    assert math_tools.needs_symbolic_math("show work " * 3201) is False


def test_a_buried_solve_word_is_not_an_equation() -> None:
    assert math_tools.extract_math_intent("I resolved x=1") is None
    solved = math_tools.extract_math_intent("I solved 2x+3=7")
    assert solved is not None
    assert solved.kind == "equation"
    intent = math_tools.extract_math_intent("solve 2x=1")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "2x"
    assert intent.rhs == "1"
    # A value already stated is not solved again: that certified what was typed.
    assert math_tools.extract_math_intent("solve x=1") is None


def test_extract_equation_intent() -> None:
    intent = math_tools.extract_math_intent("Solve x^2 + 2 = 6")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "x^2 + 2"
    assert intent.rhs == "6"
    assert intent.variable == "x"


def test_chained_equality_is_not_claimed_by_the_equation_solver() -> None:
    assert math_tools.extract_math_intent("2x+3=3=7") is None


def test_glued_graph_command_is_vertical_line_not_multiplied_letters() -> None:
    """``X=6graph`` is ``graph x=6`` (vertical line), not 6·g·r·a·p·h."""
    intent = math_tools.extract_math_intent("X=6graph")
    assert intent is not None
    assert intent.kind == "vertical"
    assert intent.point_x == 6.0


def test_composer_dollar_wrap_still_vertical_line() -> None:
    """Math keyboard wraps the 6 in ``$...$``; that must not hide the plot."""
    intent = math_tools.extract_math_intent("X=$6$graph")
    assert intent is not None
    assert intent.kind == "vertical"
    assert intent.point_x == 6.0


def test_glued_english_on_equation_is_not_implicit_product() -> None:
    """Trailing English on a bare equation is stripped, not multiplied letters."""
    intent = math_tools.extract_math_intent("2x+3=7please")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "2x+3"
    assert intent.rhs == "7"


def test_paragraph_is_not_a_graph_keyword() -> None:
    assert math_tools.needs_symbolic_math("write a paragraph about trees") is False


def test_glued_please_is_equation_not_graph() -> None:
    intent = math_tools.extract_math_intent("2X=6please")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "2X"
    assert intent.rhs == "6"


def test_glued_graph_is_not_a_vega_chart_question() -> None:
    from app.modules.turn_reading.chart import is_chart_question

    assert is_chart_question("X=6graph") is False


def test_mass_energy_equation_is_not_peeled() -> None:
    energy = math_tools.extract_math_intent("E=mc^2")
    assert energy is not None
    assert energy.kind == "equation"
    assert energy.lhs == "E"
    assert energy.rhs == "mc^2"


@pytest.mark.parametrize(
    "text, expected_var",
    [
        ("Solve for y: x+y=5", "y"),
        ("solve for y in x+y=5", "y"),
        ("find y if x+y=5", "y"),
        ("find the value of y in 2y = 10", "y"),
        ("Solve for x: x+y=5", "x"),
    ],
)
def test_extract_equation_respects_solve_for_variable(text: str, expected_var: str) -> None:
    """BUG FIX: 'Solve for y: x+y=5' used to solve for x (alphabetical first
    of guess_variables) and return the wrong answer in the verified card. The
    extractor now parses the explicit 'solve for <var>' / 'find <var>' cue."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.variable == expected_var


def test_extract_equation_solve_for_unknown_variable_falls_back() -> None:
    """'solve for z' where z is not in the equation must not solve for z —
    fall back to the guessed variable rather than producing an empty solve."""
    intent = math_tools.extract_math_intent("Solve for z: x + 2 = 5")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.variable == "x"


@pytest.mark.parametrize(
    "text, expected_var",
    [
        ("Solve for e: e + 1 = 5", "e"),
        ("solve for E in E - 2 = 3", "E"),
    ],
)
def test_extract_equation_honors_explicit_solve_for_e(text: str, expected_var: str) -> None:
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.variable == expected_var


def test_solve_for_e_produces_verified_answer() -> None:
    intent = math_tools.extract_math_intent("Solve for e: e + 1 = 5")
    assert intent is not None
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    assert "4" in block.canonical_answer
    assert "no solution" not in block.canonical_answer.lower()


def test_extract_equation_sin_pi_x_still_solves_for_x() -> None:
    """Default guess still excludes e so Euler's number is not a free variable."""
    intent = math_tools.extract_math_intent("solve sin(pi*x) = 0")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.variable == "x"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2x+3=7", True),
        ("y=x^2", True),
        ("a+b=10", True),
        ("let x = 5", True),
        ("the meeting = 3pm", False),
        ("What's the weather?", False),
        ("let x = the reason I'm late, it doesn't matter", False),
        ("[File: quiz.pdf]\nx^2 - 5x + 6 = 0", True),
        ("[File: quiz.pdf]\nx^2 - 5x + 6 = 0\nShow your work.", True),
        ("[File: /attachments/abc/file]\n[File (application/pdf)]\n2x+3=7", True),
        ("Summarize this file.\n\n2x+3=7", True),
        ("Summarize this file.\n\n[File: notes.pdf]\nNo equation here.", False),
    ],
)
def test_needs_symbolic_math_bare_equation(text: str, expected: bool) -> None:
    """Bare algebraic equations (no 'solve'/'find' keyword) now trigger SymPy.
    Prose with an '=' but no math sides does not."""
    assert math_tools.needs_symbolic_math(text) is expected


def test_late_reason_prose_does_not_extract_an_equation() -> None:
    assert math_tools.extract_math_intent("let x = the reason I'm late, it doesn't matter") is None


@pytest.mark.parametrize(
    "text",
    [
        "draw y=x^2",
        "chart y=x^2",
        "sketch y = x^2",
        "visualize y=x^2",
        "what does y=x^2 look like",
        "show the shape of y=x^2",
        "show y=x^2",
    ],
)
def test_plot_phrasing_extracts_as_graph_not_equation(text: str) -> None:
    """``draw y=x^2`` used to miss graph_expr and ship a verified *solve* of
    y=x^2 (no diagram). Plot verbs must claim the graph kind."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "graph"
    assert intent.expr
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "Equation:" not in block.text
    assert "a d r" not in block.text


@pytest.mark.parametrize(
    "text",
    [
        "tell me about y=x^2",
        "help me understand y=x^2",
        "describe the curve y=x^3",
        "explain why y=mx+b",
        "my teacher wrote v=d/t on the board",
        "the slope formula m=(y2-y1)/(x2-x1)",
        "the answer key says x=5 but i got 6",
        "i dont get why y=x^2 is a parabola",
        "remind me what pv=nrt means",
        "in chemistry pv=nrt is the gas law",
        "summarize the identity sin^2+cos^2=1",
        "how do I find the slope of y=x^2",
    ],
)
def test_prose_mentioning_an_equation_is_not_a_verified_solve(text: str) -> None:
    """Conversational mentions must not become kind=equation under a
    'verified by SymPy' header. Graph/other kinds are allowed; a solve is not."""
    intent = math_tools.extract_math_intent(text)
    assert intent is None or intent.kind != "equation"
    if intent is not None:
        block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
        if block is not None:
            assert "Equation:" not in block.text
            singles = [tok for tok in block.text.split() if len(tok) == 1 and tok.isalpha()]
            assert len(singles) < 3


@pytest.mark.parametrize(
    "text",
    [
        "solve 2x+3=7",
        "find x if 2x+3=7",
        "calculate 2x+3=7",
        "what is x when 2x=10",
        "2x+3=7",
        "y=x^2",
        "graph y=x^2",
        "simplify 4x+2x=18",
        "show me how to solve 2x+3=7",
        "Show steps: 2x+3=7",
        "Just the answer: 2x+3=7",
    ],
)
def test_imperative_and_bare_equations_still_extract(text: str) -> None:
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind in {"equation", "graph"}


def test_simplify_equation_falls_through_to_solve() -> None:
    """``simplify 4x+2x=18`` used to match calculus simplify and fail verification."""
    intent = math_tools.extract_math_intent("simplify 4x+2x=18")
    assert intent is not None
    assert intent.kind == "equation"
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    assert "3" in block.canonical_answer


def test_let_x_then_evaluate_is_not_solve_x_equals_five() -> None:
    """``Let x = 5. What is x + 2?`` must eval to 7, not stamp ```answer x = 5."""
    intent = math_tools.extract_math_intent("Let x = 5. What is x + 2?")
    assert intent is not None
    assert intent.kind == "arithmetic"
    assert intent.expr is not None
    # Evaluated with x = 5 substituted (the given-values rule writes the working).
    assert intent.school_op == "expression_value" and intent.evaluation_point == "5"
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    assert "7" in block.canonical_answer
    assert "x = 5" not in block.canonical_answer.replace(" ", "")
    # A bare given is not a problem to solve; "x = 5" would only certify itself.
    assert math_tools.extract_math_intent("let x = 5") is None


def test_chained_equals_is_not_collapsed_into_one_equation() -> None:
    """``2x + 3 = 3 = 7`` must not be rewritten as ``2x + 3 = 7``."""
    assert math_tools.extract_math_intent("Solve 2x + 3 = 3 = 7") is None


def test_extract_bare_equation_intent() -> None:
    intent = math_tools.extract_math_intent("2x+3=7")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "2x+3"
    assert intent.rhs == "7"
    assert intent.variable == "x"


def test_extract_latex_inline_sixth_power_equation() -> None:
    intent = math_tools.extract_math_intent("$x^{6}=1$")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "x^6"
    assert intent.rhs == "1"
    assert intent.variable == "x"
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    # School answers are real when a real root exists; the four non-real
    # sixth roots of unity need an explicit request.
    assert r"\pm 1" in block.canonical_answer
    assert " i" not in block.canonical_answer


@pytest.mark.parametrize(
    "text, expected_lhs",
    [
        ("roots of x^2 - 4", "x^2 - 4"),
        ("find the roots of x^3 - 1", "x^3 - 1"),
        ("zeros of x^2 - 9", "x^2 - 9"),
    ],
)
def test_extract_roots_of_rewrites_to_equation(text: str, expected_lhs: str) -> None:
    """'roots of <expr>' / 'zeros of <expr>' have no '=', so they used to
    fall through every extractor and ship unverified. They now rewrite to
    'solve <expr> = 0' and solve as a plain equation."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == expected_lhs
    assert intent.rhs == "0"


def test_english_calculus_reads_as_the_words_say() -> None:
    """``x squared plus 3x`` was once letter-producted (``s*q*u*a*r*e*d``); it reads as
    x^2 + 3x now that spoken maths becomes symbols (match/spoken.py)."""
    intent = math_tools.extract_math_intent("what's the derivative of x squared plus 3x")
    assert intent is not None and intent.operation == "differentiate"
    assert intent.expr == "x^2 + 3x"


def test_symbolic_calculus_still_extracts() -> None:
    intent = math_tools.extract_math_intent("d/dx x**2 + 3x")
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.operation == "differentiate"
    assert intent.expr == "x**2 + 3x"


def test_english_roots_of_does_not_solve_a_equals_zero() -> None:
    intent = math_tools.extract_math_intent("roots of my hair are 2 inches long")
    assert intent is None


def test_system_longer_than_four_equations_is_not_verified() -> None:
    """Five equations used to be sliced to four and verified as that smaller system."""
    text = "solve a+b=1, a+c=2, a+d=3, b+c=4, b+d=5"
    assert math_tools.extract_math_intent(text) is None


def test_photo_system_longer_than_four_equations_is_not_verified() -> None:
    from app.modules.math.tools.image_intent import intent_from_image_extract

    equations = [(f"a+{name}", "1") for name in ("b", "c", "d", "e", "f")]
    extracted = MathImageExtract(kind="system", equations=equations, variables=["a", "b"])
    assert intent_from_image_extract(extracted) is None


def test_system_of_four_equations_still_extracts() -> None:
    text = "solve a+b=1, a+c=2, a+d=3, b+c=4"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "system"
    assert intent.system_equations is not None
    assert len(intent.system_equations) == 4


def test_extract_system_intent_for_multiple_equations() -> None:
    """BUG FIX (most severe correctness bug found in the audit): before this
    fix, a message with 2+ equations fell through to the single-equation
    branch, which only ever looked at the first clause."""
    intent = math_tools.extract_math_intent("solve x+y=5, x-y=1")
    assert intent is not None
    assert intent.kind == "system"
    assert intent.system_equations == [("x+y", "5"), ("x-y", "1")]
    assert intent.system_variables is not None
    assert set(intent.system_variables) >= {"x", "y"}


def test_spaced_system_does_not_drop_first_x() -> None:
    """Prose 'x + y' after 'the system' used to extract ('+ y', '5') and
    verify the wrong solution (x=6, y=5) against correct prose."""
    text = "Solve the system x + y = 5 and x - y = 1."
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "system"
    assert intent.system_equations == [("x + y", "5"), ("x - y", "1")]
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    assert "x = 3" in block.canonical_answer
    assert "y = 2" in block.canonical_answer
    assert "x = 6" not in block.canonical_answer


def test_trailing_sentence_period_still_solves_equation() -> None:
    intent = math_tools.extract_math_intent("Solve 1/2 + 1/3 = x.")
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.lhs == "1/2 + 1/3"
    assert intent.rhs == "x"
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    compact = block.canonical_answer.replace(" ", "")
    assert "5}{6}" in compact or "5/6" in compact


_WORKED_QUADRATIC_PASTE = r"""\[ 2x^2-7x+3=0 \]
Factor it:
 \[ 2x^2-6x-x+3=0 \]
Group terms:
 \[ 2x(x-3)-1(x-3)=0 \] \[ (2x-1)(x-3)=0 \]
So:
 \[ 2x-1=0 \Rightarrow x=\frac12 \]
or
 \[ x-3=0 \Rightarrow x=3 \]
**Final answer:**
 \[ \boxed{x=\frac12,\ 3} \]"""


def test_worked_quadratic_paste_is_not_a_no_solution_system() -> None:
    """Live: a pasted factoring write-up was extracted as a simultaneous
    system (2x-1=0 AND x-3=0) and the gray pill said 'no solution'."""
    intent = math_tools.extract_math_intent(_WORKED_QUADRATIC_PASTE)
    assert intent is not None
    assert intent.kind == "equation"
    assert intent.variable == "x"
    compact = (intent.lhs or "").replace(" ", "")
    assert "x^2" in compact
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.canonical_answer is not None
    assert "no solution" not in block.canonical_answer.lower()
    assert "1}{2}" in block.canonical_answer or "1/2" in block.canonical_answer
    assert "3" in block.canonical_answer
    assert r"\text{ or }" in block.canonical_answer
    assert r"\begin{aligned}" not in block.canonical_answer


def test_two_real_roots_format_with_or_not_aligned_stack() -> None:
    """Live: aligned + 48px KaTeX pill hid the second row (x=3) under x=1/2."""
    out = math_tools._format_equation_answer(
        [r"x = \frac{1}{2}", "x = 3"],
        "finite",
    )
    assert out == r"x = \frac{1}{2} \text{ or } x = 3"
    many = math_tools._format_equation_answer(
        ["x = 1", "x = 2", "x = 3"],
        "finite",
    )
    assert r"\begin{aligned}" in many


@pytest.mark.asyncio
async def test_augment_prompt_injects_system_solve_block() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "solve x+y=5, x-y=1"
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "Equation 1:" in verified.text
    assert "Equation 2:" in verified.text
    assert "x = 3" in verified.text
    assert "y = 2" in verified.text
    assert any("x = 3" in m["content"] for m in out if m["role"] == "system")


@pytest.mark.asyncio
async def test_physics_augmentation_verifies_kinematics_trajectory() -> None:
    settings = Settings(math_tools_enabled=True)
    note, verified, solve_failed = await build_physics_augmentation(
        "A ball is dropped from 20m. How long until it hits the ground?",
        settings,
    )

    assert verified is not None
    assert solve_failed is False
    assert note is not None and note.startswith(verified.text + "\n\n")
    assert "Physics reply policy for this request:" in note
    assert verified.canonical_answer == "2.02 s"
    # The drop is drawn as the fall itself, from the 20 m ledge to the ground;
    # a height-time curve beside it would plot the same samples again.
    (scene,) = verified.canonical_fences
    assert scene["type"] == "projectile_motion"
    assert scene["title_key"] == "free_fall"
    path = scene["bodies"][0]["path"]
    radius = scene["bodies"][0]["radius"]
    assert path[0][1] == pytest.approx(20.0 + radius)
    assert path[-1][1] == pytest.approx(radius)


@pytest.mark.asyncio
async def test_chained_equality_skips_llm_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.math.tools import prompt as math_prompt

    async def _boom(_text: str, _settings: Settings) -> None:
        raise AssertionError("LLM extract must not rewrite a chained equality")

    monkeypatch.setattr(math_prompt, "llm_extract_math_intent", _boom)
    note, verified = await math_prompt.build_math_augmentation(
        "Solve 2x + 3 = 3 = 7",
        Settings(math_tools_enabled=True, math_llm_extract_enabled=True),
        needs_math=True,
    )
    assert verified is None
    assert note is not None
    assert "chains equalities" in note
    assert not note.startswith("Math note:")


@pytest.mark.asyncio
async def test_augment_prompt_no_intent_forbids_invented_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.math.tools import prompt as math_prompt

    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def _no_llm_extract(_text: str, _settings: Settings) -> None:
        return None

    monkeypatch.setattr(math_prompt, "llm_extract_math_intent", _no_llm_extract)
    settings = Settings(math_tools_enabled=True)
    note, verified = await math_prompt.build_math_augmentation(
        "find the angle",
        settings,
        needs_math=True,
    )
    assert verified is None
    assert note is not None
    assert "Do not claim verification or invent missing measures" in note
    assert "ask at most one necessary clarification question" in note


@pytest.mark.asyncio
async def test_augment_prompt_system_flags_inconsistent_equations() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "solve x+y=5, x+y=10"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "inconsistent" in verified.text.lower()


@pytest.mark.parametrize(
    "text, expected_expr, expected_var, expected_guess",
    [
        (
            "use newton's method to find the root of x^3 - 2x - 5 = 0 starting at x0 = 2",
            "x^3 - 2x - 5",
            "x",
            2.0,
        ),
        ("newton's method for x^2 - 2 = 0 with initial guess of 1", "x^2 - 2", "x", 1.0),
        ("numerically solve x = cos(x) starting near 1", "(x)-(cos(x))", "x", 1.0),
        ("find the root of x^3 - 2x - 5 = 0 near x=2", "x^3 - 2x - 5", "x", 2.0),
        # "near" inside "nonlinear" and "linear" was read as the guess label, and the
        # equation was cut off before it.
        (
            "numerically solve the nonlinear equation cos(x) = x with guess 0.5",
            "(cos(x))-(x)",
            "x",
            0.5,
        ),
        (
            "use newton's method to solve the linear equation 2x - 3 = 0 with guess 4",
            "2x - 3",
            "x",
            4.0,
        ),
    ],
)
def test_extract_numerical_method_intent(
    text: str, expected_expr: str, expected_var: str, expected_guess: float
) -> None:
    assert math_tools.needs_symbolic_math(text) is True
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "numerical_method"
    assert intent.expr == expected_expr
    assert intent.variable == expected_var
    assert intent.newton_guess == expected_guess


@pytest.mark.parametrize(
    "text, guess, equation",
    [
        (
            "numerically solve the nonlinear equation cos(x) = x with guess 0.5",
            0.5,
            "numerically solve the nonlinear equation cos(x) = x",
        ),
        (
            "use newton's method to solve the linear equation 2x - 3 = 0 with guess 4",
            4.0,
            "use newton's method to solve the linear equation 2x - 3 = 0",
        ),
        # A label inside a longer word is not the label.
        (
            "find the root of the linear map f(x) = 2x - 3",
            1.0,
            "find the root of the linear map f(x) = 2x - 3",
        ),
        ("restarting at 2, solve x^2 - 2 = 0", 1.0, "restarting at 2, solve x^2 - 2 = 0"),
        # Still read where it is a word, in the same order.
        ("use newton's method on x^2 - 2 = 0 near 1.5", 1.5, "use newton's method on x^2 - 2 = 0"),
        ("find the root of x^3 - 2x - 5 = 0 near x=2", 2.0, "find the root of x^3 - 2x - 5 = 0"),
        (
            "newton's method for x^2 - 2 = 0 with initial guess of -1",
            -1.0,
            "newton's method for x^2 - 2 = 0",
        ),
        (
            "use newton's method on x^3 - 2x - 5 = 0 starting at x0 = 2",
            2.0,
            "use newton's method on x^3 - 2x - 5 = 0",
        ),
    ],
)
def test_newton_guess_labels_are_whole_words(text: str, guess: float, equation: str) -> None:
    from app.modules.math.tools.direct_newton import _parse_newton_guess

    assert _parse_newton_guess(text) == (guess, equation)


def test_extract_numerical_method_intent_defaults_guess_when_absent() -> None:
    intent = math_tools.extract_math_intent("use newton's method on x^2 - 2 = 0")
    assert intent is not None
    assert intent.kind == "numerical_method"
    assert intent.newton_guess == 1.0


@pytest.mark.asyncio
async def test_augment_prompt_injects_newton_iteration_table() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "use newton's method to find the root of x^3 - 2x - 5 = 0 starting at x0 = 2"
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "n=0" in verified.text
    assert "Converged" in verified.text
    assert "2.0945514817" in verified.text or "2.094551482" in verified.text
    assert any("Converged" in m["content"] for m in out if m["role"] == "system")
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "answer"
    assert "```answer\n" not in verified.text
    assert verified.canonical_answer
    assert verified.canonical_fence["content"]


@pytest.mark.asyncio
async def test_augment_prompt_newton_reports_non_convergence() -> None:
    """BUG FIX target: a request that can't converge within the iteration
    budget must say so explicitly rather than silently omitting a root or
    (worse) presenting the last iterate as a verified answer."""
    settings = Settings(math_tools_enabled=True)
    text = "use newton's method to find the root of x^3 - 2x - 5 = 0 starting at x0 = 2"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    from app.modules.math.schemas import NewtonMethodResult

    with patch(
        "app.modules.math.tools.math_solve.newton_method",
        return_value=NewtonMethodResult(
            iterations=[], converged=False, root=None, iterations_used=0
        ),
    ):
        block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert "did not converge" in block.text.lower()
    assert block.canonical_fence is None
    assert "```answer" not in block.text


def test_extract_rectangle_intent() -> None:
    intent = math_tools.extract_math_intent("rectangle 8 x 5 cm find diagonal")
    assert intent is not None
    assert intent.kind == "rectangle"
    assert intent.width == 8
    assert intent.height == 5


def test_extract_draw_rectangle_defaults() -> None:
    intent = math_tools.extract_math_intent("Draw a rectangle")
    assert intent is not None
    assert intent.kind == "rectangle"
    assert intent.width == 6
    assert intent.height == 4


@pytest.mark.parametrize(
    "text, wants_diagonal, wants_angle, wants_area, wants_perimeter",
    [
        ("rectangle area with 4 by 5", False, False, True, False),
        ("rectangle 8 x 5 cm find diagonal", True, False, False, False),
        ("rectangle 8 x 5 cm diagonal angle", True, True, False, False),
        ("rectangle perimeter 4 by 5", False, False, False, True),
        ("rectangle 4 by 5", False, False, False, False),
    ],
)
def test_extract_rectangle_intent_captures_what_was_asked(
    text: str, wants_diagonal: bool, wants_angle: bool, wants_area: bool, wants_perimeter: bool
) -> None:
    intent = math_tools.extract_math_intent(text)
    assert isinstance(intent, MathIntent)
    assert intent.wants_diagonal is wants_diagonal
    assert intent.wants_angle is wants_angle
    assert intent.wants_area is wants_area
    assert intent.wants_perimeter is wants_perimeter


def test_extract_circle_radius_intent() -> None:
    intent = math_tools.extract_math_intent("Draw a circle with radius 4 cm")
    assert intent is not None
    assert intent.kind == "circle"
    assert intent.radius == 4


def test_extract_circle_diameter_intent() -> None:
    intent = math_tools.extract_math_intent("circle diameter 10")
    assert intent is not None
    assert intent.kind == "circle"
    assert intent.radius == 5
    assert intent.wants_diameter is False
    assert intent.given_diameter is True


def test_extract_circle_intent_defaults_without_dims() -> None:
    intent = math_tools.extract_math_intent("Draw a circle")
    assert intent is not None
    assert intent.kind == "circle"
    assert intent.radius == 5


@pytest.mark.parametrize(
    "text",
    [
        "what is a circle?",
        "explain the unit circle",
        "the circle is a set of points",
        "what is a trapezoid?",
        "define a parallelogram",
        "area of a triangle",
        "what is a right triangle",
        "sector of a circle with radius 5",
        "what is a cylinder?",
        "what is a sphere",
    ],
)
def test_geometry_does_not_invent_dims_without_draw_or_measures(text: str) -> None:
    """BUG FIX: bare shape prose used to invent default dimensions and emit a
    SymPy-verified ```geometry fence (e.g. circle r=5, trap 4x8x5)."""
    intent = math_tools.extract_math_intent(text)
    assert intent is None or intent.kind not in {
        "circle",
        "trapezoid",
        "parallelogram",
        "triangle",
        "right_triangle",
        "sector",
        "square",
        "rectangle",
        "solid",
    }


@pytest.mark.parametrize(
    "text, expected_kind",
    [
        ("solve x^2 + y^2 = 25 for the circle of radius 5", "equation"),
        ("find the equation of a circle with radius 4", None),
        ("equation of the circle with center (0,0) and radius 5", None),
        ("solve x^2 + y^2 = 1 (unit circle)", "equation"),
    ],
)
def test_geometry_does_not_steal_algebra_asks(text: str, expected_kind: str | None) -> None:
    """Geometry extractors run before equation/graph. A radius/dim cue must
    not swallow an algebra ask into a ```geometry fence."""
    intent = math_tools.extract_math_intent(text)
    if expected_kind is None:
        assert intent is None or intent.kind not in {
            "circle",
            "triangle",
            "right_triangle",
            "trapezoid",
            "parallelogram",
            "sector",
        }
    else:
        assert intent is not None
        assert intent.kind == expected_kind


def test_draw_circle_with_radius_still_geometry() -> None:
    """Draw cue wins over algebra deferral — explicit diagram requests stay
    on the geometry path even if the sentence also says 'equation'."""
    intent = math_tools.extract_math_intent(
        "draw a circle with radius 4 and show the equation labels"
    )
    assert intent is not None
    assert intent.kind == "circle"
    assert intent.radius == 4


def test_draw_right_triangle_uses_named_legs_not_default_6_by_4() -> None:
    """BUG FIX: 'legs 3 and 4' is not an 8x5 dim pair, so extract fell
    through to the 6x4 default and the diagram/area pill were wrong."""
    intent = math_tools.extract_math_intent(
        "Draw a right triangle with legs 3 and 4. Label the sides including the hypotenuse."
    )
    assert intent is not None
    assert intent.kind == "right_triangle"
    assert intent.base == 3
    assert intent.height == 4
    assert intent.wants_area is False


def test_draw_right_triangle_does_not_attach_area_answer_pill() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent(
        "Draw a right triangle with legs 3 and 4. Label the sides including the hypotenuse."
    )
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_fence is not None
    assert block.canonical_fence["type"] == "right_triangle"
    assert block.canonical_fence["base"] == 3
    assert block.canonical_fence["height"] == 4
    assert block.canonical_answer is None
    assert "Opposite the base (3 units) is 36.9°" in block.text
    assert "opposite the height (4 units) is 53.1°" in block.text


def test_area_of_right_triangle_with_legs_still_answers_area() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("area of a right triangle with legs 3 and 4")
    assert isinstance(intent, MathIntent)
    assert intent.wants_area is True
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer == "6"


@pytest.mark.parametrize(
    "text",
    [
        "(2,3)",
        "(2, 3)",
        "(2.3)",  # BUG FIX: comma-for-period mobile keyboard slip
        "(-2, 3)",
        "plot the point (2, 3)",
        "mark point 2, 3",
    ],
)
def test_extract_bare_point_intent(text: str) -> None:
    """BUG FIX regression: a bare coordinate pair (e.g. answering "what
    point?" with "(2,3)") had no intent detection at all, so the model was
    left to freely improvise — observed inventing an unrequested line
    (y=1.5x) that merely happens to pass through the point instead of
    marking the point itself."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "point"
    assert intent.point_x == pytest.approx(-2.0 if text.startswith("(-2") else 2.0)
    assert intent.point_y == pytest.approx(3.0)


def test_bare_point_does_not_misfire_on_prose_with_a_decimal_in_parens() -> None:
    """The whole-message match requirement keeps this from misfiring on
    ordinary prose that happens to contain a parenthesized decimal."""
    intent = math_tools.extract_math_intent("The result is about (2.3) give or take")
    assert intent is None or intent.kind != "point"


def test_extract_square_intent() -> None:
    intent = math_tools.extract_math_intent("Draw a square with side 5 cm")
    assert intent is not None
    assert intent.kind == "square"
    assert intent.side == 5


@pytest.mark.parametrize(
    "text",
    [
        "solve square root of x = 4",
        "graph the square root of x",
        "factor this perfect square trinomial",
        "what is the square of 7",
    ],
)
def test_square_root_does_not_become_geometry_square(text: str) -> None:
    """BUG FIX: substring 'square' used to inject a default 5 cm square."""
    intent = math_tools.extract_math_intent(text)
    assert intent is None or intent.kind != "square"


def test_draw_square_without_side_still_defaults() -> None:
    intent = math_tools.extract_math_intent("Draw a square")
    assert intent is not None
    assert intent.kind == "square"
    assert intent.side == 5


@pytest.mark.parametrize(
    "text, shape, volume_asked, sa_asked",
    [
        ("volume of a cube with side 5 cm", "cube", True, False),
        ("surface area of a cube side 4", "cube", False, True),
        ("volume of a rectangular prism 3 by 4 by 5", "rectangular_prism", True, False),
        ("Volume of a rectangular prism 3 by 4 by 5.", "rectangular_prism", True, False),
        ("volume of a cuboid length 3 width 4 height 5", "rectangular_prism", True, False),
        ("volume of a cylinder radius 3 height 10", "cylinder", True, False),
        ("volume of a cone radius 3 height 4", "cone", True, False),
        ("volume of a sphere radius 3", "sphere", True, False),
        ("volume of a square pyramid base 6 height 4", "pyramid", True, False),
        ("surface area of a sphere with radius 3", "sphere", False, True),
    ],
)
def test_extract_solid_intent(text: str, shape: str, volume_asked: bool, sa_asked: bool) -> None:
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "solid"
    assert intent.solid_shape == shape
    assert intent.wants_volume is volume_asked
    assert intent.wants_surface_area is sa_asked


def test_rectangular_prism_does_not_become_2d_rectangle() -> None:
    intent = math_tools.extract_math_intent("volume of a rectangular prism 3 by 4 by 5")
    assert intent is not None
    assert intent.kind == "solid"
    assert intent.solid_shape == "rectangular_prism"


@pytest.mark.parametrize(
    "text",
    [
        "cube root of 8",
        "solve the cubic equation",
        "what is the cube of 7",
    ],
)
def test_algebraic_cube_is_not_a_solid(text: str) -> None:
    intent = math_tools.extract_math_intent(text)
    assert intent is None or intent.kind != "solid"


def test_convert_atmosphere_is_unit_not_sphere() -> None:
    intent = math_tools.extract_math_intent("convert 1 atmosphere to psi")
    assert intent is not None
    assert intent.kind == "unit"
    assert intent.unit_from is not None
    assert "atmosphere" in intent.unit_from.lower()
    block = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert "Solid (sphere)" not in block.text
    assert "Equation:" not in block.text


def test_silicone_is_not_a_cone_solid() -> None:
    intent = math_tools.extract_math_intent("how much silicone")
    assert intent is None or intent.kind != "solid"


def test_verified_block_cube_volume() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("volume of a cube with side 5 cm")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer == r"125\ \mathrm{cm}^{3}"
    assert "```answer\n" not in block.text
    assert block.canonical_answer is not None
    assert block.canonical_fence is not None
    assert block.canonical_fence["type"] == "answer"


def test_verified_block_prism_volume() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("volume of a rectangular prism 3 by 4 by 5")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer == r"60\ \mathrm{units}^{3}"


def test_verified_block_prism_volume_sentence_period() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("Volume of a rectangular prism 3 by 4 by 5.")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer == r"60\ \mathrm{units}^{3}"


def test_verified_block_integral_of_2x_sentence_period() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("What is the integral of 2x.")
    assert intent is not None
    assert intent.kind == "calculus"
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    compact = block.canonical_answer.replace(" ", "")
    assert "x^{2}" in compact or "x^2" in compact


def test_verified_block_force_accelerated_phrasing() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = extract_physics_intent("A 5 kg mass is accelerated at 2 m/s^2. What is the force.")
    assert intent is not None
    assert intent.kind == "force"
    block = build_verified_physics_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    assert "10" in block.canonical_answer


@pytest.mark.parametrize(
    "text",
    [
        "A 5 kg mass is accelerated at 2 m/s². What is the force.",
        r"A 5 kg mass is accelerated at 2 m/s^{2}. What is the force.",
        r"A 5 kg mass is accelerated at $2$ m/s^{2}. What is the force.",
        r"A 5 kg mass is accelerated at 2 m/s$^2$$^2.$^2. What is the force.",
    ],
)
def test_verified_block_force_math_keyboard_units(text: str) -> None:
    """Unicode / LaTeX s² from the math keyboard used to miss extract, then
    the bubble still said Couldn't verify this with SymPy."""
    settings = Settings(math_tools_enabled=True)
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.kind == "force"
    assert intent.physics_params is not None
    assert intent.physics_params["a"] == 2.0
    block = build_verified_physics_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    assert "10" in block.canonical_answer


@pytest.mark.parametrize(
    "text, kind",
    [
        ("what is 1+1", "arithmetic"),
        ("7*8", "arithmetic"),
        ("3*4+2", "arithmetic"),
        ("what is 7*8", "arithmetic"),
        ("7*8", "arithmetic"),
        ("8-8*2", "arithmetic"),
        ("what is 15% of 80", "arithmetic"),
        ("increase 200 by 12%", "arithmetic"),
        ("what percent of 50 is 12", "arithmetic"),
        ("split 120 in the ratio 2:3", "arithmetic"),
        ("10th term of 3, 7, 11, 15", "arithmetic"),
        ("compound interest on 1000 at 5% for 3 years", "arithmetic"),
        ("union of {1,2,3} and {3,4}", "arithmetic"),
        ("simplify the ratio 6:8", "arithmetic"),
        ("sin 30", "trig"),
        ("What is sin of 30 degrees.", "trig"),
        ("sine of 30 degrees", "trig"),
        ("distance between (0,0) and (3,4)", "coord"),
        ("midpoint of (0,0) and (4,6)", "coord"),
        ("magnitude of <3,4>", "vector"),
        ("dot product of <1,2> and <3,4>", "vector"),
        ("binomial n=5 k=2 p=0.5", "probability"),
        ("convert 5 ft to m", "unit"),
        ("taylor of sin(x) at 0 order 3", "calculus"),
    ],
)
def test_extract_school_homework_kinds(text: str, kind: str) -> None:
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == kind


@pytest.mark.parametrize(
    "text, gated, kind",
    [
        ("8-8*2", True, "arithmetic"),
        ("7*8", True, "arithmetic"),
        ("what is 9/9", True, "arithmetic"),
        ("10-3-2", True, "arithmetic"),
        ("100/5/2", True, "arithmetic"),
        ("9/9", False, None),
        ("9/9", False, None),
        ("10-3", True, "arithmetic"),
        ("555-1234", False, None),
        ("8x5", False, None),
        ("8 by 5", False, None),
        ("A rectangle is 8×5 cm. Find the diagonal angle.", True, "rectangle"),
    ],
)
def test_gate_and_extractor_agree_on_bare_arithmetic(
    text: str, gated: bool, kind: str | None
) -> None:
    """``8-8*2`` used to gate via first_dim_pair then fail extract → disclaimer."""
    assert math_tools.needs_symbolic_math(text) is gated
    intent = math_tools.extract_math_intent(text)
    if kind is None:
        assert intent is None
    else:
        assert intent is not None
        assert intent.kind == kind


def test_bare_arithmetic_verifies_pemdas() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("8-8*2")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    compact = block.canonical_answer.replace(" ", "")
    assert "-8" in compact
    times = math_tools.extract_math_intent("7*8")
    assert times is not None
    tblock = math_tools._build_verified_block(times, settings)
    assert tblock is not None
    assert tblock.canonical_answer is not None
    assert "56" in tblock.canonical_answer.replace(" ", "")


def test_verified_percent_and_distance() -> None:
    settings = Settings(math_tools_enabled=True)
    percent = math_tools.extract_math_intent("what is 15% of 80")
    assert percent is not None
    block = math_tools._build_verified_block(percent, settings)
    assert block is not None
    assert block.canonical_answer == "12"
    dist = math_tools.extract_math_intent("distance between (0,0) and (3,4)")
    assert dist is not None
    dblock = math_tools._build_verified_block(dist, settings)
    assert dblock is not None
    assert dblock.canonical_answer == "5"


def test_verified_trig_sin_of_degrees() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("What is sin of 30 degrees.")
    assert intent is not None
    assert intent.kind == "trig"
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    answer = block.canonical_answer
    assert answer is not None
    assert "1}{2" in answer or "1/2" in answer


@pytest.mark.parametrize(
    "text, expected_expr",
    [
        ("graph x^2 please", "x**2"),
        ("graph x^2 for me", "x**2"),
        ("plot sin(x) and explain it", "sin(x)"),
        ("can you graph x^2 now", "x**2"),
        # The composer/math keyboard wraps the expression in $...$ and can
        # emit a base-less superscript chain for "x²" — without stripping
        # the delimiters and folding ^{x}^{2} → x^{2} → x^2, SymPy's safe-char
        # gate rejects $/{/} and the turn ships with no verified fence.
        ("Graph $x^2$", "x**2"),
        ("Graph $^{x}^{2}$", "x**2"),
        ("Graph y =Graph y = x^2.", "x**2"),
        ("Graph y =Graph y = x².", "x**2"),
        (r"Graph y =Graph y = $x^{2}$.", "x**2"),
        (r"Graph y =Graph y$= x^$$= x^2.$", "x**2"),
        ("Graph y = Graph y = x^2", "x**2"),
        ("graph this: graph y=x^2", "x**2"),
        ("graph theory then graph y=x^2", "x**2"),
        ("draw y=x^2", "x**2"),
        ("sketch y = x^2", "x**2"),
        ("visualize y=x^2", "x**2"),
        ("chart y=x^2", "x**2"),
        ("what does y=x^2 look like", "x**2"),
        ("show the shape of y=x^2", "x**2"),
        ("Graph y =Graph y= x= x².", "x**2"),
    ],
)
def test_extract_graph_intent_strips_trailing_prose(text: str, expected_expr: str) -> None:
    """BUG FIX regression: the graph-expr capture is greedy, so natural
    phrasing ('graph x^2 please') used to sweep trailing conversational
    words into the "expression" — which then failed to parse in SymPy and
    silently disabled the verified-graph augmentation entirely."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "graph"
    assert intent.expr == expected_expr


def test_garbled_graph_ask_does_not_become_equation() -> None:
    """English leftover after a graph cue must stay kind=graph (honesty note),
    not fall through to the equation solver as a fabricated verified solve."""
    settings = Settings(math_tools_enabled=True)
    text = "graph x = the reason I am late"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "graph"
    assert not intent.expr
    assert intent.lhs is None
    block = math_tools._build_verified_block(intent, settings)
    assert block is None


def test_unverified_graph_note_bans_table_and_mermaid_substitute() -> None:
    from app.modules.math.reply_policy import GRAPH_NO_SUBSTITUTE_CLAUSE
    from app.modules.math.tools.prompt import _unverified_math_note

    note = _unverified_math_note("graph")
    assert GRAPH_NO_SUBSTITUTE_CLAUSE in note
    assert "Do NOT emit ```answer, ```geometry, or ```graph" in note


def test_verified_block_graph_duplicated_graph_y_prefix() -> None:
    """Screen prompt ``Graph y =Graph y = x².`` used to sample
    x**2/(G*a*h*p*r), fail, and ship a point table + ASCII sketch."""
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("Graph y =Graph y = x².")
    assert intent is not None
    assert intent.kind == "graph"
    assert intent.expr == "x**2"
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_fence is not None
    assert block.canonical_fence.get("type") == "function"
    pts = block.canonical_fence.get("points")
    assert isinstance(pts, list) and len(pts) > 10


def test_verified_block_graph_keypad_dollar_equals() -> None:
    """On-screen ``Graph y =Graph y$= x^$$= x^2.$`` used to miss extract,
    stamp Couldn't verify, and ship a Mermaid flowchart of points."""
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent(r"Graph y =Graph y$= x^$$= x^2.$")
    assert intent is not None
    assert intent.kind == "graph"
    assert intent.expr == "x**2"
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_fence is not None
    assert block.canonical_fence.get("type") == "function"
    pts = block.canonical_fence.get("points")
    assert isinstance(pts, list) and len(pts) > 10


@pytest.mark.parametrize(
    "text, expected_expr",
    [
        ("graph x=2y", "x/2"),
        ("Graph x = 2y.", "x/2"),
        ("plot x = 2*y", "x/2"),
        ("graph x=-3y", "-x/3"),
        ("graph 2x=y", "2*x"),
    ],
)
def test_extract_graph_intent_solves_equation_for_y(text: str, expected_expr: str) -> None:
    """BUG FIX regression: 'graph x=2y' is an equation, not a function
    expression. sample_function used to receive 'x=2y' (an Equality) and
    reject it, so no verified graph was emitted and the model emitted its
    own (often wrong) spec. The extractor now solves for y as y = f(x)."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "graph"
    assert intent.expr == expected_expr


@pytest.mark.parametrize(
    "text",
    [
        "graph 4x^2-5x-12=0",
        "Graph 4x^2 - 5x - 12 = 0",
        "plot 4x²-5x-12=0",
        "graph 0=4x^2-5x-12",
    ],
)
def test_extract_graph_intent_plots_equation_as_function_of_x(text: str) -> None:
    """``graph 4x^2-5x-12=0`` is not y=f(x); sample_function rejected the
    Equality and stamped Couldn't verify. Plot lhs-rhs (the parabola)."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "graph"
    assert "=" not in (intent.expr or "")
    settings = Settings(math_tools_enabled=True)
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_fence is not None
    assert block.canonical_fence.get("type") == "function"
    pts = block.canonical_fence.get("points")
    assert isinstance(pts, list) and len(pts) > 10
    x, y = pts[len(pts) // 2]
    assert abs(y - (4.0 * x * x - 5.0 * x - 12.0)) < 1e-3


def test_extract_graph_circle_relation_not_rewritten_as_fx() -> None:
    intent = math_tools.extract_math_intent("graph x^2+y^2=1")
    assert intent is not None
    assert intent.kind == "graph"
    assert "=" in (intent.expr or "")


def test_bare_quadratic_equation_stays_solve() -> None:
    intent = math_tools.extract_math_intent("4x^2-5x-12=0")
    assert intent is not None
    assert intent.kind == "equation"


@pytest.mark.asyncio
async def test_graph_it_uses_prior_quadratic_equation() -> None:
    settings = Settings(math_tools_enabled=True)
    note, verified = await math_tools.build_math_augmentation(
        "graph it",
        settings,
        prior_user_messages=["4x^2-5x-12=0"],
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence.get("type") == "function"
    pts = verified.canonical_fence.get("points")
    assert isinstance(pts, list) and len(pts) > 10
    x, y = pts[len(pts) // 2]
    assert abs(y - (4.0 * x * x - 5.0 * x - 12.0)) < 1e-3
    assert note is not None
    assert "Couldn't verify" not in note


@pytest.mark.asyncio
async def test_graph_it_without_prior_does_not_stamp_unverified() -> None:
    """It asks which function to graph instead of letting the model sketch one."""

    note, verified = await math_tools.build_math_augmentation(
        "graph it",
        Settings(math_tools_enabled=True),
    )
    assert note is NOTHING_TO_GRAPH
    assert "verif" not in note.lower()
    assert verified is None


def test_graph_and_solve_does_not_become_vertical_line() -> None:
    """A graph plus a second solve is atomic and must not verify either half."""
    text = "graph y=x**2 and also solve 3x=9"
    assert math_tools.extract_math_intent(text) is None


@pytest.mark.parametrize(
    "text, expected_expr",
    [
        ("y=3x+4", "3x+4"),
        ("$y=3x+4$", "3x+4"),
        ("y=x^2", "x**2"),
    ],
)
def test_extract_graph_intent_bare_y_equals(text: str, expected_expr: str) -> None:
    """A slope-intercept / function-form message with no 'graph'/'plot'
    still extracts as a graph so the verified sample fence reaches the
    rewriter. Otherwise the model emits an empty-points ```graph and the
    user sees 'Could not render that diagram.'"""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "graph"
    assert intent.expr == expected_expr


def test_extract_bare_y_equals_stays_equation_when_solving() -> None:
    intent = math_tools.extract_math_intent("solve y=3x+4")
    assert intent is not None
    assert intent.kind == "equation"


@pytest.mark.asyncio
async def test_augment_bare_y_equals_injects_graph_fence() -> None:
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "$y=3x+4$"}],
        "$y=3x+4$",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "function"
    points = verified.canonical_fence["points"]
    assert len(points) >= 2
    x0, y0 = points[len(points) // 2]
    assert abs(y0 - (3.0 * x0 + 4.0)) < 1e-4


@pytest.mark.parametrize(
    "text, expected_expr",
    [
        ("differentiate x^2 please", "x^2"),
        ("integrate x^2 for me", "x^2"),
        ("What is the integral of 2x.", "2x"),
        ("simplify x^2 + 2x + x^2 now", "x^2 + 2x + x^2"),
    ],
)
def test_extract_calculus_intent_strips_trailing_prose(text: str, expected_expr: str) -> None:
    """Same bug as the graph case, for the calculus expr-match capture."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.expr == expected_expr


@pytest.mark.parametrize(
    "text, expected_op",
    [
        ("factor x^2 - 1", "factor"),
        ("expand (x-1)(x+1)", "expand"),
        ("Factor the polynomial x^3 - 1", "factor"),
        ("factor x^2-5x+6=0", "factor"),
        ("expand (x+1)^2=x^2+2x+1", "expand"),
    ],
)
def test_extract_factor_expand_intent(text: str, expected_op: str) -> None:
    """BUG FIX regression: factor/expand were in _MATH_KEYWORDS (so they
    enabled the math path) but had no intent branch — a silent no-op. They
    now route to a calculus factor/expand operation."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.operation == expected_op
    assert intent.expr


def test_calculus_without_sympy_steps_asks_model_to_derive() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("factor x^2 - 1")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    assert "x" in block.canonical_answer


def test_differentiate_block_copies_verified_steps() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("differentiate x^3 + 5")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert "Sum rule" in block.text or "Power rule" in block.text


def test_extract_definite_integral_bounds() -> None:
    """'integrate x^2 from 0 to 1' parses bounds and strips them from expr."""
    intent = math_tools.extract_math_intent("integrate x^2 from 0 to 1")
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.operation == "integrate"
    assert intent.expr == "x^2"
    assert intent.integral_lower == "0"
    assert intent.integral_upper == "1"


def test_extract_indefinite_integral_has_no_bounds() -> None:
    intent = math_tools.extract_math_intent("integrate x^2")
    assert intent is not None
    assert intent.operation == "integrate"
    assert intent.integral_lower is None
    assert intent.integral_upper is None


@pytest.mark.parametrize(
    "text, expected_expr",
    [
        ("Integrate x squared", "x^2"),
        ("integrate x cubed", "x^3"),
        ("What is the integral of x squared.", "x^2"),
        ("differentiate x squared", "x^2"),
    ],
)
def test_extract_english_squared_cubed(text: str, expected_expr: str) -> None:
    """Speech / typed 'x squared' used to miss extract, then stamp unverified."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.expr == expected_expr


def test_verified_integrate_x_squared_english() -> None:
    settings = Settings(math_tools_enabled=True)
    intent = math_tools.extract_math_intent("Integrate x squared")
    assert intent is not None
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    compact = block.canonical_answer.replace(" ", "")
    assert "x^{3}" in compact or "x^3" in compact
    assert "3" in compact


def test_english_area_squared_does_not_become_are_caret() -> None:
    """Rewrite only 1-letter / digit bases — not the word 'area'."""
    assert math_tools.extract_math_intent("integrate area squared") is None


@pytest.mark.parametrize(
    "text, expected_cmp",
    [
        ("solve x**2 - 1 > 0", ">"),
        ("solve x \\leq 5", "<="),
        ("solve 2x + 1 < 7", "<"),
    ],
)
def test_extract_inequality_intent(text: str, expected_cmp: str) -> None:
    """Inequalities route to a dedicated intent kind with the canonical
    comparator. Safe from prose false-positives because extract_math_intent
    is only called when a math keyword already matched."""
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "inequality"
    assert intent.comparator == expected_cmp
    assert intent.lhs and intent.rhs


def test_extract_compound_inequality_intent() -> None:
    intent = math_tools.extract_math_intent("solve 1 < x < 5")
    assert intent is not None
    assert intent.kind == "inequality"
    assert intent.lower == "1"
    assert intent.lhs == "x"
    assert intent.rhs == "5"
    assert intent.comparator == "<"
    assert intent.comparator_upper == "<"


def test_extract_abs_inequality_intent() -> None:
    intent = math_tools.extract_math_intent("solve |x-2| < 5")
    assert intent is not None
    assert intent.kind == "inequality"
    assert intent.lhs == "Abs(x-2)"
    assert intent.rhs == "5"
    assert intent.comparator == "<"


@pytest.mark.parametrize(
    "text, expected_expr, expected_var, expected_point",
    [
        ("find the limit of x^2 as x approaches 3", "x**2", "x", "3"),
        ("limit of sin(x)/x as x approaches 0", "sin(x)/x", "x", "0"),
        ("what is the limit of 1/x as x approaches infinity", "1/x", "x", "infinity"),
        ("evaluate the limit of (x^2-1)/(x-1) as x -> 1", "(x**2-1)/(x-1)", "x", "1"),
        ("lim x->0 sin(x)/x", "sin(x)/x", "x", "0"),
        (r"\lim_{x \to 0} \sin(x)/x", "sin(x)/x", "x", "0"),
    ],
)
def test_extract_limit_intent(
    text: str, expected_expr: str, expected_var: str, expected_point: str
) -> None:
    assert math_tools.needs_symbolic_math(text) is True
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "limit"
    assert intent.expr == expected_expr
    assert intent.variable == expected_var
    assert intent.limit_point == expected_point


def test_limit_regex_does_not_misfire_on_unrelated_approaches_prose() -> None:
    """The word "approaches" alone (without "limit"/"lim") must not trigger
    symbolic math — e.g. "the deadline as it approaches Friday" is not math."""
    assert math_tools.needs_symbolic_math("the deadline as it approaches Friday") is False


@pytest.mark.parametrize(
    "text, expected_expr, expected_var, expected_start, expected_end",
    [
        (
            "does the series sum of 1/n^2 from n=1 to infinity converge",
            "1/n**2",
            "n",
            "1",
            "infinity",
        ),
        ("evaluate the sum of 1/2^n from n=0 to infinity", "1/2**n", "n", "0", "infinity"),
        ("sum of n from n=1 to 10", "n", "n", "1", "10"),
        (r"\sum_{n=1}^{\infty} 1/n^2", "1/n**2", "n", "1", "infty"),
    ],
)
def test_extract_series_intent(
    text: str, expected_expr: str, expected_var: str, expected_start: str, expected_end: str
) -> None:
    assert math_tools.needs_symbolic_math(text) is True
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "series"
    assert intent.expr == expected_expr
    assert intent.variable == expected_var
    assert intent.series_start == expected_start
    assert intent.series_end == expected_end


@pytest.mark.asyncio
async def test_augment_prompt_injects_limit_block() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "find the limit of x^2 as x approaches 3"
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "Result: 9" in verified.text
    assert any("Result: 9" in m["content"] for m in out if m["role"] == "system")
    assert verified.canonical_fence == {"type": "answer", "content": "9"}
    assert "```answer\n" not in verified.text
    assert verified.canonical_answer is not None


@pytest.mark.asyncio
async def test_augment_prompt_calculus_attaches_answer_fence() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "differentiate x^2"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "answer"
    assert "2" in verified.canonical_fence["content"]
    assert "```answer\n" not in verified.text
    assert verified.canonical_answer is not None


@pytest.mark.asyncio
async def test_english_calculus_verifies_via_llm_extract_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Was: English calculus the regex can't parse stayed unverified. The LLM
    extraction fallback (gate-fired + regex-None) now closes it — SymPy still
    does the actual math."""
    from app.gateways import litellm_gateway
    from app.modules.math.tools.llm_extract import LLMMathExtract

    async def fake_extract(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(
            found=True, kind="calculus", operation="differentiate", expr="x^2 + 3*x"
        )

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_extract)
    settings = Settings(math_tools_enabled=True)
    text = "what's the derivative of x squared plus 3x"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert verified.canonical_answer is not None
    compact = verified.canonical_answer.replace(" ", "")
    assert "2*x" in compact or "2x" in compact


@pytest.mark.asyncio
async def test_english_calculus_verifies_without_the_llm_extract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.gateways import litellm_gateway
    from app.modules.math.tools.llm_extract import LLMMathExtract

    async def fake_extract(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(found=False)

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake_extract)
    settings = Settings(math_tools_enabled=True)
    text = "what's the derivative of x squared plus 3x"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None and verified.canonical_answer == "2 x + 3"


@pytest.mark.asyncio
async def test_ddx_calculus_still_produces_verified_block() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "d/dx x**2 + 3x"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert verified.canonical_answer is not None
    compact = verified.canonical_answer.replace(" ", "")
    assert "2*x" in compact or "2x" in compact


@pytest.mark.asyncio
async def test_english_roots_does_not_produce_verified_block() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "roots of my hair are 2 inches long"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is None


@pytest.mark.asyncio
async def test_augment_prompt_calculus_includes_derivation_steps() -> None:
    """BUG FIX (MATH-BE-026): differentiation used to ship only the final
    result with no worked derivation, so the model invented its own (often
    wrong) steps. Now SymPy-verified per-term derivation steps (rule-named)
    are injected so the model can follow verified steps."""
    settings = Settings(math_tools_enabled=True)
    text = "differentiate x^3 + 2x"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    # Sum rule line + per-term power-rule lines + result line.
    assert "Sum rule" in verified.text
    assert "Power rule" in verified.text
    assert "Result:" in verified.text


def test_differentiate_expression_steps_name_rules() -> None:
    """Unit-level check: the differentiation steps name the rule applied to
    each term and carry the SymPy-verified derivative."""
    from app.modules.math import solve as math_solve

    out = math_solve.differentiate_expression("x^3 + 5", "x")
    assert out.solved
    assert any("Sum rule" in s for s in out.steps)
    assert any("Power rule" in s and "3" in s for s in out.steps)
    assert any("Constant rule" in s for s in out.steps)
    assert out.steps[-1].startswith("Result:")
    # The verified derivative of x^3 + 5 is 3*x^2.
    assert "3" in out.result and "x" in out.result


def test_first_derivative_phrasing_stays_order_one() -> None:
    intent = math_tools.extract_math_intent("find the derivative of sin(x)cos(x)")
    assert intent is not None
    assert intent.operation == "differentiate"
    assert intent.derivative_order == 1


def test_second_derivative_is_not_the_first() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "find the second derivative of x^4 - 3x^2"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.operation == "differentiate"
    assert intent.derivative_order == 2
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    # f' = 4x^3 - 6x; f'' = 12x^2 - 6 (possibly factored). Must not ship f'.
    assert "x^{3}" not in block.canonical_answer
    assert "2 x^{2}" in block.canonical_answer or "12" in block.canonical_answer


def test_second_derivative_of_y_equals_polynomial_verifies() -> None:
    """``y = x^3 - 3x`` used to fail extract, then stamp Couldn't verify."""
    settings = Settings(math_tools_enabled=True)
    text = "Find the second derivative of y = x^3 - 3x"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.operation == "differentiate"
    assert intent.derivative_order == 2
    assert "=" not in (intent.expr or "")
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    compact = block.canonical_answer.replace(" ", "")
    assert "6x" in compact or "6 x" in block.canonical_answer


def test_dydx_if_y_equals_differentiates_the_rhs() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "Find dy/dx if y = x^3 - 3x"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.operation == "differentiate"
    assert intent.derivative_order == 1
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    compact = block.canonical_answer.replace(" ", "")
    assert "3x^2" in compact or "3x^{2}" in compact or "3 x^{2}" in block.canonical_answer


def test_dsolve_first_order_separable() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "solve the differential equation dy/dx = y"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.operation == "dsolve"
    assert intent.expr is not None
    assert intent.expr.lower().startswith("dy/dx")
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    low = block.canonical_answer.lower()
    assert "e" in low or "exp" in low or "c" in low


def test_critical_points_are_not_a_fake_equation_solve() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "find the critical points of f(x) = x^3 - 3x"
    intent = math_tools.extract_math_intent(text)
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.operation == "critical_points"
    block = math_tools._build_verified_block(intent, settings)
    assert block is not None
    assert block.canonical_answer is not None
    assert "re(" not in block.canonical_answer
    assert "1" in block.canonical_answer and "-1" in block.canonical_answer


def test_maclaurin_aliases_taylor_at_zero() -> None:
    intent = math_tools.extract_math_intent("maclaurin series of e^x")
    assert intent is not None
    assert intent.operation == "taylor"
    assert intent.limit_point == "0"


@pytest.mark.asyncio
async def test_augment_prompt_unsolved_integral_has_no_answer_fence() -> None:
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "integrate x**x"}], "integrate x**x", settings
    )
    assert verified is not None
    assert verified.canonical_fence is None
    assert "```answer" not in verified.text


@pytest.mark.asyncio
async def test_augment_prompt_distinguishes_nonexistent_two_sided_limit() -> None:
    """Opposite one-sided infinities are not a positive-infinity answer."""
    settings = Settings(math_tools_enabled=True)
    text = "what is the limit of 1/x as x approaches 0"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "does not exist" in verified.text.lower()
    assert verified.canonical_answer is None


@pytest.mark.asyncio
async def test_augment_prompt_injects_series_block_with_convergence() -> None:
    settings = Settings(math_tools_enabled=True)
    text = r"\sum_{n=1}^{\infty} 1/n^2"
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "Convergent: True" in verified.text
    assert any("Convergent: True" in m["content"] for m in out if m["role"] == "system")


@pytest.mark.asyncio
async def test_augment_prompt_flags_divergent_series() -> None:
    """BUG FIX target: the harmonic series (sum 1/n) diverges — the model
    must be told it diverges/is infinite, not shown a plausible finite
    number it would otherwise be tempted to invent."""
    settings = Settings(math_tools_enabled=True)
    text = "does the series sum of 1/n from n=1 to infinity converge"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert "Convergent: False" in verified.text
    assert "diverges" in verified.text.lower()


@pytest.mark.asyncio
async def test_augment_prompt_injects_geometry_block() -> None:
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "rectangle 8 x 5 cm diagonal angle"}]
    out, verified = await augment_prompt_messages(
        messages,
        "rectangle 8 x 5 cm diagonal angle",
        settings,
    )
    assert len(out) == 2
    assert "```geometry\n" not in out[0]["content"]
    assert "diagonal" in out[0]["content"]
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "rectangle"


@pytest.mark.asyncio
async def test_augment_prompt_rectangle_area_query_does_not_force_diagonal_and_angle() -> None:
    """BUG FIX regression: the rectangle geometry block always set
    show_diagonal=True, show_angle=True regardless of what was asked, so a
    plain "rectangle area 4 by 5" query drew an unrequested diagonal plus a
    diagonal-vs-base angle that visually contradicted the rectangle's own
    (always 90°) corner. The diagram should only annotate what was asked."""
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "What about rectangle area with 4 by 5"}]
    _out, verified = await augment_prompt_messages(
        messages,
        "What about rectangle area with 4 by 5",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["show_diagonal"] is False
    assert verified.canonical_fence["show_angle"] is False
    assert verified.canonical_fence["show_area"] is True
    assert verified.canonical_fence["show_perimeter"] is False
    assert verified.canonical_answer == "20"


@pytest.mark.asyncio
async def test_augment_prompt_injects_circle_geometry_block() -> None:
    """BUG FIX regression: circles were never a supported geometry kind
    anywhere in the pipeline — the model's own improvised ```geometry
    {"type":"circle",...} fence had no SymPy-verified values and no schema
    to validate against. Now a direct "circle radius 4" gets the same
    verified-computation treatment as every other shape."""
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "circle radius 4 area circumference"}]
    out, verified = await augment_prompt_messages(
        messages,
        "circle radius 4 area circumference",
        settings,
    )
    assert len(out) == 2
    assert "```geometry\n" not in out[0]["content"]
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "circle"
    assert verified.canonical_fence["show_area"] is True
    assert verified.canonical_fence["show_circumference"] is True


@pytest.mark.asyncio
async def test_augment_circle_circumference_answer_not_area() -> None:
    """BUG FIX: 'circumference of circle r=4' used to return the area
    (≈50.27) as the verified final answer because the canonical answer was
    unconditionally the area. Now an explicit circumference request yields
    the circumference (≈25.13)."""
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "circumference of circle radius 4"}]
    _out, verified = await augment_prompt_messages(
        messages,
        "circumference of circle radius 4",
        settings,
    )
    assert verified is not None
    assert verified.canonical_answer is not None
    assert abs(float(verified.canonical_answer) - 25.13) < 0.01


@pytest.mark.asyncio
async def test_augment_circle_area_answer_when_only_area_requested() -> None:
    """'area of circle r=4' (no circumference) still returns the area as the
    verified final answer — the circumference fix must not regress the
    default area path."""
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "area of circle radius 4"}]
    _out, verified = await augment_prompt_messages(
        messages,
        "area of circle radius 4",
        settings,
    )
    assert verified is not None
    assert verified.canonical_answer is not None
    assert abs(float(verified.canonical_answer) - 50.27) < 0.01


@pytest.mark.asyncio
async def test_augment_stats_sample_stdev_uses_sample_divisor() -> None:
    """BUG FIX: 'sample standard deviation of {1,2,3,4,5}' used to return the
    population stdev because the only 'stdev' op mapped to population_stdev.
    Now 'sample …' maps to the (n-1) sample stdev."""
    import statistics as _stats

    settings = Settings(math_tools_enabled=True)
    data = [1, 2, 3, 4, 5]
    content = "sample standard deviation of 1, 2, 3, 4, 5"
    messages = [{"role": "user", "content": content}]
    _out, verified = await augment_prompt_messages(messages, content, settings)
    assert verified is not None
    assert verified.canonical_answer is not None
    expected = f"{_stats.stdev(data):.4f}"
    assert verified.canonical_answer == expected
    # Sanity: sample stdev must differ from population stdev here.
    assert expected != f"{_stats.pstdev(data):.4f}"


@pytest.mark.asyncio
async def test_augment_stats_population_stdev_still_default() -> None:
    """Bare 'standard deviation of …' (no sample/population qualifier) keeps
    the historical population-stdev default — the sample fix must not change
    the default interpretation."""
    import statistics as _stats

    settings = Settings(math_tools_enabled=True)
    data = [1, 2, 3, 4, 5]
    content = "standard deviation of 1, 2, 3, 4, 5"
    messages = [{"role": "user", "content": content}]
    _out, verified = await augment_prompt_messages(messages, content, settings)
    assert verified is not None
    assert verified.canonical_answer is not None
    assert verified.canonical_answer == f"{_stats.pstdev(data):.4f}"


@pytest.mark.asyncio
async def test_augment_prompt_injects_single_point_graph_block() -> None:
    """BUG FIX regression: a bare "(2,3)" reply (e.g. answering "what
    point?") had no augmentation at all, so the model was free to invent
    an unrequested line through the point instead of just marking it.
    Now it gets a verified single-point ```graph fence with an explicit
    instruction not to invent a function through it."""
    settings = Settings(math_tools_enabled=True)
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "(2,3)"}],
        "(2,3)",
        settings,
    )
    assert len(out) == 2
    assert "```graph\n" not in out[0]["content"]
    assert VERIFIED_MATH_BEGIN in out[0]["content"]
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["points"] == [[2.0, 3.0]]


@pytest.mark.asyncio
async def test_augment_prompt_injects_graph_block() -> None:
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "Graph y = x^2"}]
    out, verified = await augment_prompt_messages(messages, "Graph y = x^2", settings)
    assert len(out) == 2
    assert "```graph\n" not in out[0]["content"]
    assert "points" in out[0]["content"]
    assert VERIFIED_MATH_BEGIN in out[0]["content"]
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "function"


@pytest.mark.asyncio
async def test_augment_graph_uses_user_named_domain() -> None:
    """BUG FIX: 'graph y=x^2 from 0 to 100' used to sample on the [-10, 10]
    default window. Now the user-named domain drives the verified sample so
    the rendered curve spans the requested range."""
    settings = Settings(math_tools_enabled=True)
    text = "graph y = x^2 from 0 to 100"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    pts = verified.canonical_fence["points"]
    xs = [p[0] for p in pts]
    assert min(xs) >= 0
    assert max(xs) <= 100
    assert verified.canonical_fence["domain_explicit"] is True


@pytest.mark.parametrize(
    "expr, expected_lo, expected_hi, expected_clean",
    [
        ("y=x^2 from 0 to 100", 0.0, 100.0, "y=x^2"),
        ("x^2 between -2 and 3", -2.0, 3.0, "x^2"),
        ("sin(x) on [-5, 5]", -5.0, 5.0, "sin(x)"),
        ("y=x^2 from -pi to pi", -3.14159265, 3.14159265, "y=x^2"),
        ("y=x^2 from 0 to 2pi", 0.0, 6.2831853, "y=x^2"),
    ],
)
def test_graph_domain_parses_user_window(
    expr: str, expected_lo: float, expected_hi: float, expected_clean: str
) -> None:
    from app.modules.math import match as mtm

    out = mtm.graph_domain(expr)
    assert out is not None
    lo, hi, cleaned = out
    assert abs(lo - expected_lo) < 1e-4
    assert abs(hi - expected_hi) < 1e-4
    assert cleaned == expected_clean


def test_graph_domain_none_when_no_clause() -> None:
    from app.modules.math import match as mtm

    assert mtm.graph_domain("y = x^2") is None
    # Reversed bounds are invalid — fall back to default rather than misplot.
    assert mtm.graph_domain("y=x^2 from 100 to 0") is None


@pytest.mark.asyncio
async def test_augment_prompt_injects_unit_circle_relation_graph() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "graph x^2 + y^2 = 1"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "function"
    pts = verified.canonical_fence["points"]
    assert len(pts) >= 16
    assert pts[0] == pts[-1]  # closed curve
    assert "parametric" in verified.text.lower() or "relation" in verified.text.lower()


@pytest.mark.asyncio
async def test_augment_prompt_injects_ellipse_relation_graph() -> None:
    settings = Settings(math_tools_enabled=True)
    text = "plot x^2/9 + y^2/4 = 1"
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": text}], text, settings
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    xs = [p[0] for p in verified.canonical_fence["points"]]
    ys = [p[1] for p in verified.canonical_fence["points"]]
    assert max(xs) == pytest.approx(3.0, abs=0.05)
    assert max(ys) == pytest.approx(2.0, abs=0.05)


@pytest.mark.asyncio
async def test_augment_prompt_attaches_segments_and_warns_on_discontinuous_graph() -> None:
    """BUG FIX (verified live): tan(x) over the default range drew a
    near-straight line across the pi/2 asymptote. The canonical fence must
    carry the split segments, and the model must be told not to describe it
    as one continuous curve."""
    settings = Settings(math_tools_enabled=True)
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "Graph tan(x)"}], "Graph tan(x)", settings
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert len(verified.canonical_fence["segments"]) == 7
    assert "discontinuity" in verified.text.lower()
    assert any("discontinuity" in m["content"].lower() for m in out if m["role"] == "system")


@pytest.mark.asyncio
async def test_augment_prompt_omits_segments_for_a_continuous_graph() -> None:
    """The overwhelmingly common case (no discontinuity) must not carry a
    redundant segments field duplicating every point."""
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "Graph x^2"}], "Graph x^2", settings
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["segments"] == []
    assert "discontinuity" not in verified.text.lower()


@pytest.mark.asyncio
async def test_augment_prompt_flags_unsolved_integral_instead_of_asserting_it() -> None:
    """BUG FIX: integrate_expression can hand back a result that still
    contains a literal unevaluated Integral(...) instead of raising, and this
    used to be injected as "Result: ... Do NOT recompute" — the exact same
    verified-confidence phrasing used for a real closed-form answer. The
    model must be told SymPy found no closed form instead."""
    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "integrate x**x"}]
    out, verified = await augment_prompt_messages(messages, "integrate x**x", settings)
    assert verified is not None
    assert "Do NOT recompute" not in verified.text
    assert "closed-form" in verified.text.lower() or "no closed form" in verified.text.lower()
    assert any(
        "closed-form" in m["content"].lower() or "no closed form" in m["content"].lower()
        for m in out
        if m["role"] == "system"
    )


@pytest.mark.asyncio
async def test_vertical_line_graph_builds_canonical_fence() -> None:
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "Graph x = 4"}],
        "Graph x = 4",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "vertical"
    assert verified.canonical_fence["x"] == 4.0
    assert verified.canonical_answer is None
    # Sample window stays on the fence; don't give the model y=±10 to parrot.
    assert "from y" not in verified.text.lower()
    assert "y = -10" not in verified.text
    assert "Recall will attach" not in verified.text
    assert "Do not mention attaching" not in verified.text
    assert VERIFIED_MATH_BEGIN in verified.text
    assert verified.canonical_fence["x_min"] == 0.0
    assert verified.canonical_fence["x_max"] == 10.0
    assert verified.canonical_fence["y_min"] == -10.0
    assert verified.canonical_fence["y_max"] == 10.0


@pytest.mark.asyncio
async def test_glued_graph_command_injects_vertical_fence_not_chart() -> None:
    """``X=6graph`` is graph-the-line x=6 (```graph), not Vega ```chart."""
    settings = Settings(math_tools_enabled=True)
    out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "X=6graph"}],
        "X=6graph",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "vertical"
    assert verified.canonical_fence["x"] == 6.0
    assert verified.canonical_answer is None
    assert verified.canonical_fence["x_min"] == 0.0
    assert verified.canonical_fence["x_max"] == 12.0
    joined = " ".join(m["content"] for m in out)
    assert "```chart" not in joined
    assert '"type":"bar"' not in joined


@pytest.mark.asyncio
async def test_composer_dollar_wrap_injects_vertical_fence() -> None:
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "X=$6$graph"}],
        "X=$6$graph",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "vertical"
    assert verified.canonical_fence["x"] == 6.0
    import json

    from app.modules.math.fence import validate_math_fences

    prose = "$X = 6$ is a **vertical line** on the Cartesian plane.\n\n$X = 6$"
    out = validate_math_fences(prose, verified=verified)
    assert "```graph" in out
    assert json.loads(out.split("```graph")[1].split("```")[0].strip())["type"] == "vertical"


@pytest.mark.asyncio
async def test_graph_inequality_builds_number_line_fence() -> None:
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "graph x > 3"}],
        "graph x > 3",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "number_line"
    iv = verified.canonical_fence["intervals"][0]
    assert iv["start"] == 3.0
    assert iv["end"] is None
    assert iv["start_inclusive"] is False
    # The prompt describes the number-line rendering (no longer says "NOT a
    # 1D number line" — that contradicted the emitted type:"number_line").
    assert "number line" in verified.text.lower()


@pytest.mark.asyncio
async def test_bare_inequality_builds_number_line_fence() -> None:
    """BUG FIX regression: a bare inequality with no math keyword ("X>4")
    used to fail needs_symbolic (the gate required a keyword), so the
    inequality extractor never ran and the model emitted "Could not render
    that diagram." with no verified fence. The gate now detects symbolic
    comparators with a variable + number, and the inequality builder emits
    a number_line canonical_fence so validate_math_fences can replace the
    model's malformed graph attempt."""
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "X>4"}],
        "X>4",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "number_line"
    iv = verified.canonical_fence["intervals"][0]
    assert iv["start"] == 4.0
    assert iv["end"] is None
    assert iv["start_inclusive"] is False
    assert verified.canonical_answer is not None
    assert "4" in verified.canonical_answer


@pytest.mark.asyncio
async def test_graph_sample_respects_math_graph_max_points_above_200() -> None:
    """BUG FIX regression: a stray `min(..., 200)` silently capped every
    graph at 200 points regardless of math_graph_max_points, so raising
    the setting above 200 had no effect."""
    settings = Settings(math_tools_enabled=True, math_graph_max_points=220)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "Graph y = x^2"}],
        "Graph y = x^2",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert len(verified.canonical_fence["points"]) == 220
    assert VERIFIED_MATH_BEGIN in verified.text
    assert "Do not mention attaching" not in verified.text
    assert "Recall will attach" not in verified.text
    assert "```graph\n" not in verified.text


@pytest.mark.asyncio
async def test_default_graph_sample_stays_compact_for_chat_bubbles() -> None:
    """Default budget (~96) keeps densified fences SVG-friendly instead of
    dumping hundreds of points into the message (and FallbackMarkdown)."""
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "Graph y = x^4 - 4x^2"}],
        "Graph y = x^4 - 4x^2",
        settings,
    )
    assert verified is not None
    assert verified.canonical_fence is not None
    assert len(verified.canonical_fence["points"]) == settings.math_graph_max_points
    assert settings.math_graph_max_points <= 120


@pytest.mark.asyncio
async def test_wide_sine_graph_zooms_instead_of_aliasing() -> None:
    settings = Settings(math_tools_enabled=True)
    _out, verified = await augment_prompt_messages(
        [{"role": "user", "content": "Graph y = sin(x) from -1000 to 1000"}],
        "Graph y = sin(x) from -1000 to 1000",
        settings,
    )
    assert verified is not None
    fence = verified.canonical_fence
    assert fence is not None
    assert fence["type"] == "function"
    assert fence["x_max"] - fence["x_min"] < 100
    ys = [p[1] for p in fence["points"]]
    assert max(ys) > 0.5
    assert min(ys) < -0.5


@pytest.mark.asyncio
async def test_augment_prompt_injects_sympy_block() -> None:
    settings = Settings(math_tools_enabled=True)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Solve x^2 + 2 = 6"},
    ]
    out, verified = await augment_prompt_messages(
        messages,
        "Solve x^2 + 2 = 6",
        settings,
    )
    assert len(out) == 3
    assert out[1]["role"] == "system"
    assert VERIFIED_MATH_BEGIN in out[1]["content"]
    assert "SymPy" not in out[1]["content"]
    # Equation answers get a ```answer canonical fence for post-stream rewrite.
    assert verified is not None
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "answer"
    assert "x" in verified.canonical_fence["content"]


@pytest.mark.asyncio
async def test_sympy_solve_runs_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
) -> None:
    """The blocking SymPy call must not run on the event loop thread.

    Uses the in-process thread executor so the spy can record the worker
    thread (a subprocess can't write back to the test's memory). The
    production ProcessPoolSympyExecutor is exercised separately in
    test_sympy_executor.py.
    """
    import threading

    settings = Settings(math_tools_enabled=True)
    caller_thread = threading.current_thread()
    seen_thread: dict[str, threading.Thread] = {}

    original = math_tools._build_verified_block

    def spy(intent, settings):
        seen_thread["thread"] = threading.current_thread()
        return original(intent, settings)

    monkeypatch.setattr(math_tools, "_build_verified_block", spy)

    out, _verified = await augment_prompt_messages(
        [{"role": "user", "content": "Solve x^2 + 2 = 6"}],
        "Solve x^2 + 2 = 6",
        settings,
    )

    assert seen_thread["thread"] is not caller_thread
    assert len(out) == 2


@pytest.mark.asyncio
async def test_augment_prompt_times_out_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
) -> None:
    """A hung solve should not hang the caller, and must inject an honesty note.

    Uses the in-process thread executor so the local ``slow_build`` closure is
    callable (closures aren't picklable across a subprocess boundary). The
    production ProcessPoolSympyExecutor's hard-kill-on-timeout is exercised
    separately in test_sympy_executor.py.
    """
    settings = Settings(math_tools_enabled=True, stem_solve_timeout_seconds=0.05)

    def slow_build(intent, settings):
        import time

        time.sleep(0.5)
        return "should never be returned"

    monkeypatch.setattr(math_tools, "_build_verified_block", slow_build)

    messages = [{"role": "user", "content": "Solve x^2 + 2 = 6"}]
    out, verified = await augment_prompt_messages(
        messages,
        "Solve x^2 + 2 = 6",
        settings,
    )

    assert verified is None
    assert len(out) == 2
    note = next(m["content"] for m in out if m["role"] == "system")
    assert "could not be produced" in note
    assert "Do NOT claim the answer was verified" in note


@pytest.mark.asyncio
async def test_augment_prompt_math_service_error_injects_unverified_note(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
) -> None:
    """Parse/solve failures used to drop silently — same verified-looking chat
    UX as a successful SymPy block. Inject honesty instead."""
    settings = Settings(math_tools_enabled=True)

    def boom(intent, settings):
        raise math_tools.math_solve.SolveServiceError("unsafe expr")

    monkeypatch.setattr(math_tools, "_build_verified_block", boom)

    messages = [{"role": "user", "content": "Solve x^2 + 2 = 6"}]
    out, verified = await augment_prompt_messages(
        messages,
        "Solve x^2 + 2 = 6",
        settings,
    )

    assert verified is None
    note = next(m["content"] for m in out if m["role"] == "system")
    assert "kind=equation" in note
    assert "Do NOT claim the answer was verified" in note


@pytest.mark.asyncio
async def test_augment_prompt_broken_pool_injects_unverified_note(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
) -> None:
    """A sibling timeout's pool kill must not fail this turn before streaming."""
    from concurrent.futures.process import BrokenProcessPool

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise BrokenProcessPool("killed by sibling timeout")

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", boom)

    settings = Settings(math_tools_enabled=True)
    messages = [{"role": "user", "content": "Solve x^2 + 2 = 6"}]
    out, verified = await augment_prompt_messages(
        messages,
        "Solve x^2 + 2 = 6",
        settings,
    )

    assert verified is None
    note = next(m["content"] for m in out if m["role"] == "system")
    assert "Do NOT claim the answer was verified" in note
