"""A direct Newton reply retains the verified method, parameters, and iterates."""

import re
from dataclasses import replace
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.fence import validate_math_fences
from app.modules.math.schemas import NewtonMethodInput
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent

_QUERY = "Use Newton method to solve x^2-2=0 starting at 1"
_SETTINGS = Settings(math_tools_enabled=True)


def _block(query=_QUERY):
    intent = extract_math_intent(query)
    assert intent is not None
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None
    return block


def test_exact_c17_displays_verified_recurrence_every_iterate_and_root_without_model():
    block = _block()
    result = block.newton_result
    assert result is not None
    with patch.object(math_solve, "newton_method", side_effect=AssertionError("no re-solve")):
        reply = maybe_direct_math_reply(block, _QUERY)
    assert reply is not None
    assert result.recurrence_latex in reply
    assert r"\frac{x_{n}^{2} - 2}{2 x_{n}}" in reply
    for row in [
        "$x_{0} = 1$",
        "$x_{1} = 1.5$",
        "$x_{2} = 1.4166666667$",
        "$x_{3} = 1.4142156863$",
        "$x_{4} = 1.4142135624$",
    ]:
        assert row in reply
    assert r"$x \approx 1.41421$" in reply
    assert "0.000001" in reply
    assert "Tip" not in reply
    assert "```answer" not in reply
    # The fence pass lands the verified root in the card under Answer, still an
    # approximation of x: a numerical root never looks exact.
    landed = validate_math_fences(reply, verified=block)
    card = "**Answer**\n\n```answer\nverified: true\nx \\approx 1.41421\n```"
    assert landed.rstrip().endswith(card)
    assert landed.count("```answer") == 1


def test_an_exact_answer_card_carries_no_approximation():
    """The approximate form is Newton's display form, not a rule for every card."""
    block = _block("solve 3x^2+5=4")
    assert block.newton_result is None
    landed = validate_math_fences("Subtract 5, then divide by 3.", verified=block)
    exact = "x = \\pm \\frac{\\sqrt{3}}{3} i"
    assert landed.rstrip().endswith(f"**Answer**\n\n```answer\nverified: true\n{exact}\n```")
    assert "\\approx" not in landed


@pytest.mark.parametrize(
    "query",
    [
        "Use Newton's method to solve x^3-2x-5=0 starting at x0 = 2",
        "Newton's method for x^2-2=0 with initial guess of -1",
        "Please use Newton method to solve t^2-2=0 starting at 1.",
        "Use Newton's method on x=cos(x) starting at 1",
        "Use Newton method to solve x^2-2=0 starting at 0.5",
    ],
)
def test_whole_supported_equations_variables_and_starts_match_the_solve(query):
    block = _block(query)
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None
    assert block.newton_result.recurrence_latex in reply
    assert rf"${block.newton_input.variable} \approx {block.canonical_answer}$" in reply


@pytest.mark.parametrize(
    "query",
    [
        _QUERY + " to 8 decimal places",
        _QUERY + " with tolerance 0.001",
        _QUERY + " for exactly 3 iterations",
        _QUERY + " and solve x+1=2",
        _QUERY + " and explain why",
        _QUERY + ", hint only",
        _QUERY + " with proof of convergence",
        _QUERY + " using bisection too",
        _QUERY + " on the interval [0,2]",
        _QUERY + "!",
        "Use Newton method to solve x^2-2=0",
        "Use Newton method to solve x^2-2=0 starting at .5",
        "Use Newton method to solve x^2-2=0 starting at 1e-3",
        "Use Newton method to solve x^2-2=0 starting at y0=1",
        "Use Newton method to solve x^2-2=0 and x-1=0 starting at 1",
        "Use Newton method to solve x^2-2=0 starting at 1 and 2",
        "Prove Newton's method converges for x^2-2=0 starting at 1",
    ],
)
def test_partial_teaching_precision_and_unsupported_parameters_keep_model(query):
    assert maybe_direct_math_reply(_block(), query) is None


@pytest.mark.parametrize(
    "updates",
    [
        {"expr": "x^2-3"},
        {"variable": "t"},
        {"initial_guess": 2.0},
        {"tolerance": 0.001},
        {"max_iterations": 3},
    ],
)
def test_every_verified_input_parameter_must_match_the_complete_request(updates):
    block = _block()
    changed = block.newton_input.model_copy(update=updates)
    assert maybe_direct_math_reply(replace(block, newton_input=changed), _QUERY) is None


@pytest.mark.parametrize(
    "updates",
    [
        {"converged": False},
        {"root": None},
        {"root": float("nan")},
        {"root": 3.0},
        {"iterations_used": 99},
        {"iterations": []},
        {"function_latex": None},
        {"derivative_latex": "0"},
        {"recurrence_latex": None},
    ],
)
def test_failed_or_incomplete_results_cannot_be_presented_as_newton_success(updates):
    block = _block()
    changed = block.newton_result.model_copy(update=updates)
    assert maybe_direct_math_reply(replace(block, newton_result=changed), _QUERY) is None


def test_recorded_history_must_start_at_the_input_and_have_finite_contiguous_steps():
    block = _block()
    for updates in ({"n": 99}, {"x_n": float("inf")}, {"f_x_n": float("nan")}, {"x_n": 2.0}):
        changed = block.newton_result.model_copy(deep=True)
        changed.iterations[0] = changed.iterations[0].model_copy(update=updates)
        assert maybe_direct_math_reply(replace(block, newton_result=changed), _QUERY) is None


def test_nonconvergent_actual_newton_solve_and_image_requests_keep_model():
    query = "Use Newton method to solve x^2+1=0 starting at 0"
    block = _block(query)
    assert block.canonical_answer is None
    assert block.newton_result is not None and not block.newton_result.converged
    assert maybe_direct_math_reply(block, query) is None
    assert maybe_direct_math_reply(_block(), _QUERY, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(_block(), allow_direct=False), _QUERY) is None


def test_missing_metadata_or_mismatched_extra_fences_never_use_a_numeric_fallback():
    block = _block()
    assert maybe_direct_math_reply(replace(block, newton_input=None), _QUERY) is None
    assert maybe_direct_math_reply(replace(block, newton_result=None), _QUERY) is None
    assert maybe_direct_math_reply(replace(block, canonical_answer="9"), _QUERY) is None
    changed = replace(block, canonical_fences=[{"type": "answer", "content": "9"}])
    assert maybe_direct_math_reply(changed, _QUERY) is None


def test_long_iteration_history_shows_labeled_first_and_last_actual_rows():
    query = "Use Newton method to solve x^2-2=0 starting at 1000"
    block = _block(query)
    assert len(block.newton_result.iterations) > 8
    reply = maybe_direct_math_reply(block, query)
    assert reply is not None
    # First four and last three iterates, with a gap line between.
    assert "$x_{0} = 1000$" in reply and "…" in reply
    # Seven iterates and the gap line, not the whole history.
    assert len([line for line in reply.splitlines() if re.match(r"\$x_\{\d+\}", line)]) == 7
    last = block.newton_result.iterations[-1]
    assert f"$x_{{{last.n}}} = {last.x_n}" in reply


def test_block_carries_deep_copies_of_the_actual_solved_result():
    solved = math_solve.newton_method(NewtonMethodInput(expr="x^2-2", initial_guess=1))
    with patch.object(math_solve, "newton_method", return_value=solved):
        block = _block()
    solved.root = 99
    solved.iterations[0].x_n = 99
    assert block.newton_result.root != 99
    assert block.newton_result.iterations[0].x_n == 1
    assert maybe_direct_math_reply(block, _QUERY) is not None
