"""Sequence extractors and verified blocks."""

from __future__ import annotations

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.number_text import DECIMAL_LITERAL
from app.services.text_match import word_index

_SEQUENCE_LIST_MAX = 20
_SEQUENCE_N_MAX = 10_000


_ORDINAL_SUFFIXES = ("st", "nd", "rd", "th")


def _read_leading_int(text: str) -> tuple[int, int] | None:
    i = 0
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n or not text[i].isdigit():
        return None
    j = i
    while j < n and text[j].isdigit():
        j += 1
    if j < n and text[j] in ".":
        return None
    value = int(text[i:j])
    return value, j


def _ordinal_term_n(lower: str) -> int | None:
    i = 0
    n = len(lower)
    found: int | None = None
    while i < n:
        if lower[i].isdigit():
            if i > 0 and lower[i - 1] == ".":
                i += 1
                continue
            j = i
            while j < n and lower[j].isdigit():
                j += 1
            suffix = lower[j : j + 2]
            if suffix in _ORDINAL_SUFFIXES:
                k = j + 2
                while k < n and lower[k].isspace():
                    k += 1
                if lower.startswith("term", k):
                    value = int(lower[i:j])
                    if found is not None:
                        return None
                    found = value
            i = j
        else:
            i += 1
    return found


def _sequence_sum_n(lower: str) -> int | None:
    for cue in ("sum of the first", "sum of first"):
        idx = lower.find(cue)
        if idx == -1:
            continue
        parsed = _read_leading_int(lower[idx + len(cue) :])
        if parsed is None:
            return None
        return parsed[0]
    return None


def _named_even_odd_terms(lower: str) -> list[float] | None:
    has_even = word_index(lower, "even") != -1
    has_odd = word_index(lower, "odd") != -1
    if has_even == has_odd:
        return None
    if "number" not in lower:
        return None
    if has_even:
        return [2.0, 4.0]
    return [1.0, 3.0]


def _listed_sequence_terms(cleaned: str, lower: str) -> list[float] | None:
    idx = lower.rfind(" of ")
    if idx == -1:
        return None
    from app.modules.math.match.discrete import numeric_data_values

    numbers = numeric_data_values(cleaned[idx + 4 :])
    if numbers is None or len(numbers) < 3 or len(numbers) > _SEQUENCE_LIST_MAX:
        return None
    return numbers


def _extract_sequence_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    sum_n = _sequence_sum_n(lower)
    term_n = _ordinal_term_n(lower)
    if sum_n is not None:
        if term_n is not None and term_n != sum_n:
            return None
        n = sum_n
        op = "sequence_sum"
    elif term_n is not None:
        n = term_n
        op = "sequence_nth"
    else:
        return None
    if n < 1 or n > _SEQUENCE_N_MAX:
        return None
    named = _named_even_odd_terms(lower) if sum_n is not None else None
    listed = None if named is not None else _listed_sequence_terms(cleaned, lower)
    terms = named if named is not None else listed
    if terms is None:
        return None
    if not math_school.is_ap_or_gp(terms):
        return None
    expected = 1 if named is not None else 1 + len(terms)
    if len(list(DECIMAL_LITERAL.finditer(cleaned))) != expected:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op=op,
        stats_numbers=terms,
        combo_n=n,
        operation="solve",
    )


def extract_infinite_geometric(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "infinity" not in lower and "infinite" not in lower:
        return None
    if "sum" not in lower and "series" not in lower:
        return None
    from app.modules.math.formulas import is_convergent_geometric
    from app.modules.math.match.discrete import numeric_data_values

    idx = lower.rfind(" of ")
    if idx == -1:
        return None
    terms = numeric_data_values(cleaned[idx + 4 :])
    if terms is None or len(terms) < 3:
        return None
    if len(list(DECIMAL_LITERAL.finditer(cleaned))) != len(terms):
        return None
    if not is_convergent_geometric(terms):
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="infinite_gp",
        stats_numbers=terms,
        operation="solve",
    )


def _block_infinite_gp(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if intent.stats_numbers is None:
        return None
    answer = math_formulas.infinite_geometric_sum(intent.stats_numbers)
    lines.append(f"Infinite GP sum = {answer}")
    return finish_with_answer(lines, answer)


def _block_sequence(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.stats_numbers is None or intent.combo_n is None:
        return None
    if intent.school_op == "sequence_nth":
        answer = math_school.sequence_nth(intent.stats_numbers, intent.combo_n)
        lines.append(f"Term {intent.combo_n} = {answer}")
    else:
        answer = math_school.sequence_sum(intent.stats_numbers, intent.combo_n)
        lines.append(f"Sum of first {intent.combo_n} terms = {answer}")
    return finish_with_answer(lines, answer)
