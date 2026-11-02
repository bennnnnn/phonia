"""School homework cues the math gate reads: percentages, rates, sequences, vectors, ...

Each is a ``NeedSignal`` (``need_signals.py``): a named predicate over the
prepared line and its lowercase form that runs no extractor.
"""

from __future__ import annotations

import re

from app.modules.math.match.calculus import y_prime_math_cue
from app.modules.math.match.need_signals import has_digit
from app.services.number_text import count_word_pattern
from app.services.text_match import has_any_word, has_equation, word_index

_CHANCE_WORD = re.compile(r"\b(?:probability|chance|likelihood)\b", re.IGNORECASE)
_COUNTED_OUTCOME = re.compile(
    rf"\b(?:\d{{1,3}}|{count_word_pattern()})\s+"
    r"(?:heads|tails|sixes)\b",
    re.IGNORECASE,
)


def _has_ordinal_term_cue(lower: str) -> bool:
    i = 0
    n = len(lower)
    while i < n:
        if lower[i].isdigit():
            if i > 0 and lower[i - 1] == ".":
                i += 1
                continue
            j = i
            while j < n and lower[j].isdigit():
                j += 1
            if lower[j : j + 2] in {"st", "nd", "rd", "th"}:
                k = j + 2
                while k < n and lower[k].isspace():
                    k += 1
                if lower.startswith("term", k):
                    return True
            i = j
        else:
            i += 1
    return False


def percent_cue(cleaned: str, lower: str) -> bool:
    """A percentage of, a change, interest, a mixture, a tax or a discount."""
    if not has_digit(cleaned):
        return False
    if "% of " in lower or "what percent" in lower or "what percentage" in lower:
        return True
    if "%" in cleaned and has_any_word(lower, ("increase", "increased", "decrease", "decreased")):
        return True
    if "%" in cleaned and (
        "compound interest" in lower
        or "simple interest" in lower
        or "compound amount" in lower
        # "$5000 invested at 4% interest compounded annually for 3 years"
        or ("compounded" in lower and "interest" in lower)
    ):
        return True
    if cleaned.count("%") == 2 and has_any_word(lower, ("mix", "mixed", "mixture")):
        return True
    # The charges ``tools/school/charges.py`` reads: "20% VAT on £50", "a 15% gratuity".
    charge = has_any_word(lower, ("vat", "gratuity")) or "service charge" in lower
    return "%" in cleaned and (
        charge or has_any_word(lower, ("tax", "tip", "discount", "off", "markup"))
    )


def everyday_cue(cleaned: str, lower: str) -> bool:
    """Ratios, work rates, proportion, cost, rounding, present value and conversions."""
    if not has_digit(cleaned):
        return False
    if "ratio" in lower and ":" in cleaned and has_any_word(lower, ("split", "share", "divide")):
        return True
    together = word_index(lower, "together") != -1
    if together and ("hour" in lower or "twice as many" in lower or "2 times as many" in lower):
        return True
    if "direct proportion" in lower or "inverse proportion" in lower:
        return True
    if word_index(lower, "cost") != -1 and word_index(lower, "if") != -1:
        return True
    if word_index(lower, "round") != -1 and ("decimal" in lower or "significant" in lower):
        return True
    if "present value" in lower or ("convert" in lower and " to " in lower):
        return True
    from app.modules.math.match.units import asked_conversion

    return asked_conversion(cleaned) is not None


def sequence_cue(cleaned: str, lower: str) -> bool:
    """A sequence's nth term, a sum of the first terms, or an infinite or Taylor series."""
    if has_digit(cleaned) and _has_ordinal_term_cue(lower):
        return True
    if ("sum of the first" in lower or "sum of first" in lower) and (
        has_any_word(lower, ("even", "odd")) or "," in cleaned
    ):
        return True
    if ("infinity" in lower or "infinite" in lower) and ("sum" in lower or "series" in lower):
        return True
    return (
        "taylor of " in lower or "maclaurin" in lower or ("taylor" in lower and "series" in lower)
    )


def identity_cue(cleaned: str, lower: str) -> bool:
    """An identity to prove or verify."""
    return has_equation(cleaned) and (
        "identity" in lower
        or "show that" in lower
        or "prove that" in lower
        or "verify that" in lower
    )


def curve_plot_cue(cleaned: str, lower: str) -> bool:
    """A polar or parametric curve to plot."""
    compact = lower.replace(" ", "")
    if (
        "r=" in compact
        and ("polar" in lower or "theta" in lower or "θ" in cleaned)
        and has_any_word(lower, ("graph", "plot", "polar", "sketch", "draw"))
    ):
        return True
    return (
        "x=" in compact
        and "y=" in compact
        and ("parametric" in lower or has_any_word(lower, ("graph", "plot")))
    )


def coordinate_cue(cleaned: str, lower: str) -> bool:
    """Lines, distances, midpoints, slopes and vectors given as coordinates."""
    if "equation of" in lower and "line" in lower and "(" in cleaned:
        return True
    if word_index(lower, "distance") != -1 and "(" in cleaned and "=" in cleaned:
        return True
    if (
        any(w in lower for w in ("unit vector", "projection of", "angle between"))
        and "<" in cleaned
    ):
        return True
    if any(w in lower for w in ("midpoint", "distance between", "slope of")) and "(" in cleaned:
        return True
    return any(w in lower for w in ("dot product", "cross product", "magnitude of <"))


def probability_cue(cleaned: str, lower: str) -> bool:
    """Distributions, Bayes, quartiles, a range of data, expectation and z-scores."""
    if "geometric" in lower and "k=" in lower.replace(" ", ""):
        return True
    if "poisson" in lower or has_any_word(lower, ("bayes", "complement")):
        return True
    if has_any_word(lower, ("quartiles", "percentile", "iqr", "interquartile")):
        return True
    if ("range of" in lower and "," in cleaned) or "binomial" in lower or "expected value" in lower:
        return True
    if _CHANCE_WORD.search(cleaned) and _COUNTED_OUTCOME.search(cleaned):
        # "exactly 2 heads in 4 coin flips": a fair coin or die, repeated.
        return True
    return "z-score" in lower or "z score" in lower


def structure_cue(cleaned: str, lower: str) -> bool:
    """Set operations, modular arithmetic, the remainder theorem, matrices, complex numbers."""
    if "{" in cleaned and has_any_word(lower, ("union", "intersection", "difference")):
        return True
    if "modular inverse" in lower or ("totient" in lower and has_digit(cleaned)):
        return True
    if "chinese remainder" in lower or word_index(lower, "crt") != -1:
        return True
    if "[[" in cleaned and ("transpose" in lower or word_index(lower, "add") != -1):
        return True
    return "modulus" in lower or "imaginary" in lower or "complex number" in lower


def calculus_cue(cleaned: str, lower: str) -> bool:
    """Multivariable and implicit calculus, partials and derivative notation."""
    if any(
        word in lower
        for word in (
            "gradient",
            "directional derivative",
            "divergence",
            "curl",
            "average value",
            "linear approximation",
            "implicit",
            "triple integral",
        )
    ):
        return True
    if "partial of " in lower or "partial derivative" in lower or " wrt" in lower:
        return True
    return "dy/dx" in lower or "day/dx" in lower or y_prime_math_cue(cleaned)


# ``sec``, ``csc`` and ``cot`` as calls: ``sec(60°)``, ``\\cot(\\frac{\\pi}{4})``, ``sec 60``,
# ``sec x``. Never ``4 sec`` (seconds), ``in a sec``, ``cotton`` or ``seconds``.
_RECIPROCAL_TRIG_CALL = re.compile(
    r"(?<![a-z])(?<!\ba )(?:sec|csc|cot)\s*(?:\(|\\|\d|π|pi\b|x\b|θ)"
)


def trig_cue(cleaned: str, lower: str) -> bool:
    """A trig function with an angle, or a triangle's area from two sides and an angle."""
    if "area" in lower and "triangle" in lower and "angle" in lower and "sides" in lower:
        return True
    has_trig_call = any(f"{fn}(" in lower or f"{fn} " in lower for fn in ("sin", "cos", "tan"))
    has_trig_call = has_trig_call or _RECIPROCAL_TRIG_CALL.search(lower) is not None
    return has_trig_call and ("°" in cleaned or has_digit(cleaned))
