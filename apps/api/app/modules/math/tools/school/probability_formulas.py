"""Probability asked for by its formula: geometric, Poisson, Bayes' theorem and the complement.

Extractor and verified block. ``probability.py`` tries this reader before its own and hands
these operations' blocks here.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import _exactly_n_numbers
from app.services.number_text import SIGNED_DECIMAL
from app.services.text_match import word_index
from app.services.workout import Workout, math_line, render_workout

_NAMED_PROBABILITY_NUMBER = rf"({SIGNED_DECIMAL})\s*(%|percent(?:age)?)?"


def _named_probability(cleaned: str, name: str) -> float | None:
    """Read ``sensitivity 95%`` and ``95% sensitivity`` as probabilities."""
    escaped = re.escape(name)
    after = re.search(
        rf"\b{escaped}\b\s*(?:(?:is|was|of)\s+|[=:]\s*)?{_NAMED_PROBABILITY_NUMBER}",
        cleaned,
        re.IGNORECASE,
    )
    before = re.search(
        rf"{_NAMED_PROBABILITY_NUMBER}\s*\b{escaped}\b",
        cleaned,
        re.IGNORECASE,
    )
    match = after or before
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError, OverflowError):
        return None
    percent_marked = match.group(2) is not None
    if percent_marked or value > 1:
        value /= 100.0
    return value if math.isfinite(value) and 0 <= value <= 1 else None


_GEOMETRIC_NOT_DISTRIBUTION = re.compile(
    r"\bgeometric\s+(?:sequence|series|progression|mean|growth|shape|figure)s?\b"
)


def _medical_bayes_values(cleaned: str) -> list[float] | None:
    """Return Bayes inputs as prior, true-positive rate, false-positive rate."""
    prevalence = _named_probability(cleaned, "prevalence")
    sensitivity = _named_probability(cleaned, "sensitivity")
    specificity = _named_probability(cleaned, "specificity")
    if prevalence is None or sensitivity is None or specificity is None:
        return None
    return [prevalence, sensitivity, 1.0 - specificity]


def extract_probability_formulas(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    medical_bayes = _medical_bayes_values(cleaned)
    if medical_bayes is not None:
        return MathIntent(
            kind="probability",
            school_op="bayes",
            vec_a=medical_bayes,
            operation="solve",
        )
    compact = lower.replace(" ", "")
    # "the 6th term of the geometric sequence 2, 6, 18" is a sequence, not the distribution.
    if "geometric" in lower and not _GEOMETRIC_NOT_DISTRIBUTION.search(lower):
        k_at = compact.find("k=")
        p_at = compact.find("p=")
        if k_at == -1 or p_at == -1 or "n=" in compact:
            return MathIntent(kind="probability", school_op="geometric", operation="solve")
        values = _exactly_n_numbers(cleaned, 2)
        if values is None:
            return MathIntent(kind="probability", school_op="geometric", operation="solve")
        k = values[0] if k_at < p_at else values[1]
        p = values[1] if k_at < p_at else values[0]
        if not k.is_integer():
            return MathIntent(kind="probability", school_op="geometric", operation="solve")
        return MathIntent(
            kind="probability",
            school_op="geometric",
            combo_k=int(k),
            percent_base=p,
            operation="solve",
        )
    if "poisson" in lower:
        k_at = compact.find("k=")
        lam_at = compact.find("lambda=")
        if lam_at == -1:
            lam_at = compact.find("λ=")
        if k_at == -1 or lam_at == -1:
            return MathIntent(kind="probability", school_op="poisson", operation="solve")
        values = _exactly_n_numbers(cleaned, 2)
        if values is None:
            return MathIntent(kind="probability", school_op="poisson", operation="solve")
        k = values[0] if k_at < lam_at else values[1]
        lam = values[1] if k_at < lam_at else values[0]
        if not k.is_integer():
            return MathIntent(kind="probability", school_op="poisson", operation="solve")
        return MathIntent(
            kind="probability",
            school_op="poisson",
            combo_k=int(k),
            percent_base=lam,
            operation="solve",
        )
    if word_index(lower, "bayes") != -1 or "p(a|b)" in compact:
        values = _exactly_n_numbers(cleaned, 3)
        if values is None:
            return MathIntent(kind="probability", school_op="bayes", operation="solve")
        return MathIntent(
            kind="probability",
            school_op="bayes",
            vec_a=values,
            operation="solve",
        )
    if word_index(lower, "complement") != -1:
        values = _exactly_n_numbers(cleaned, 1)
        if values is None:
            return MathIntent(kind="probability", school_op="complement", operation="solve")
        return MathIntent(
            kind="probability",
            school_op="complement",
            percent_base=values[0],
            operation="solve",
        )
    return None


def probability_formula_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if (
        intent.school_op == "geometric"
        and intent.combo_k is not None
        and intent.percent_base is not None
    ):
        answer = math_formulas.geometric_pmf(intent.combo_k, intent.percent_base)
        lines.append(f"P(X={intent.combo_k}) = {answer}")
        return finish_with_answer(lines, answer)
    if (
        intent.school_op == "poisson"
        and intent.combo_k is not None
        and intent.percent_base is not None
    ):
        answer = math_formulas.poisson_pmf(intent.combo_k, intent.percent_base)
        lines.append(f"P(X={intent.combo_k}) = {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "complement" and intent.percent_base is not None:
        answer = math_formulas.complement_probability(intent.percent_base)
        lines.append(f"1-P = {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "bayes" and intent.vec_a and len(intent.vec_a) == 3:
        prior, hit, false_positive = intent.vec_a
        posterior = math_formulas.bayes_probability(prior, hit, false_positive)
        evidence = hit * prior + false_positive * (1.0 - prior)
        request_text = (intent._request_text or "").lower()
        medical = all(name in request_text for name in ("sensitivity", "specificity", "prevalence"))
        if medical:
            answer = f"{float(posterior) * 100:.6g}\\%"
            direct = render_workout(
                Workout(
                    given=(
                        math_line(f"P(D) = {prior:g}", "prevalence"),
                        math_line(f"P(+\\mid D) = {hit:g}", "sensitivity"),
                        math_line(f"P(-\\mid \\neg D) = {1.0 - false_positive:g}", "specificity"),
                    ),
                    find=(math_line("P(D\\mid +)"),),
                    formula=(
                        math_line("P(D\\mid +) = \\frac{P(+\\mid D)P(D)}{P(+)}", "Bayes' theorem"),
                    ),
                    substitution=(
                        math_line(
                            f"P(+\\mid \\neg D) = 1 - {1.0 - false_positive:g}"
                            f" = {false_positive:g}",
                            "false-positive rate",
                        ),
                        math_line(
                            f"P(+\\cap D) = ({hit:g})({prior:g}) = {hit * prior:g}",
                            "true positives",
                        ),
                        math_line(
                            f"P(+) = ({hit:g})({prior:g}) + ({false_positive:g})(1-{prior:g})"
                            f" = {evidence:g}",
                            "every positive result",
                        ),
                        math_line(
                            f"P(D\\mid +) = \\frac{{({hit:g})({prior:g})}}{{{evidence:g}}}"
                            f" = {posterior}"
                        ),
                        math_line(f"\\approx {answer}"),
                    ),
                ),
                answer,
            )
        else:
            answer = posterior
            direct = render_workout(
                Workout(
                    given=(
                        math_line(f"P(A) = {prior:g}"),
                        math_line(f"P(B\\mid A) = {hit:g}"),
                        math_line(f"P(B\\mid \\neg A) = {false_positive:g}"),
                    ),
                    find=(math_line("P(A\\mid B)"),),
                    formula=(
                        math_line(
                            "P(A\\mid B)=\\frac{P(B\\mid A)P(A)}"
                            "{P(B\\mid A)P(A)+P(B\\mid \\neg A)P(\\neg A)}",
                            "Bayes' theorem",
                        ),
                    ),
                    substitution=(
                        math_line(
                            f"P(A\\mid B)=\\frac{{({hit:g})({prior:g})}}"
                            f"{{({hit:g})({prior:g})+({false_positive:g})(1-{prior:g})}}={posterior}"
                        ),
                    ),
                ),
                answer,
            )
        lines.append(f"P(A|B) = {posterior}")
        return replace(finish_with_answer(lines, answer), direct_reply=direct)
    return None
