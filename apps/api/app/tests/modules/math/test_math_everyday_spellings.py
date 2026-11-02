"""Everyday spellings of closed homework read completely, and look-alikes stay prose.

"456 x 23", "log base 2 of 64", "derivitive of …", "limit as x approaches 2 of …",
"det [[…]]", "lcm of 12, 18 and 30", "factorise …", the ``∫`` sign and systems typed
without "solve" each extend the grammar that owns them, so the gate, the extractor and
the direct-reply guard read the same words.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.match.arithmetic import bare_arithmetic_expr, times_between_numbers
from app.modules.math.match.calculus import calc_op, parse_limit, parse_series
from app.modules.math.match.discrete import (
    gcd_lcm_list_signal,
    matrix_signal,
    number_theory_signal,
)
from app.modules.math.match.scan import bare_equation_system, fix_leading_solve_typo
from app.modules.math.match.written import written_arithmetic_request
from app.modules.math.schemas.discrete import NumberTheoryInput
from app.modules.math.solve.discrete import compute_number_theory
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.keyboard_notation import keyboard_math_to_plain
from app.modules.math.tools.prompt import build_math_augmentation, needs_symbolic_math


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("456 x 23", "456 * 23"),
        ("1.5 X 4", "1.5 * 4"),
        ("15 - 4 x 3 + 8/2", "15 - 4 * 3 + 8/2"),
        ("8x5", "8x5"),
        ("2x + 3", "2x + 3"),
        ("3x+2y", "3x+2y"),
        ("0x10", "0x10"),
        ("x2 x 3", "x2 x 3"),
    ],
)
def test_times_between_numbers_reads_only_a_spaced_number_x_number(
    text: str, expected: str
) -> None:
    assert times_between_numbers(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("456 x 23", "456 * 23"),
        ("wat is 15 - 4 x 3 + 8/2", "15 - 4 * 3 + 8/2"),
        ("wats 6 x 7", "6 * 7"),
        ("what is 1.8*10^(-5) times 2", "1.8*10^(-5) * 2"),
        ("3 times 4 plus 2", "3 * 4 + 2"),
        ("10 divided by 4 minus 1", "10 / 4 - 1"),
        ("log base 2 of 64", "(ln(64)/ln(2))"),
        ("what is log base 10 of 1000", "(ln(1000)/ln(10))"),
        ("what is 0x10", None),
        ("2x + 3", None),
        ("3 times a day", None),
        ("log base 2 of my files", None),
    ],
)
def test_bare_arithmetic_expr_reads_everyday_operators(text: str, expected: str | None) -> None:
    assert bare_arithmetic_expr(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("456 x 23", ("456", "23", "*", "column_multiplication")),
        ("7 x 9", ("7", "9", "*", "column_multiplication")),
        ("1234 ÷ 7 with remainder", ("1234", "7", "/", "long_division")),
        ("0x10", None),
        ("8x5", None),
        ("2 x 4 lumber", None),
    ],
)
def test_written_arithmetic_request_reads_x_between_numbers(
    text: str, expected: tuple[str, str, str, str] | None
) -> None:
    assert written_arithmetic_request(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("factorise x^2+5x+6", "factor"),
        ("factorize x^2+5x+6", "factor"),
        ("derivitive of (2x+1)^5", "derivative"),
        ("dirivative of x^3", "derivative"),
        ("intergrate x^2", "integrate"),
        ("∫ x dx", "integrate"),
        ("derive the formula", None),
    ],
)
def test_calc_op_reads_british_and_misspelled_verbs(text: str, expected: str | None) -> None:
    assert calc_op(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("limit as x approaches 2 of (x^2-4)/(x-2)", ("(x^2-4)/(x-2)", "x", "2")),
        ("find the limit as x approaches 0 of sin(x)/x", ("sin(x)/x", "x", "0")),
        ("lim x→∞ (3x^2+1)/(x^2-5)", ("(3x^2+1)/(x^2-5)", "x", "oo")),
        ("lim x→-∞ e^x", ("e^x", "x", "-oo")),
        ("lim (1+1/n)^n as n->infinity", ("(1+1/n)^n", "n", "infinity")),
        ("limit of (x^2-4)/(x-2) as x->2", ("(x^2-4)/(x-2)", "x", "2")),
        ("limit as x approaches 2 of my patience", None),
        ("limit as x approaches 2", None),
        ("what's the speed limit as of 2024", None),
    ],
)
def test_parse_limit_reads_everyday_forms(text: str, expected: tuple[str, str, str] | None) -> None:
    hit = parse_limit(text)
    assert (None if hit is None else (hit.expr, hit.var, hit.point)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sum k^2 for k=1 to 10", ("k^2", "k", "1", "10")),
        ("sum of 1/n^2 for n=1 to infinity", ("1/n^2", "n", "1", "infinity")),
        ("sum my expenses for k=1 to 10", None),
    ],
)
def test_parse_series_reads_for_bounds(
    text: str, expected: tuple[str, str, str, str] | None
) -> None:
    hit = parse_series(text)
    assert (None if hit is None else (hit.expr, hit.var, hit.start, hit.end)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hcf of 48 and 180", ("gcd", 48, 180)),
        ("highest common factor of 12 and 30", ("gcd", 12, 30)),
        ("gcf of 8 and 12", ("gcd", 8, 12)),
        ("lowest common multiple of 4 and 6", ("lcm", 4, 6)),
        ("factor 360", ("factorize", 360, None)),
        ("factorise 360", ("factorize", 360, None)),
        ("please factorise 84 into primes", ("factorize", 84, None)),
        ("factor 2 hours into the plan", None),
        ("the factor 3 matters", None),
    ],
)
def test_number_theory_signal_reads_hcf_and_factor_spellings(
    text: str, expected: tuple[str, int, int | None] | None
) -> None:
    assert number_theory_signal(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("lcm of 12, 18 and 30", ("lcm", [12, 18, 30])),
        ("gcd of 12, 18 and 30", ("gcd", [12, 18, 30])),
        ("lcm(4, 6, 10, 15)", ("lcm", [4, 6, 10, 15])),
        ("lcm of 12 and 18", None),
        ("lcm of 12, 18 and 30.5", None),
        ("lcm of 0, 4 and 6", None),
    ],
)
def test_gcd_lcm_list_signal_reads_three_or_more_numbers(
    text: str, expected: tuple[str, list[int]] | None
) -> None:
    assert gcd_lcm_list_signal(text) == expected


@pytest.mark.parametrize(
    ("operation", "values", "result"),
    [("lcm", [12, 18, 30], 180), ("gcd", [12, 18, 30], 6), ("lcm", [4, 6, 10, 15], 60)],
)
def test_compute_number_theory_combines_a_list(
    operation: str, values: list[int], result: int
) -> None:
    solved = compute_number_theory(
        NumberTheoryInput.model_validate(
            {"operation": operation, "a": values[0], "b": values[1], "values": values}
        )
    )
    assert solved.result_int == result
    assert solved.steps[-1] == f"{operation}({', '.join(map(str, values))}) = {result}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("det [[2,3],[1,4]]", "determinant"),
        ("det of [[1,2],[3,4]]", "determinant"),
        ("detail [[1,2],[3,4]]", None),
    ],
)
def test_matrix_signal_reads_det_shorthand(text: str, expected: str | None) -> None:
    signal = matrix_signal(text)
    assert (None if signal is None else signal[0]) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x+y+z=6, 2x-y+z=3, x+2y-z=2", True),
        ("3x+2y=12 and x-y=1", True),
        ("2x + y = 7; x - y = 2", True),
        ("a=1, b=2", False),
        ("x=1, y=2", False),
        ("2x+3=7", False),
        ("meeting = 3pm, lunch = noon", False),
        ("x+y=1, x-y=2, x+2y=3, 2x-y=4, x=5", False),
    ],
)
def test_bare_equation_system_reads_only_equations(text: str, expected: bool) -> None:
    assert bare_equation_system(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("slove 4x - 8 = 12", "solve 4x - 8 = 12"),
        ("Sovle x+1=2", "solve x+1=2"),
        ("the slove 4x", "the slove 4x"),
    ],
)
def test_fix_leading_solve_typo_reads_the_verb(text: str, expected: str) -> None:
    assert fix_leading_solve_typo(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\\frac{d}{dx} x^5", "d/dx x^5"),
        ("\\int_{0}^{1} x^2\\,dx", "integrate x^2 from 0 to 1"),
        ("see \\frac{d}{dx} in my notes", "see \\frac{d}{dx} in my notes"),
    ],
)
def test_keyboard_math_to_plain_reads_latex_typed_without_dollars(text: str, expected: str) -> None:
    assert keyboard_math_to_plain(text) == expected


@pytest.mark.parametrize(
    ("text", "kind", "lower", "upper"),
    [
        ("∫ (3x^2 + 2x) dx", "calculus", None, None),
        ("∫_0^π sin x dx", "calculus", "0", "pi"),
        ("∫_{1}^{e} ln x dx", "calculus", "1", "e"),
    ],
)
def test_extract_math_intent_reads_the_integral_sign(
    text: str, kind: str, lower: str | None, upper: str | None
) -> None:
    intent = extract_math_intent(text)
    assert intent is not None
    assert intent.kind == kind and intent.operation == "integrate"
    assert "∫" not in (intent.expr or "")
    assert (intent.integral_lower, intent.integral_upper) == (lower, upper)


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("456 x 23", "10488"),
        ("wat is 15 - 4 x 3 + 8/2", "7"),
        ("1234 ÷ 7 with remainder", "176 R2"),
        ("log base 2 of 64", "6"),
        ("derivitive of (2x+1)^5", r"10 \left(2 x + 1\right)^{4}"),
        ("factorise x²+5x+6", r"\left(x + 2\right) \left(x + 3\right)"),
        ("factor 360", r"2^{3} \times 3^{2} \times 5"),
        ("limit as x approaches 2 of (x^2-4)/(x-2)", "4"),
        ("lim x→∞ (3x^2+1)/(x^2-5)", "3"),
        ("lim (1+1/n)^n as n->infinity", "e"),
        ("det [[2,3],[1,4]]", "5"),
        ("lcm of 12, 18 and 30", "180"),
        ("hcf of 48 and 180", "12"),
        ("∫_0^π sin x dx", "2"),
        ("sum k^2 for k=1 to 10", "385"),
        ("x+y+z=6, 2x-y+z=3, x+2y-z=2", "x = 1, y = 2, z = 3"),
        ("slove 4x - 8 = 12", "x = 5"),
        ("\\frac{d}{dx} x^5", "5 x^{4}"),
    ],
)
@pytest.mark.asyncio
async def test_build_math_augmentation_verifies_everyday_spellings(text: str, answer: str) -> None:
    assert needs_symbolic_math(text)
    _, verified = await build_math_augmentation(text, Settings(math_tools_enabled=True))
    assert verified is not None
    assert verified.canonical_answer == answer


@pytest.mark.parametrize(
    "text",
    [
        "I need 2 x 4 lumber for the deck",
        "what is 0x10 in decimal",
        "factor 2 hours into the plan",
        "factorise my reading list by topic",
        "the derivitive market crashed",
        "det is short for detective",
        "limit as x approaches 2 of my patience",
        "sum my expenses for k=1 to 10",
        "hcf meeting at 3",
        "a=1, b=2",
    ],
)
def test_needs_symbolic_math_keeps_lookalikes_out(text: str) -> None:
    assert not needs_symbolic_math(text)
