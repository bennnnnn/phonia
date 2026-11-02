"""Undefined integral outcomes must not become verified answer cards."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.fence import validate_math_fences
from app.modules.math.schemas import MathExprResult
from app.modules.math.tool import SympyAdapter
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.calculus_outcome import undefined_integral_note
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent
from app.tests.tool_context import tool_context

_SETTINGS = Settings(math_tools_enabled=True)


def _block(query):
    intent = extract_math_intent(query)
    assert intent is not None
    block = _build_verified_block(intent, _SETTINGS)
    assert block is not None
    return block


def test_actual_undefined_improper_integral_does_not_append_nan_to_explanation():
    query = "Integrate 1/x from -1 to 1"
    # Preserve the solver's diagnostic. Only its presentation becomes a non-result.
    outcome = math_solve.integrate_definite("1/x", "x", "-1", "1")
    assert outcome.result == "nan"
    block = _block(query)
    assert block.canonical_answer is None and block.canonical_fence is None
    assert "did not establish a defined value" in block.text
    assert "diverges" not in block.text
    assert "principal value" in block.text
    assert maybe_direct_math_reply(block, query) == (
        "This ordinary improper integral does not converge. "
        "A Cauchy principal value is a separate convention and was not requested."
    )
    explanation = "The ordinary improper integral does not converge."
    assert validate_math_fences(explanation, verified=block) == explanation
    assert "NaN" not in validate_math_fences(explanation, verified=block)


@pytest.mark.parametrize("raw,latex", [("nan", r"\text{NaN}"), ("zoo", r"\tilde{\infty}")])
def test_nonresults_are_not_mislabeled_as_unevaluated_or_signed_divergence(raw, latex):
    with patch.object(
        math_solve, "integrate_definite", return_value=MathExprResult(result=raw, latex=latex)
    ):
        block = _block("Integrate x from 0 to 1")
    assert block.canonical_answer is None and block.canonical_fence is None
    assert "No closed-form" not in block.text
    assert "diverges" not in block.text
    assert "did not establish a defined value" in block.text


@pytest.mark.parametrize(
    "query,direction",
    [
        ("Integrate 1/x^2 from -1 to 1", "positive"),
        ("Integrate -1/x^2 from -1 to 1", "negative"),
    ],
)
def test_signed_infinity_retains_a_divergence_explanation(query, direction):
    block = _block(query)
    assert block.canonical_answer is None
    assert f"diverges to {direction} infinity" in block.text
    symbol = "+∞" if direction == "positive" else "−∞"
    assert maybe_direct_math_reply(block, query) == (
        f"This improper integral diverges to {symbol}; it does not converge to a finite value."
    )
    assert "NaN" not in validate_math_fences("This integral diverges.", verified=block)


@pytest.mark.parametrize(
    "query,answer",
    [
        ("Integrate x^2 from 0 to 1", r"\frac{1}{3}"),
        ("Integrate 1/sqrt(x) from 0 to 1", "2"),
        ("Integrate exp(-x) from 0 to infinity", "1"),
        ("Integrate x^2", r"\frac{x^{3}}{3} + C"),
    ],
)
def test_defined_finite_and_convergent_improper_integrals_keep_their_answers(query, answer):
    block = _block(query)
    assert block.canonical_answer == answer
    assert "did not establish" not in block.text
    assert "diverges" not in block.text


@pytest.mark.parametrize(
    "query",
    [
        "Find the Cauchy principal value of the integral of 1/x from -1 to 1",
        "Find the principal-value integral of 1/x from -1 to 1",
        "Find the PRINCIPAL VALUE of the integral of 1/x from -1 to 1",
        "Integrate 1/x from -1 to 1 in the Cauchy principal value sense",
    ],
)
def test_principal_value_is_not_silently_solved_as_an_ordinary_integral(query):
    assert extract_math_intent(query) is None
    assert maybe_direct_math_reply(_block("Integrate x^2 from 0 to 1"), query) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expr,answer,phrase",
    [
        ("1/x", None, "did not establish a defined value"),
        ("1/x^2", r"\infty", "diverges to positive infinity"),
        ("-1/x^2", r"-\infty", "diverges to negative infinity"),
        ("x^2", r"\frac{2}{3}", "Verified result"),
    ],
)
async def test_tool_loop_uses_the_same_integral_outcome_contract(expr, answer, phrase):
    async def compute_locally(fn, *args):
        return fn(*args)

    adapter = SympyAdapter(_SETTINGS)
    with patch.object(adapter, "_run_off_loop", side_effect=compute_locally):
        result = await adapter.invoke(
            {"action": "integrate", "expr": expr, "lower": "-1", "upper": "1"}, tool_context()
        )
    assert phrase in result.content
    if answer is None or "infty" in (answer or ""):
        assert result.data is None
        assert "Verified result" not in result.content
        if answer is None:
            assert "diverges" not in result.content
        else:
            assert "diverges" in result.content
    else:
        assert result.data is not None
        assert result.data["canonical_answer"] == answer


@pytest.mark.asyncio
async def test_tool_complex_infinity_does_not_produce_a_canonical_answer():
    adapter = SympyAdapter(_SETTINGS)
    with patch.object(
        adapter,
        "_run_off_loop",
        AsyncMock(return_value=MathExprResult(result="zoo", latex=r"\tilde{\infty}")),
    ):
        result = await adapter.invoke(
            {"action": "integrate", "expr": "x", "lower": "0", "upper": "1"}, tool_context()
        )
    assert result.data is None
    assert "did not establish a defined value" in result.content


@pytest.mark.parametrize("expr", ["1/0", "1/(x-x)"])
def test_indefinite_integral_with_embedded_complex_infinity_is_not_an_answer(expr):
    block = _block(f"Integrate {expr}")
    assert block.canonical_answer is None and block.canonical_fence is None
    assert "did not establish a defined value" in block.text
    assert "+ C" not in block.text
    explanation = "The integrand is undefined."
    assert validate_math_fences(explanation, verified=block) == explanation


@pytest.mark.asyncio
@pytest.mark.parametrize("expr", ["1/0", "1/(x-x)"])
async def test_tool_indefinite_integral_rejects_embedded_complex_infinity(expr):
    async def compute_locally(fn, *args):
        return fn(*args)

    adapter = SympyAdapter(_SETTINGS)
    with patch.object(adapter, "_run_off_loop", side_effect=compute_locally):
        result = await adapter.invoke({"action": "integrate", "expr": expr}, tool_context())
    assert result.data is None
    assert "did not establish a defined value" in result.content
    assert "+ C" not in result.content


@pytest.mark.parametrize(
    "result", ["nan_value", "zoo_value", "nanosecond", "zookeeper", "AccumBounds_value"]
)
def test_undefined_marker_detection_does_not_match_parts_of_symbol_names(result):
    assert undefined_integral_note(result) is None


@pytest.mark.parametrize("expr", ["sin(x)", "cos(x)"])
def test_oscillating_improper_integral_does_not_become_an_interval_answer(expr):
    block = _block(f"Integrate {expr} from 0 to infinity")
    assert block.canonical_answer is None and block.canonical_fence is None
    assert "did not establish a defined value" in block.text
    explanation = "The ordinary improper integral does not converge."
    assert validate_math_fences(explanation, verified=block) == explanation


@pytest.mark.asyncio
@pytest.mark.parametrize("expr", ["sin(x)", "cos(x)"])
async def test_tool_accumulation_bounds_are_not_an_integral_value(expr):
    async def compute_locally(fn, *args):
        return fn(*args)

    adapter = SympyAdapter(_SETTINGS)
    with patch.object(adapter, "_run_off_loop", side_effect=compute_locally):
        result = await adapter.invoke(
            {"action": "integrate", "expr": expr, "lower": "0", "upper": "infinity"}, tool_context()
        )
    assert result.data is None
    assert "did not establish a defined value" in result.content
