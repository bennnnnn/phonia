"""Inputs the October 2026 review found certified with a wrong answer.

Each row runs the real pre-stream path (subject dispatch, extraction, SymPy,
direct reply) with no model call. See docs/MATH_REVIEW.md §2.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.solve.parse import parse_expression
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import build_subject_augmentation, maybe_direct_subject_reply


def _settings() -> Settings:
    return Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)


async def _answer(text: str) -> tuple[str | None, str | None, str | None]:
    """(subject, canonical answer, direct reply) for one turn."""
    augmentation = await build_subject_augmentation(text, _settings())
    verified = augmentation.verified
    reply = maybe_direct_subject_reply(verified, text)
    answer = getattr(verified, "canonical_answer", None) if verified is not None else None
    return augmentation.subject, answer, reply


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("log2(x) + log2(x-2)", "log(x)/log(2) + log(x - 2)/log(2)"),
        ("log10(x)", "log(x)/log(10)"),
        (r"\log_{2}(x)", "log(x)/log(2)"),
        ("cos2x", "cos(2*x)"),
        ("sin2x", "sin(2*x)"),
        ("sinx", "sin(x)"),
        ("lnx", "log(x)"),
        ("2xy", "2*x*y"),
        ("mx+c", "c + m*x"),
    ],
)
def test_parse_reads_written_function_shorthand(text: str, expected: str) -> None:
    assert str(parse_expression(text, ["x"])) == expected


@pytest.mark.parametrize("text", ["5 kg", "3 cm", "20 mol", "sinx^2", "log(x) + 2kg"])
def test_parse_refuses_letters_taken_from_a_word(text: str) -> None:
    """A symbol that exists only inside a function or unit word is a misread."""
    with pytest.raises(SolveServiceError):
        parse_expression(text, ["x"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("solve log2(x) + log2(x-2) = 3", "x = 4"),
        ("solve cos2x = 0", r"x = \pi k + \frac{\pi}{4}"),
        ("solve e^(2x) = 5", r"x = \frac{\ln 5}{2}"),
        ("solve x^3 = 8", "x = 2"),
        ("solve x^4 = 16", r"x = \pm 2"),
        ("solve x^2 + 1 = 0", r"x = \pm i"),
    ],
)
async def test_equations_answer_what_was_written(text: str, answer: str) -> None:
    subject, canonical, reply = await _answer(text)
    assert subject == "math"
    assert canonical is not None and canonical.startswith(answer)
    assert reply is not None
    for misread in ("g l o", "c o s", r"\pi i", r"\sqrt{3} i"):
        assert misread not in reply


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("log(x)", "log(x)/log(10)"),
        ("log x", "log(x)/log(10)"),
        (r"\log x", "log(x)/log(10)"),
        ("lg(x)", "log(x)/log(10)"),
        ("ln(x)", "log(x)"),
        ("log(8, 2)", "3"),
        ("log(1000)", "3"),
    ],
)
def test_parse_reads_a_bare_log_as_base_ten(text: str, expected: str) -> None:
    """School notation: ``log`` is base 10, ``ln`` is natural, a written base is kept."""
    assert str(parse_expression(text, ["x"])) == expected


def test_natural_log_prints_as_ln_and_a_change_of_base_as_its_base() -> None:
    from sympy import Symbol, latex, log

    x = Symbol("x")
    assert latex(log(x)) == r"\ln{\left(x \right)}"
    assert latex(log(x) / log(10)) == r"\log_{10}\left(x\right)"
    assert latex(3 * log(x) / log(2)) == r"3 \log_{2}\left(x\right)"
    assert latex(1 / (x * log(10))) == r"\frac{1}{x \ln 10}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("solve log(x) = 2", "x = 100"),
        ("solve lg(x) = 3", "x = 1000"),
        ("solve log(x) + log(x - 3) = 1", "x = 5"),
        ("solve ln(x) = 2", "x = e^{2}"),
        ("solve 10^x = 50", r"x = \log_{10} 50"),
    ],
)
async def test_bare_log_equations_are_base_ten(text: str, answer: str) -> None:
    subject, canonical, reply = await _answer(text)
    assert subject == "math"
    assert canonical == answer
    assert reply is not None


@pytest.mark.asyncio
async def test_base_ten_derivative_is_exact_with_its_rule() -> None:
    _, canonical, reply = await _answer("differentiate log(x^2 + 1)")
    assert canonical == r"\frac{2 x}{\left(x^{2} + 1\right) \ln 10}"
    assert reply is not None
    assert r"$\frac{d}{dx} \log_{b} x = \frac{1}{x \ln b}$" in reply
    assert "0.86" not in reply


@pytest.mark.asyncio
async def test_all_roots_keeps_the_complex_roots() -> None:
    _subject, canonical, _reply = await _answer("find all roots of x^3 - 8")
    assert canonical is not None
    assert "x = 2" in canonical and r"\sqrt{3} i" in canonical


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer", "shown"),
    [
        ("standard deviation of 2,4,4,4,5,5,7,9", "2", r"\sigma = 2"),
        ("variance of 2,4,4,4,5,5,7,9", "4", r"\sigma^{2} = 4"),
        ("sample standard deviation of 2,4,4,4,5,5,7,9", "2.1381", "s = 2.1381"),
    ],
)
async def test_data_list_spread_is_math_and_says_which_spread(
    text: str, answer: str, shown: str
) -> None:
    subject, canonical, reply = await _answer(text)
    assert subject == "math"
    assert canonical == answer
    assert reply == f"```answer\n{shown}\n```\n"


@pytest.mark.asyncio
async def test_mean_and_standard_deviation_answers_both() -> None:
    subject, canonical, _reply = await _answer("mean and standard deviation of 2,4,4,4,5,5,7,9")
    assert subject == "math"
    assert canonical == r"\bar{x} = 5,\quad \sigma = 2"


@pytest.mark.asyncio
async def test_lab_readings_stay_chemistry() -> None:
    subject, _canonical, _reply = await _answer(
        "Find the standard deviation of these measurements: 10.1, 10.3, 10.2"
    )
    assert subject == "chemistry"


@pytest.mark.asyncio
async def test_unit_givens_are_physics_not_algebra() -> None:
    subject, canonical, reply = await _answer("F = 20 N, m = 5 kg, find a")
    assert subject == "physics"
    assert canonical is not None and canonical.startswith("4")
    assert reply is not None and "infinitely many" not in reply


@pytest.mark.asyncio
async def test_system_does_not_answer_a_letter_it_never_contains() -> None:
    subject, canonical, reply = await _answer("a = 3, b = 4, find c")
    assert subject == "math"
    assert canonical is None and reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("Show steps: ∛(x)=2", "x = 8"),
        ("solve ∛x = 3", "x = 27"),
        ("Show steps: (1/2)x+3=7", "x = 8"),
        ("Show steps: log_2(x)+log_2(x-2)=3", "x = 4"),
        ("Show steps: 2/(x-1)=3/(x+1)", "x = 5"),
        ("Show steps: |2x-1|=7", r"x = -3 \text{ or } x = 4"),
    ],
)
async def test_scan_readings_solve_what_was_printed(text: str, answer: str) -> None:
    """What the scanner shows is what Solve sends; it must parse whole."""
    _subject, canonical, _reply = await _answer(text)
    assert canonical == answer


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Show steps: x^2=2, x∈ℤ", "Show steps: 2x + 3 = 7 (x ∈ ℤ)"])
async def test_a_printed_number_set_is_never_dropped(text: str) -> None:
    _subject, canonical, reply = await _answer(text)
    assert canonical is None and reply is None
