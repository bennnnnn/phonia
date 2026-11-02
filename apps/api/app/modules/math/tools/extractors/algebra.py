"""Algebra and numerical-method intent extractors."""

from __future__ import annotations

import re

from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.extractors.stated import (
    already_solved,
    lists_alternatives,
    names_a_constant,
    one_of_several_answers,
)
from app.modules.math.tools.function_def import substituted_eval_expr

_SOLVE_FOR_VAR_RE = re.compile(
    r"\bsolve\s+for\s+(?:the\s+value\s+of\s+)?([a-zA-Z])(?![a-zA-Z])",
    re.IGNORECASE,
)
_FIND_VAR_RE = re.compile(
    r"\bfind\s+(?:the\s+value\s+of\s+)?([a-zA-Z])(?![a-zA-Z])",
    re.IGNORECASE,
)
_TRAILING_FOR_VAR_RE = re.compile(
    r"\bfor\s+([a-zA-Z])(?![a-zA-Z])\s*$",
    re.IGNORECASE,
)
# Whole-word cues that mean "solve this" even mid-sentence (`show me how to
# solve 2x+3=7`). `find` is not here — "how do I find the slope of y=x^2"
# is not a solve request.
_SOLVE_WORD_CUES = ("solve", "isolate", "factor", "expand")
_LEADING_SOLVE_CUES = (
    "find",
    "calculate",
    "compute",
    "evaluate",
    "determine",
    "simplify",
    "what is",
    "what's",
)
_PLOT_VERB_PREFIXES = (
    "draw ",
    "sketch ",
    "visualize ",
    "visualise ",
    "chart ",
    "show ",
    "graph ",
    "plot ",
)
_TRAILING_OK_WORDS = frozenset({"please", "thanks", "now", "quickly", "briefly", "here"})
_EQ_BIND_PREFIXES = ("let ", "set ", "given ", "if ", "when ", "where ")


def _has_whole_word(cleaned: str, word: str) -> bool:
    lower = cleaned.lower()
    start = 0
    n = len(word)
    while True:
        idx = lower.find(word, start)
        if idx == -1:
            return False
        before_ok = idx == 0 or not lower[idx - 1].isalpha()
        after = idx + n
        after_ok = after >= len(lower) or not lower[after].isalpha()
        if before_ok and after_ok:
            return True
        start = idx + 1


def _leading_after_polite(cleaned: str) -> str:
    s = cleaned.strip()
    low = s.lower()
    for polite in ("please ", "can you ", "could you "):
        if low.startswith(polite):
            s = s[len(polite) :].lstrip()
            low = s.lower()
    return low


def _has_solve_cue(cleaned: str, equation_text: str = "") -> bool:
    """True for an imperative solve / requested variable, not a buried cue."""
    if equation_text and _requested_variable(cleaned, equation_text) is not None:
        return True
    if any(_has_whole_word(cleaned, word) for word in _SOLVE_WORD_CUES):
        return True
    low = _leading_after_polite(cleaned)
    for cue in _LEADING_SOLVE_CUES:
        if low.startswith(cue) and (len(low) == len(cue) or not low[len(cue)].isalpha()):
            return True
    return False


def _blank_extracted_equation(core: str, lhs: str, rhs: str) -> str:
    """Remove the extracted ``lhs=rhs`` span so leftover English can be counted.

    Do not ``str.replace`` a 1-letter lhs — that hits the ``y`` in ``why``.
    """
    eq = core.find("=")
    if eq == -1:
        return core
    start = core.rfind(lhs, 0, eq)
    end = core.find(rhs, eq + 1)
    if start == -1 or end == -1:
        return core
    return core[:start] + " " + core[end + len(rhs) :]


def _leftover_prose_blocks_solve(cleaned: str, lhs: str, rhs: str) -> bool:
    """True when English around the extracted sides is a sentence, not a glue.

    ``2x+3=7please`` / ``2x + 3 = 7 please`` still solve. ``tell me about
    y=x^2`` does not.
    """
    if _has_solve_cue(cleaned, f"{lhs}={rhs}"):
        return False
    core = _equation_core_after_leadin(cleaned)
    s = _blank_extracted_equation(core, lhs, rhs)
    words = [w.lower().strip(".,?!:;") for w in s.split() if w.strip(".,?!=:;")]
    english = [w for w in words if len(w) >= 3 and w.isalpha() and w not in _TRAILING_OK_WORDS]
    # One leftover word is glue (``please`` is already ignored). A word that
    # only contains a command, such as ``resolved``, is not a command, so the
    # equation is not solved.
    if english:
        from app.modules.math.match.scan import has_math_keyword

        if not has_math_keyword(cleaned.lower()):
            return True
    return len(english) >= 2


# Lagrange (y', y'') and Leibniz (d^2y/dx^2, d2y/dx2) derivative marks.
_DERIVATIVE_MARK_RE = re.compile(r"[A-Za-z]\s*['\u2032\u2033]|\bd\s*\^?\s*2\s*[A-Za-z]\s*/")


def _derivative_term_dropped(cleaned: str, lhs: str, rhs: str) -> bool:
    """True when a derivative term was left behind by the extracted sides.

    ``solve y'' + y = 0`` used to extract ``+ y = 0``, silently dropping the
    ``y''``. The remnant solved to a confident, verified ``y = 0`` — the worst
    result this pipeline can produce, because the block tells the model not to
    recompute. Second-order ODEs belong to the dsolve path in
    ``math.tools.school``; when that path declines, the answer is the model's
    to give unverified, never algebra's to invent.

    Scoped to derivative marks on purpose. A general "did we consume the whole
    equation" check needs the extractor to report the span it consumed: the
    residue legitimately holds qualifiers like ``for x:``, ``for 0<=x<=2*pi``
    or ``with a proof``, which are not dropped math.
    """
    if not _DERIVATIVE_MARK_RE.search(cleaned):
        return False
    residue = _blank_extracted_equation(_equation_core_after_leadin(cleaned), lhs, rhs)
    return bool(_DERIVATIVE_MARK_RE.search(residue))


def _has_unclaimed_plot_verb(cleaned: str) -> bool:
    """Plot phrasing that missed ``graph_expr`` must not fall through to solve."""
    from app.modules.math import match as mtm
    from app.modules.math.match.graph import _find_unprefixed_phrase

    if mtm.graph_expr(cleaned) is not None:
        return False
    if _has_solve_cue(cleaned):
        return False
    lower = cleaned.lower()
    return any(_find_unprefixed_phrase(lower, prefix) != -1 for prefix in _PLOT_VERB_PREFIXES)


def _equation_core_after_leadin(cleaned: str) -> str:
    from app.modules.math.solve.extract_eq import _strip_leading_filler

    s = _strip_leading_filler(cleaned)
    prev = None
    while prev != s:
        prev = s
        low = s.lower()
        for prefix in _EQ_BIND_PREFIXES:
            if low.startswith(prefix):
                s = s[len(prefix) :].lstrip()
                break
        else:
            break
    return s


_LEADIN_WORDS = frozenset(
    {
        "solve",
        "for",
        "find",
        "the",
        "value",
        "of",
        "in",
        "when",
        "given",
        "if",
        "such",
        "that",
        "where",
        "with",
        "please",
        "let",
        "us",
        "determine",
        "calculate",
        "compute",
        "get",
        "isolate",
        "express",
        "what",
        "is",
        "are",
        "does",
        "can",
        "you",
        "show",
        "tell",
    }
)


def _requested_variable(cleaned: str, equation_text: str) -> str | None:
    """Return the variable the user explicitly asked to solve for, or None."""
    m = (
        _SOLVE_FOR_VAR_RE.search(cleaned)
        or _FIND_VAR_RE.search(cleaned)
        or _TRAILING_FOR_VAR_RE.search(cleaned)
    )
    if m is None:
        return None
    var = m.group(1)
    tokens = re.findall(r"[a-zA-Z]+", equation_text)
    kept = [t for t in tokens if t.lower() not in _LEADIN_WORDS]
    letters = {c for t in kept for c in t if c.isalpha()}
    # ``e``/``E`` are Euler's number in guess_variables — still honor an
    # explicit "solve for e" when that letter is actually in the equation.
    if var in {"e", "E"}:
        return var if var in letters else None
    letters.discard("e")
    letters.discard("E")
    return var if var in letters else None


def _extract_numerical_method_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if not ("newton" in lower or "numerically" in lower or "root of" in lower):
        return None
    # Deferred: direct_newton loads direct_calculus, which loads extract, which loads this.
    from app.modules.math.tools.direct_newton import _parse_newton_guess, _strip_newton_leadin

    guess, text_for_eq = _parse_newton_guess(cleaned)
    text_for_eq = _strip_newton_leadin(text_for_eq)
    newton_pairs = math_solve.try_extract_equations_from_text(text_for_eq)
    if not newton_pairs:
        return None
    lhs, rhs = newton_pairs[0]
    rhs_is_zero = rhs.strip() in ("0", "0.0")
    expr = lhs if rhs_is_zero else f"({lhs})-({rhs})"
    variables = math_solve.guess_variables(f"{lhs} {rhs}")
    var = variables[0] if variables else "x"
    return MathIntent(
        kind="numerical_method",
        expr=expr,
        variable=var,
        newton_guess=float(guess),
        operation="newton",
    )


def _extract_matrix_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm
    from app.modules.math.match.discrete import bracket_matrices

    signal = mtm.matrix_signal(cleaned)
    if signal is None:
        return None
    op, rows = signal
    rows_b = None
    if op in {"multiply", "add"}:
        matrices = bracket_matrices(cleaned)
        if matrices is None or len(matrices) != 2:
            return None
        rows, rows_b = matrices[0], matrices[1]
    return MathIntent(
        kind="matrix",
        matrix_op=op,
        matrix_rows=rows,
        matrix_rows_b=rows_b,
        operation="solve",
    )


def _primary_equation_pair(eq_pairs: list[tuple[str, str]]) -> tuple[str, str]:
    """Pick the problem statement from a worked solution (steps + roots).

    A paste like ``2x^2-7x+3=0`` then ``2x-1=0`` / ``x-3=0`` is one quadratic,
    not three simultaneous equations. Prefer the longest ``= 0`` polynomial, else the first.
    """
    zeros = [(lhs, rhs) for lhs, rhs in eq_pairs if rhs.strip() in {"0", "0.0"}]
    pool = zeros or eq_pairs[:1]
    return max(pool, key=lambda pair: (pair[0].count("^"), len(pair[0])))


# SystemOfEquationsInput allows at most four equations. A longer system
# must be declined whole; slicing to four verifies a different problem.
_MAX_SYSTEM_EQUATIONS = 4


def oversized_system(text: str) -> bool:
    """True when the text is a multi-variable system longer than the solver allows."""
    eq_pairs = math_solve.try_extract_equations_from_text(text)
    if len(eq_pairs) <= _MAX_SYSTEM_EQUATIONS:
        return False
    all_text = " ".join(f"{lhs} {rhs}" for lhs, rhs in eq_pairs)
    return len(math_solve.guess_variables(all_text)) >= 2


def _extract_system_intent(cleaned: str) -> MathIntent | None:
    eq_pairs = math_solve.try_extract_equations_from_text(cleaned)
    if len(eq_pairs) < 2:
        return None
    # ``x = 3, y = 1`` lists values. Nothing is left to solve, and solving
    # it would certify whatever the values are.
    if all(already_solved(lhs, rhs) for lhs, rhs in eq_pairs) or lists_alternatives(cleaned):
        return None
    # A system is solved as a system: the single-equation branch below reads only the
    # first clause, and would answer the others' question with full "verified"
    # confidence while ignoring them.
    all_text = " ".join(f"{lhs} {rhs}" for lhs, rhs in eq_pairs)
    defined = [name for lhs, _ in eq_pairs if (name := math_solve.defined_variable(lhs))]
    variables = [*dict.fromkeys(defined), *math_solve.guess_variables(all_text)]
    # One variable + several =0 lines is factoring / "set each factor to 0",
    # not a simultaneous system. Treating 2x-1=0 AND x-3=0 as a system
    # attaches ```answer no solution while the quadratic is solved.
    if len(variables) < 2:
        return None
    if len(eq_pairs) > _MAX_SYSTEM_EQUATIONS:
        return None
    # "a = 3, b = 4, find c" asks for a letter no equation contains; restating
    # the givens is not an answer to it.
    asked = _SOLVE_FOR_VAR_RE.search(cleaned) or _FIND_VAR_RE.search(cleaned)
    if asked is not None and asked.group(1) not in variables:
        return None
    return MathIntent(
        kind="system",
        system_equations=eq_pairs,
        system_variables=variables,
        operation="solve",
    )


def _extract_equation_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math.response_intent import (
        MathMethod,
        MathResponseMode,
        classify_math_response_intent,
    )
    from app.modules.math.tools.lesson import strip_lesson_prefixes

    lower = cleaned.lower()
    response_intent = classify_math_response_intent(cleaned)
    if response_intent.mode == MathResponseMode.EXPLAIN and not any(
        cue in lower for cue in (" solve ", "solve ", " find ", "calculate ", " step", "working")
    ):
        # “Explain why y=mx+b” asks about a statement; it does not ask Recall
        # to solve that equality for one of its symbols.
        return None
    requested_method = (
        "quadratic_formula"
        if response_intent.requested_method == MathMethod.QUADRATIC_FORMULA
        else "factoring"
        if response_intent.requested_method == MathMethod.FACTORING
        else None
    )
    if requested_method is None and "decimal approximation" in lower and "exact" in lower:
        requested_method = "exact_and_decimal"
    probe = strip_lesson_prefixes(cleaned)
    if _has_unclaimed_plot_verb(probe):
        return None
    eq_pairs = math_solve.try_extract_equations_from_text(probe)
    if not eq_pairs:
        return None
    # Let-binding + "what is x+2" is arithmetic after substitute, not solve x=5.
    if substituted_eval_expr(probe) is not None:
        return None
    lhs, rhs = eq_pairs[0] if len(eq_pairs) == 1 else _primary_equation_pair(eq_pairs)
    from app.modules.math.tools.expr_rewrite import math_expr_or_none

    if math_expr_or_none(lhs) is None or math_expr_or_none(rhs) is None:
        return None
    if (
        already_solved(lhs, rhs)
        or names_a_constant(lhs, rhs)
        or one_of_several_answers(lhs, eq_pairs)
    ):
        return None
    if _leftover_prose_blocks_solve(probe, lhs, rhs):
        return None
    if _derivative_term_dropped(probe, lhs, rhs):
        return None
    variables = math_solve.guess_variables(lhs + rhs)
    requested = _requested_variable(probe, lhs + rhs) or math_solve.defined_variable(lhs, rhs)
    # In a single school equation, x is the conventional unknown and other
    # letters are parameters unless the learner explicitly names a target.
    # Alphabetical selection made ``solve ax=5`` solve for a instead of x.
    variable = requested or ("x" if "x" in variables else variables[0] if variables else "x")
    return MathIntent(
        kind="equation",
        lhs=lhs,
        rhs=rhs,
        operation="solve",
        variable=variable,
        school_op=requested_method,
    )


def _extract_inequality_intent(cleaned: str) -> MathIntent | None:
    # Inequality — only reached when a math keyword already matched (this
    # function is called solely from needs_symbolic_math-gated paths), so bare
    # < / > here is safe from prose false-positives like "less than 5 minutes".
    probe = _strip_number_line_presentation(cleaned)
    compound = math_solve.try_extract_compound_inequality_from_text(probe)
    if compound is not None:
        low, low_op, mid, high_op, high = compound
        variables = math_solve.guess_variables(f"{low} {mid} {high}")
        if len(variables) > 1:  # "0 < y < 2x" bounds one unknown by another
            return None
        requested = _requested_variable(probe, f"{low} {mid} {high}")
        variable = requested or (variables[0] if variables else "x")
        return MathIntent(
            kind="inequality",
            lower=low,
            lhs=mid,
            rhs=high,
            comparator=low_op,
            comparator_upper=high_op,
            operation="solve",
            variable=variable,
        )
    ineq = math_solve.try_extract_inequality_from_text(probe)
    if not ineq:
        return None
    lhs, rhs, comparator = ineq
    variables = math_solve.guess_variables(lhs + rhs)
    requested = _requested_variable(probe, lhs + rhs)
    variable = requested or (variables[0] if variables else "x")
    return MathIntent(
        kind="inequality",
        lhs=lhs,
        rhs=rhs,
        comparator=comparator,
        operation="solve",
        variable=variable,
    )


def _strip_number_line_presentation(text: str) -> str:
    """Remove a diagram-only suffix without changing the inequality itself."""
    lower = text.lower().rstrip(".?!")
    suffixes = (
        " and show the answer on a number line",
        " and show it on a number line",
        " and graph the answer on a number line",
        " and graph it on a number line",
    )
    for suffix in suffixes:
        if lower.endswith(suffix):
            return text[: len(lower) - len(suffix)].rstrip()
    return text


PRE_DISCRETE_ALGEBRA_EXTRACTORS = (_extract_numerical_method_intent,)
ALGEBRA_EXTRACTORS = (
    _extract_matrix_intent,
    _extract_system_intent,
    _extract_equation_intent,
    _extract_inequality_intent,
)
