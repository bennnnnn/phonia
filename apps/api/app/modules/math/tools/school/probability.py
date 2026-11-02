"""Probability extractor and verified block."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from fractions import Fraction

from app.core.config import Settings
from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.extractors.readings import read
from app.modules.math.tools.school._parse import count_value
from app.modules.math.tools.school.probability_formulas import (
    extract_probability_formulas,
    probability_formula_block,
)
from app.modules.math.tools.school.single_draw import fraction_tex
from app.services.number_text import SIGNED_DECIMAL, count_word_pattern
from app.services.workout import Workout, math_line, render_workout

_BINOMIAL_PARAM = re.compile(
    rf"\b([nkp])\s*=\s*({SIGNED_DECIMAL}(?:\s*/\s*{SIGNED_DECIMAL})?)(?=\s|[,;.!?]|$)",
    re.IGNORECASE,
)
_PROBABILITY_LIST = re.compile(r"\[([^\[\]]+)\]")
_DICE_CONDITIONAL_SUM = re.compile(
    r"^\s*(?:two|2)\s+fair\s+dice\s+are\s+(?:rolled|thrown)\s*[.,;]?\s*"
    r"(?:given|knowing)(?:\s+that)?\s+(?:the\s+)?sum\s+is\s+"
    r"(at\s+least|at\s+most|greater\s+than|less\s+than|exactly|equal\s+to)\s+"
    r"(\d{1,2})\s*[.,;?]?\s*"
    r"(?:what\s+is|find|calculate|compute)\s+(?:the\s+)?probability"
    r"(?:\s+(?:that|of))?\s+(?:the\s+)?sum\s+is\s+(?:exactly|equal\s+to)\s+"
    r"(\d{1,2})"
    r"(?:\s*[?.]\s*(?:show|list)(?:\s+me)?(?:\s+the)?\s+conditional\s+"
    r"sample\s+space)?\s*[?.]?\s*$",
    re.IGNORECASE,
)


_COUNT = r"(\d{1,3}|" + count_word_pattern() + ")"
_CHANCE = re.compile(r"\b(?:probability|chance|likelihood)\b", re.IGNORECASE)
_NOT_EXACTLY = re.compile(
    r"\b(?:at\s+least|at\s+most|more\s+than|fewer\s+than|less\s+than|no\s+more\s+than|"
    r"or\s+more|or\s+fewer|or\s+less)\b",
    re.IGNORECASE,
)
# "2 heads in 4 (coin) flips", "3 sixes in 5 rolls (of a die)".
_TRIALS_IN = re.compile(
    rf"\b(?:exactly\s+)?{_COUNT}\s+(heads|tails|sixes)\s+(?:in|from|out\s+of|with)\s+"
    rf"{_COUNT}\s+(?:fair\s+)?(?:coin\s+|die\s+|dice\s+)?(flips|tosses|throws|rolls)\b",
    re.IGNORECASE,
)
# "flip a coin 4 times ... exactly 2 heads" in either order.
_TRIALS_REPEAT = re.compile(
    rf"\b(?:flip|toss|roll|throw)(?:ped|ed|s)?\s+an?\s+(?:fair\s+)?(coin|die)\s+{_COUNT}\s+times\b"
    rf"|\ban?\s+(?:fair\s+)?(coin|die)\s+is\s+(?:flipped|tossed|rolled|thrown)\s+{_COUNT}\s+times\b",
    re.IGNORECASE,
)
_TRIALS_COUNTED = re.compile(rf"\b(?:exactly\s+)?{_COUNT}\s+(heads|tails|sixes)\b", re.IGNORECASE)
# The trials are read wherever they stand, so a coin or die the question says is not the
# fair six-sided one, or a chance it states, is looked for in the whole of it.
_NOT_FAIR_DEVICE = re.compile(
    r"\b(?:biased|loaded|weighted|unfair|crooked|rigged)\b|\bnot\s+(?:a\s+)?fair\b"
    r"|\b(?!six\b|6\b)\w+[- ]sided\b|\b(?:tetrahedral|octahedral|dodecahedral|icosahedral)\b"
    r"|(?<![\w.])(?:0?\.\d+|\d+(?:\.\d+)?\s*%|\d+\s*/\s*\d+)(?!\w|\.\d)",
    re.IGNORECASE,
)


# The whole request, for the direct reply: nothing else may ride along.
_TRIALS_QUESTION = re.compile(
    rf"(?:what(?:'s|\s+is)\s+)?(?:the\s+)?(?:probability|chance|likelihood)\s+"
    r"(?:of\s+)?(?:getting\s+|rolling\s+|flipping\s+|tossing\s+)?(?:exactly\s+)?"
    rf"{_COUNT}\s+(?:heads|tails|sixes)\s+(?:in|from|out\s+of|with)\s+{_COUNT}\s+"
    r"(?:fair\s+)?(?:coin\s+|die\s+|dice\s+)?(?:flips|tosses|throws|rolls)"
    r"(?:\s+of\s+an?\s+(?:fair\s+)?(?:coin|die))?\s*[?.]?",
    re.IGNORECASE,
)
_TRIALS_SETUP = re.compile(
    rf"an?\s+(?:fair\s+)?(?:coin|die)\s+is\s+(?:flipped|tossed|rolled|thrown)\s+{_COUNT}\s+"
    r"times\s*[.,]?\s*(?:what\s+is\s+|find\s+)?(?:the\s+)?(?:probability|chance)\s+"
    rf"(?:of\s+)?(?:getting\s+|rolling\s+)?(?:exactly\s+)?{_COUNT}\s+(?:heads|tails|sixes)"
    r"\s*[?.]?",
    re.IGNORECASE,
)


# "probability of at least one head in 3 coin flips": 1 - P(none).
_AT_LEAST_ONE = re.compile(
    r"(?:what(?:'s|\s+is)\s+)?(?:the\s+)?(?:probability|chance|likelihood)\s+(?:of\s+)?"
    r"(?:getting\s+|rolling\s+|flipping\s+|tossing\s+)?at\s+least\s+(?:one|1|a)\s+"
    rf"(head|tail|six)s?\s+(?:in|from|out\s+of|with)\s+{_COUNT}\s+(?:fair\s+)?"
    r"(?:coin\s+|die\s+|dice\s+)?(flips|tosses|throws|rolls)"
    r"(?:\s+of\s+an?\s+(?:fair\s+)?(?:coin|die))?\s*[?.]?",
    re.IGNORECASE,
)
# "expected value of a fair die roll": the mean of the faces 1 to 6.
_FAIR_DIE_EXPECTATION = re.compile(
    r"(?:what(?:'s|\s+is)\s+|find\s+|calculate\s+)?(?:the\s+)?expected\s+value\s+"
    r"(?:of\s+|when\s+(?:you\s+)?)?(?:rolling\s+|roll\s+)?(?:a\s+|one\s+|the\s+)?(?:single\s+)?"
    r"(?:roll\s+of\s+a\s+)?(?:fair\s+)?(?:six-sided\s+|6-sided\s+|standard\s+)?die"
    r"(?:\s+roll)?\s*[?.]?",
    re.IGNORECASE,
)


def extract_at_least_one_intent(cleaned: str) -> MathIntent | None:
    match = _AT_LEAST_ONE.fullmatch(" ".join(cleaned.split()))
    if match is None:
        return None
    outcome, n, trial = match.group(1).lower(), count_value(match.group(2)), match.group(3).lower()
    die = outcome == "six"
    if (die and trial in {"flips", "tosses"}) or (not die and trial == "rolls"):
        return None
    if not 1 <= n <= 100:
        return None
    return MathIntent(
        kind="probability",
        school_op="binomial_at_least_one",
        combo_n=n,
        percent_base=1 / 6 if die else 1 / 2,
        trial_outcome={"head": "heads", "tail": "tails", "six": "sixes"}[outcome],
        operation="solve",
    )


def _at_least_one_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock:
    """``P(at least one) = 1 - (1 - p)^n``: everything but none at all."""
    from app.modules.math.tools.school.single_draw import probability_answer

    n = intent.combo_n or 0
    p = Fraction(intent.percent_base or 0).limit_denominator(6)
    none = (1 - p) ** n
    probability = 1 - none
    outcome = intent.trial_outcome or "successes"
    trials = "rolls" if p == Fraction(1, 6) else "flips"
    answer = probability_answer(probability)
    q_tex = fraction_tex(1 - p)
    lines.append(f"P(at least one) = 1 - ({1 - p})^{n} = {probability}")
    direct = render_workout(
        Workout(
            given=(
                math_line(f"n = {n}", trials),
                math_line(f"q = {q_tex}", f"no {outcome} on one {trials[:-1]}"),
            ),
            find=(math_line(r"P(\text{at least one})"),),
            formula=(
                math_line(r"P(\text{at least one}) = 1 - q^{n}", f"1 minus no {outcome} at all"),
            ),
            substitution=(
                math_line(
                    rf"P = 1 - \left({q_tex}\right)^{{{n}}} = 1 - {fraction_tex(none)}"
                    rf" = {fraction_tex(probability)}"
                ),
            ),
        ),
        answer,
    )
    return replace(finish_with_answer(lines, answer), worked_reply=direct)


def binomial_trials_direct_request(text: str) -> bool:
    """A coin or die question and nothing else, so the worked reply may stand alone."""
    request = " ".join(text.split()).strip()
    return bool(
        _TRIALS_QUESTION.fullmatch(request)
        or _TRIALS_SETUP.fullmatch(request)
        or _AT_LEAST_ONE.fullmatch(request)
        or _FAIR_DIE_EXPECTATION.fullmatch(request)
    )


def _trials_intent(cleaned: str) -> MathIntent | None:
    """A fair coin or die repeated n times, asking for exactly k of one outcome."""
    if not _CHANCE.search(cleaned) or _NOT_EXACTLY.search(cleaned):
        return None
    if _NOT_FAIR_DEVICE.search(cleaned):
        return None
    found = _TRIALS_IN.search(cleaned)
    if found is not None:
        k, outcome, n = (
            count_value(found.group(1)),
            found.group(2).lower(),
            count_value(found.group(3)),
        )
        trial = found.group(4).lower()
    else:
        repeat = _TRIALS_REPEAT.search(cleaned)
        counted = _TRIALS_COUNTED.search(cleaned)
        if repeat is None or counted is None:
            return None
        device = (repeat.group(1) or repeat.group(3)).lower()
        n = count_value(repeat.group(2) or repeat.group(4))
        k, outcome = count_value(counted.group(1)), counted.group(2).lower()
        trial = "flips" if device == "coin" else "rolls"
    die = outcome == "sixes"
    if (die and trial in {"flips", "tosses"}) or (not die and trial == "rolls"):
        return None
    if not 0 <= k <= n <= 100:
        return None
    return MathIntent(
        kind="probability",
        school_op="binomial_trials",
        combo_n=n,
        combo_k=k,
        percent_base=1 / 6 if die else 1 / 2,
        trial_outcome=outcome,
        operation="solve",
    )


def _extract_probability_intent(cleaned: str) -> MathIntent | None:
    extra = extract_probability_formulas(cleaned)
    if extra is not None:
        return extra
    trials = _trials_intent(cleaned)
    if trials is not None:
        return trials
    at_least_one = read(extract_at_least_one_intent, cleaned)
    if at_least_one is not None:
        return at_least_one
    if _FAIR_DIE_EXPECTATION.fullmatch(" ".join(cleaned.split())):
        return MathIntent(
            kind="probability",
            school_op="expected",
            stats_numbers=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            operation="solve",
        )
    from app.modules.math.tools.school.single_draw import extract_single_draw_intent

    single = read(extract_single_draw_intent, cleaned)
    if single is not None:
        return single
    from app.modules.math.tools.school.bag_draws import extract_bag_draws_intent

    bag = read(extract_bag_draws_intent, cleaned)
    if bag is not None:
        return bag
    dice = _DICE_CONDITIONAL_SUM.fullmatch(cleaned)
    if dice is not None:
        relation, threshold_text, event_text = dice.groups()
        threshold, event = int(threshold_text), int(event_text)
        if 2 <= threshold <= 12 and 2 <= event <= 12:
            comparator = {
                "at least": ">=",
                "at most": "<=",
                "greater than": ">",
                "less than": "<",
                "exactly": "=",
                "equal to": "=",
            }[" ".join(relation.lower().split())]
            return MathIntent(
                kind="probability",
                school_op="dice_conditional_sum",
                comparator=comparator,
                combo_n=threshold,
                combo_k=event,
                operation="solve",
            )
    lower = cleaned.lower()
    if "binomial" in lower or ("n=" in lower.replace(" ", "") and "p=" in lower.replace(" ", "")):
        empty = MathIntent(kind="probability", school_op="binomial", operation="solve")
        matches = list(_BINOMIAL_PARAM.finditer(cleaned))
        if len(matches) != 3 or {match.group(1).lower() for match in matches} != {"n", "k", "p"}:
            return empty
        try:
            params = {
                match.group(1).lower(): float(Fraction(match.group(2).replace(" ", "")))
                for match in matches
            }
        except (ValueError, ZeroDivisionError, OverflowError):
            return empty
        n, k, p = params["n"], params["k"], params["p"]
        if n is not None and k is not None and p is not None:
            if not n.is_integer() or not k.is_integer():
                return empty
            return MathIntent(
                kind="probability",
                school_op="binomial",
                combo_n=int(n),
                combo_k=int(k),
                percent_base=p,
                operation="solve",
            )
    if "expected value" in lower or "expected value of" in lower:
        if any(cue in lower for cue in ("probabilit", "weight", "p(", "p=")):
            from app.modules.math.match.discrete import numeric_data_values

            lists = list(_PROBABILITY_LIST.finditer(cleaned))
            if len(lists) == 2:
                values = numeric_data_values(lists[0].group(1))
                probabilities = numeric_data_values(lists[1].group(1))
                if values is not None and probabilities is not None:
                    return MathIntent(
                        kind="probability",
                        school_op="expected",
                        stats_numbers=values,
                        stats_numbers_b=probabilities,
                        operation="solve",
                    )
            # Retain the probability intent so the model can ask for a valid
            # distribution instead of averaging every number in the sentence.
            return MathIntent(kind="probability", school_op="expected", operation="solve")
        from app.modules.math.match.discrete import numeric_data_values

        nums = numeric_data_values(cleaned[lower.index("expected value") + len("expected value") :])
        if nums is not None:
            return MathIntent(
                kind="probability",
                school_op="expected",
                stats_numbers=nums,
                operation="solve",
            )
    return None


def _binomial_trials_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock:
    """``P(X = k) = C(n, k) p^k (1 - p)^(n - k)``, exact, for a fair coin or die."""
    from app.modules.math.tools.school.single_draw import probability_answer

    n, k = intent.combo_n or 0, intent.combo_k or 0
    p = Fraction(intent.percent_base or 0).limit_denominator(6)
    ways = math.comb(n, k)
    probability = ways * p**k * (1 - p) ** (n - k)
    outcome = intent.trial_outcome or "successes"
    one_outcome = "a six" if outcome == "sixes" else outcome
    trials = "rolls" if p == Fraction(1, 6) else "flips"
    exact = fraction_tex(probability)
    answer = probability_answer(probability)
    p_tex, q_tex = fraction_tex(p), fraction_tex(1 - p)
    lines.append(f"P(X={k}) = {probability} for n={n}, k={k}, p={p}")
    direct = render_workout(
        Workout(
            given=(
                math_line(f"n = {n}", trials),
                math_line(f"k = {k}", outcome),
                math_line(f"p = {p_tex}", f"{one_outcome} on one {trials[:-1]}"),
            ),
            find=(math_line(f"P(X = {k})"),),
            formula=(
                math_line(r"P(X = k) = \binom{n}{k} p^{k} (1 - p)^{n - k}", "Binomial probability"),
            ),
            substitution=(
                math_line(
                    rf"P(X = {k}) = \binom{{{n}}}{{{k}}} \left({p_tex}\right)^{{{k}}}"
                    rf" \left({q_tex}\right)^{{{n - k}}}"
                ),
                math_line(rf"= {ways} \cdot {fraction_tex(p**k * (1 - p) ** (n - k))} = {exact}"),
            ),
        ),
        answer,
    )
    return replace(finish_with_answer(lines, answer), worked_reply=direct)


def _verified_block_probability(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.school_op == "single_draw":
        from app.modules.math.tools.school.single_draw import single_draw_block

        return single_draw_block(intent, lines)
    if intent.school_op in {"bag_draws", "bag_draws_with_replacement"}:
        from app.modules.math.tools.school.bag_draws import bag_draws_block

        return bag_draws_block(intent, lines)
    if (
        intent.school_op == "dice_conditional_sum"
        and intent.comparator in {"<", "<=", "=", ">=", ">"}
        and intent.combo_n is not None
        and intent.combo_k is not None
    ):
        compare = {
            "<": lambda total: total < intent.combo_n,
            "<=": lambda total: total <= intent.combo_n,
            "=": lambda total: total == intent.combo_n,
            ">=": lambda total: total >= intent.combo_n,
            ">": lambda total: total > intent.combo_n,
        }[intent.comparator]
        sample = [
            (first, second)
            for first in range(1, 7)
            for second in range(1, 7)
            if compare(first + second)
        ]
        favorable = [pair for pair in sample if sum(pair) == intent.combo_k]
        if not sample:
            return None
        probability = Fraction(len(favorable), len(sample))
        comparator_latex = {"<": "<", "<=": r"\le", "=": "=", ">=": r"\ge", ">": ">"}[
            intent.comparator
        ]
        answer = (
            str(probability.numerator)
            if probability.denominator == 1
            else rf"\frac{{{probability.numerator}}}{{{probability.denominator}}}"
        )
        observed_ratio = rf"\frac{{{len(favorable)}}}{{{len(sample)}}}"
        probability_working = (
            observed_ratio if observed_ratio == answer else f"{observed_ratio}={answer}"
        )
        sample_text = "{" + ", ".join(f"({a}, {b})" for a, b in sample) + "}"
        favorable_text = (
            "{" + ", ".join(f"({a}, {b})" for a, b in favorable) + "}" if favorable else "∅"
        )
        lines.extend(
            (
                f"Conditional sample space: {sample_text}",
                f"Favorable outcomes: {favorable_text}",
                f"Probability: {len(favorable)}/{len(sample)} = {probability}",
            )
        )
        event = rf"P(S={intent.combo_k}\mid S {comparator_latex} {intent.combo_n})"
        direct = render_workout(
            Workout(
                given=(math_line(f"S {comparator_latex} {intent.combo_n}", "two fair dice"),),
                find=(math_line(event),),
                formula=(
                    math_line(r"P(A \mid B) = \frac{n(A \cap B)}{n(B)}", "Equally likely outcomes"),
                ),
                substitution=(
                    math_line(
                        sample_text,
                        f"{len(sample)} outcomes with ${{S {comparator_latex} {intent.combo_n}}}$",
                    ),
                    math_line(favorable_text, f"those with $S = {intent.combo_k}$"),
                    math_line(f"{event} = {probability_working}"),
                ),
            ),
            answer,
        )
        return replace(finish_with_answer(lines, answer), direct_reply=direct)
    if (
        intent.school_op == "binomial_trials"
        and intent.combo_n is not None
        and intent.combo_k is not None
        and intent.percent_base is not None
    ):
        return _binomial_trials_block(intent, lines)
    if (
        intent.school_op == "binomial_at_least_one"
        and intent.combo_n is not None
        and intent.percent_base is not None
    ):
        return _at_least_one_block(intent, lines)
    if (
        intent.school_op == "binomial"
        and intent.combo_n is not None
        and intent.combo_k is not None
        and intent.percent_base is not None
    ):
        answer = math_school.binomial_pmf(intent.combo_n, intent.combo_k, intent.percent_base)
        lines.append(f"P(X={intent.combo_k}) = {answer}")
        return finish_with_answer(lines, answer)
    if intent.school_op == "expected" and intent.stats_numbers:
        probabilities = intent.stats_numbers_b
        if probabilities is not None:
            if len(probabilities) != len(intent.stats_numbers):
                message = (
                    "Expected value needs one probability for each outcome "
                    f"({len(intent.stats_numbers)} outcomes versus {len(probabilities)} "
                    "probabilities)."
                )
                lines.append(message)
                return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
            if any(probability < 0 or probability > 1 for probability in probabilities):
                message = "Every probability must be between 0 and 1."
                lines.append(message)
                return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
            total = sum(probabilities)
            if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
                message = (
                    f"These probabilities sum to {total:g}, not 1, so they do not form "
                    "a valid probability distribution."
                )
                lines.append(message)
                return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
        answer = math_school.expected_value(intent.stats_numbers, probabilities)
        lines.append(f"E[X] = {answer}")
        return finish_with_answer(lines, answer)
    return probability_formula_block(intent, lines)
