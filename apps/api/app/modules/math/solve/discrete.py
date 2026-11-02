"""Statistics, combinatorics, number theory, matrices."""

from __future__ import annotations

import math
import re
import statistics as _stats
from typing import Literal

from sympy import Matrix, Rational, factorint, isprime, latex

from app.modules.math.function_names import (
    GREEK_NAMES,
    MATH_FUNCTION_NAMES,
    function_name_alternation,
)
from app.modules.math.match.letter_runs import mask_unknown_letter_runs
from app.modules.math.schemas import (
    CombinatoricsInput,
    CombinatoricsResult,
    MatrixInput,
    MatrixResult,
    NumberTheoryInput,
    NumberTheoryResult,
    StatisticsInput,
    StatisticsResult,
)
from app.services.solving import SolveServiceError

# Letters around a name, not ``\b``: in ``2sin(t)`` the digit joins the word,
# so ``sin`` stayed and the guesser solved for ``i`` ("no solution").
_FUNCTION_NAME_RE = re.compile(
    rf"(?<![A-Za-z])(?:{function_name_alternation(MATH_FUNCTION_NAMES | {'min', 'max'})})"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)
# A Greek letter name is one unknown (the keypad's θ), not five letters.
_GREEK_NAME_RE = re.compile(rf"(?<![A-Za-z])(?:{'|'.join(GREEK_NAMES)})(?![A-Za-z])")

# Multi-letter mathematical constants that must NOT be split into per-letter
# variable candidates. Without this, "sin(pi*x) = 0" would guess 'i' and 'p'
# as variables (alphabetically before 'x'), silently solving for the wrong
# symbol. SymPy recognizes these as constants, so the guesser must too.
_CONSTANT_NAMES_RE = re.compile(
    r"\b(?:pi|oo|inf|infinity|nan)\b",
    re.IGNORECASE,
)


def guess_variables(text: str) -> list[str]:
    """The letters that may be the unknowns, after function names and multi-letter
    constants (pi, oo, ...) are removed: "cos(x) = 0" solves for 'x', not 'c', and
    "sin(pi*x) = 0" for 'x', not 'i' or 'p'."""
    stripped = _FUNCTION_NAME_RE.sub(" ", text)
    stripped = _CONSTANT_NAMES_RE.sub(" ", stripped)
    greek = list(dict.fromkeys(_GREEK_NAME_RE.findall(stripped)))
    stripped = _GREEK_NAME_RE.sub(" ", stripped)
    stripped = mask_unknown_letter_runs(stripped)
    found = sorted(set(re.findall(r"[a-zA-Z]", stripped)))
    # Exclude single-letter constants: e (Euler's number), i (imaginary unit
    # in some contexts, though commonly a variable index -- keep it for now
    # since 'i' is far more often a loop variable than the imaginary unit in
    # user input). E (uppercase) is SymPy's Euler number.
    # I is the imaginary unit the math keyboard types as ``\\mathrm{i}``.
    letters = greek + [c for c in found if c not in {"e", "E", "I"}]
    return letters[:4] if letters else ["x"]


def _four_places(value: float) -> str:
    """``2.1381`` stays; ``2.0000`` is ``2`` (the zeros claimed precision)."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def compute_statistics(data: StatisticsInput) -> StatisticsResult:
    """Mean/median/mode/variance/stdev for a raw list of numbers — stdlib
    `statistics`, not SymPy (no expression parsing needed for plain floats)."""
    numbers = data.numbers
    n = len(numbers)
    total = math.fsum(numbers)
    mean_val = total / n
    median_val = _stats.median(numbers)
    # multimode() returns every value tied for most frequent — when every
    # value is unique that's the WHOLE list, which isn't a meaningful mode.
    modes = sorted(_stats.multimode(numbers))
    if len(modes) == n and n > 1:
        modes = []
    variance_population = _stats.pvariance(numbers)
    stdev_population = _stats.pstdev(numbers)
    variance_sample = _stats.variance(numbers) if n >= 2 else None
    stdev_sample = _stats.stdev(numbers) if n >= 2 else None
    range_val = max(numbers) - min(numbers)
    labels = {
        "count": str(n),
        "sum": f"{total:g}",
        "mean": f"{mean_val:g}",
        "median": f"{median_val:g}",
        "mode": ", ".join(f"{m:g}" for m in modes) if modes else "none",
        "range": f"{range_val:g}",
        "population_stdev": _four_places(stdev_population),
        "sample_stdev": _four_places(stdev_sample) if stdev_sample is not None else "n/a",
    }
    return StatisticsResult(
        count=n,
        numbers=numbers,
        sum=round(total, 6),
        mean=round(mean_val, 6),
        median=round(median_val, 6),
        modes=modes,
        range=round(range_val, 6),
        variance_population=round(variance_population, 6),
        stdev_population=round(stdev_population, 6),
        variance_sample=round(variance_sample, 6) if variance_sample is not None else None,
        stdev_sample=round(stdev_sample, 6) if stdev_sample is not None else None,
        labels=labels,
    )


def compute_combinatorics(data: CombinatoricsInput) -> CombinatoricsResult:
    """Factorial / nCr / nPr — plain integer arithmetic (math.factorial/comb/
    perm), not SymPy: these never touch the untrusted-expression parser."""
    if data.operation == "factorial":
        if data.n > 170:
            raise SolveServiceError("Factorial input is capped at 170")
        result = math.factorial(data.n)
        return CombinatoricsResult(
            operation="factorial",
            n=data.n,
            k=None,
            result=result,
            steps=[f"{data.n}! = {result}"],
        )
    if data.k is None or data.k < 0 or data.k > data.n:
        raise SolveServiceError("k must satisfy 0 <= k <= n")
    if data.operation == "combinations":
        result = math.comb(data.n, data.k)
        steps = [
            f"C({data.n},{data.k}) = {data.n}! / ({data.k}! \\times "
            f"({data.n}-{data.k})!) = {result}"
        ]
    else:
        result = math.perm(data.n, data.k)
        steps = [f"P({data.n},{data.k}) = {data.n}! / ({data.n}-{data.k})! = {result}"]
    return CombinatoricsResult(
        operation=data.operation, n=data.n, k=data.k, result=result, steps=steps
    )


def _gcd_lcm_of_list(operation: Literal["gcd", "lcm"], values: list[int]) -> NumberTheoryResult:
    """gcd or lcm of a list, two numbers at a time: lcm(12, 18) = 36, lcm(36, 30) = 180."""
    combine = math.gcd if operation == "gcd" else math.lcm
    running = values[0]
    steps: list[str] = []
    for value in values[1:]:
        combined = combine(running, value)
        steps.append(f"{operation}({running}, {value}) = {combined}")
        running = combined
    listed = ", ".join(str(value) for value in values)
    steps.append(f"{operation}({listed}) = {running}")
    return NumberTheoryResult(
        operation=operation, a=values[0], b=values[1], result_int=running, steps=steps
    )


def compute_number_theory(data: NumberTheoryInput) -> NumberTheoryResult:
    """GCD / LCM / prime factorization / primality / modulo — integer-only,
    bypasses the expression parser entirely (see NumberTheoryInput's bounds
    for why factorize/is_prime stay fast even on an adversarial input)."""
    a = data.a
    if data.operation in ("gcd", "lcm") and data.values:
        return _gcd_lcm_of_list(data.operation, data.values)
    if data.operation in ("gcd", "lcm", "mod"):
        if data.b is None:
            raise SolveServiceError(f"{data.operation} requires two integers")
        b = data.b
        if data.operation == "gcd":
            result = math.gcd(a, b)
            steps = [f"gcd({a}, {b}) = {result}"]
        elif data.operation == "lcm":
            result = math.lcm(a, b)
            steps = [f"lcm({a}, {b}) = {result}"]
        else:
            if b == 0:
                raise SolveServiceError("Modulo by zero is undefined")
            result = a % b
            steps = [f"{a} \\bmod {b} = {result}"]
        return NumberTheoryResult(
            operation=data.operation, a=a, b=b, result_int=result, steps=steps
        )

    if data.operation == "mod_inverse":
        from app.modules.math.formulas import modular_inverse

        if data.b is None:
            raise SolveServiceError("modular inverse requires two integers")
        result = int(modular_inverse(a, data.b))
        return NumberTheoryResult(
            operation="mod_inverse",
            a=a,
            b=data.b,
            result_int=result,
            steps=[f"{a}^{{-1}} \\bmod {data.b} = {result}"],
        )

    if data.operation == "totient":
        from app.modules.math.formulas import euler_totient

        result = int(euler_totient(a))
        return NumberTheoryResult(
            operation="totient", a=a, b=None, result_int=result, steps=[f"\\phi({a}) = {result}"]
        )

    if data.operation == "factorize":
        if a < 2:
            raise SolveServiceError("Prime factorization needs an integer >= 2")
        raw_factors = factorint(a)
        factors = {int(p): int(e) for p, e in raw_factors.items()}
        parts = [(f"{p}^{{{e}}}" if e > 1 else f"{p}") for p, e in sorted(factors.items())]
        steps = [f"{a} = " + " \\times ".join(parts)]
        return NumberTheoryResult(operation="factorize", a=a, b=None, factors=factors, steps=steps)

    # is_prime

    result_bool = bool(isprime(a))
    steps = [f"{a} is {'prime' if result_bool else 'not prime'}"]
    return NumberTheoryResult(
        operation="is_prime", a=a, b=None, result_bool=result_bool, steps=steps
    )


def _matrix_from_rows(rows: list[list[float]]):
    return Matrix([[Rational(str(value)) for value in row] for row in rows])


def _matrix_basis_latex(vectors: list[object]) -> str:
    if not vectors:
        return r"\{0\}"
    return (
        r"\operatorname{span}\left\{" + ", ".join(latex(vector) for vector in vectors) + r"\right\}"
    )


def compute_matrix(data: MatrixInput) -> MatrixResult:
    """Small-matrix ops via sympy.Matrix using exact rational entries."""
    from app.modules.math.solve.display import format_verified_latex

    mat = _matrix_from_rows(data.rows)
    square_ops = {"determinant", "inverse", "eigenvalues", "eigenvectors", "diagonalize"}
    if data.operation in square_ops and mat.rows != mat.cols:
        raise SolveServiceError(f"{data.operation} needs a square matrix")

    if data.operation == "determinant":
        det = mat.det()
        steps = [f"\\det = {latex(det)}"]
        return MatrixResult(operation="determinant", determinant=float(det), steps=steps)

    if data.operation == "inverse":
        det = mat.det()
        if det == 0:
            raise SolveServiceError("Matrix is singular (determinant is 0) — no inverse exists")
        inv = mat.inv()
        steps = [f"\\det = {latex(det)}", f"\\text{{inverse}} = {latex(inv)}"]
        return MatrixResult(
            operation="inverse", determinant=float(det), inverse_latex=latex(inv), steps=steps
        )

    if data.operation == "multiply":
        if data.rows_b is None:
            raise SolveServiceError("multiply needs a second matrix")
        other = _matrix_from_rows(data.rows_b)
        if mat.cols != other.rows:
            raise SolveServiceError("matrix multiply inner dimensions must agree")
        product = mat * other
        steps = [f"AB = {latex(product)}"]
        return MatrixResult(operation="multiply", result_latex=latex(product), steps=steps)

    if data.operation == "rref":
        reduced = mat.rref()[0]
        steps = [f"\\mathrm{{rref}} = {latex(reduced)}"]
        return MatrixResult(operation="rref", result_latex=latex(reduced), steps=steps)

    if data.operation == "rank":
        value = int(mat.rank())
        answer = str(value)
        return MatrixResult(
            operation="rank",
            result_latex=answer,
            steps=[f"\\operatorname{{rank}}(A) = {answer}"],
        )

    if data.operation == "nullspace":
        answer = _matrix_basis_latex(mat.nullspace())
        return MatrixResult(
            operation="nullspace",
            result_latex=answer,
            steps=[f"\\operatorname{{Null}}(A) = {answer}"],
        )

    if data.operation == "columnspace":
        answer = _matrix_basis_latex(mat.columnspace())
        return MatrixResult(
            operation="columnspace",
            result_latex=answer,
            steps=[f"\\operatorname{{Col}}(A) = {answer}"],
        )

    if data.operation == "rowspace":
        answer = _matrix_basis_latex(mat.rowspace())
        return MatrixResult(
            operation="rowspace",
            result_latex=answer,
            steps=[f"\\operatorname{{Row}}(A) = {answer}"],
        )

    if data.operation == "add":
        if data.rows_b is None:
            raise SolveServiceError("add needs a second matrix")
        other = _matrix_from_rows(data.rows_b)
        if mat.rows != other.rows or mat.cols != other.cols:
            raise SolveServiceError("matrix add needs matching shapes")
        summed = mat + other
        steps = [f"A+B = {latex(summed)}"]
        return MatrixResult(operation="add", result_latex=latex(summed), steps=steps)

    if data.operation == "transpose":
        transposed = mat.T
        steps = [f"A^{{T}} = {latex(transposed)}"]
        return MatrixResult(operation="transpose", result_latex=latex(transposed), steps=steps)

    if data.operation == "eigenvectors":
        parts: list[str] = []
        for value, _multiplicity, vectors in mat.eigenvects():
            eigenvalue = format_verified_latex(value)
            basis = _matrix_basis_latex(vectors)
            parts.append(rf"\lambda={eigenvalue}:\ {basis}")
        answer = r";\quad ".join(parts)
        return MatrixResult(
            operation="eigenvectors",
            result_latex=answer,
            steps=[f"\\text{{eigenspaces: }} {answer}"],
        )

    if data.operation == "diagonalize":
        try:
            p_matrix, d_matrix = mat.diagonalize()
        except Exception as exc:
            raise SolveServiceError("matrix is not diagonalizable") from exc
        answer = f"P={latex(p_matrix)},\\quad D={latex(d_matrix)}"
        steps = [f"A=PDP^{{-1}},\\quad {answer}"]
        return MatrixResult(operation="diagonalize", result_latex=answer, steps=steps)

    evals = mat.eigenvals()
    keys = sorted(evals.keys(), key=lambda value: (complex(value).real, complex(value).imag))
    answer = ", ".join(format_verified_latex(key) for key in keys)
    steps = [f"\\lambda = {answer}"]
    return MatrixResult(operation="eigenvalues", result_latex=answer, steps=steps)
