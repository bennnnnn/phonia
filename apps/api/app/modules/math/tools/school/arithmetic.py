"""Arithmetic extractor and verified block: fact families, then one block per school op."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import NamedTuple

from app.core.config import Settings
from app.modules.math import match as mtm
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.extractors.readings import read
from app.modules.math.tools.function_def import substituted_eval_expr
from app.modules.math.tools.school.arithmetic_expression import expression_block
from app.modules.math.tools.school.fractions import _block_fraction
from app.modules.math.tools.school.interest import (
    _block_interest,
    _block_present_value,
    _extract_interest_intent,
    extract_present_value,
)
from app.modules.math.tools.school.percentages import (
    _block_discount,
    _block_original_before_percent,
    _block_percent,
    _block_percent_chain,
    _block_percent_change,
    _block_percent_change_from,
    _block_percent_is,
    _extract_percent_change,
    _extract_percent_is,
    _extract_percent_of,
    extract_discount,
    extract_original_before_percent,
    extract_percent_change_from,
    extract_with_percent_total,
)
from app.modules.math.tools.school.rates import (
    _block_mixture,
    _block_twice_as_many,
    _block_work_together,
    _extract_word_problem_intent,
)
from app.modules.math.tools.school.ratios import (
    _block_proportion,
    _block_ratio,
    _block_ratio_split,
    _extract_colon_ratio,
    _extract_ratio_split,
    extract_proportion,
)
from app.modules.math.tools.school.rounding import ROUNDING_OPS, extract_rounding, rounding_block
from app.modules.math.tools.school.sequences import (
    _block_infinite_gp,
    _block_sequence,
    _extract_sequence_intent,
    extract_infinite_geometric,
)
from app.modules.math.tools.school.sets import _block_sets, _extract_set_intent
from app.modules.math.tools.school.statistics import _block_z_score
from app.modules.math.tools.school.teaching import _block_teaching


def _extract_percent_or_ratio(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    # "% of " stays first so "Out of 250 people, what is 30% of 80?" is 24.
    percent_of = _extract_percent_of(cleaned)
    if percent_of is not None:
        return percent_of
    changed = _extract_percent_change(cleaned, lower)
    if changed is not None:
        return changed
    percent_is = _extract_percent_is(cleaned, lower)
    if percent_is is not None:
        return percent_is
    split = _extract_ratio_split(cleaned, lower)
    if split is not None:
        return split
    return _extract_colon_ratio(cleaned, lower)


# Closed school formulas, tried in this order after "a% of b" and ratios.
_FORMULA_READERS = (
    extract_original_before_percent,
    extract_discount,
    extract_with_percent_total,
    extract_percent_change_from,
    extract_present_value,
    extract_proportion,
    extract_rounding,
)


def extract_arithmetic_formulas(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    for reader in _FORMULA_READERS:
        intent = reader(cleaned, lower)
        if intent is not None:
            return intent
    return None


def _extract_arithmetic_intent(cleaned: str) -> MathIntent | None:
    lower_cleaned = cleaned.lower()
    if "decimal approximation" in lower_cleaned and "exact" in lower_cleaned:
        cut = lower_cleaned.find("give exact")
        if cut == -1:
            cut = lower_cleaned.find("give an exact")
        if cut != -1:
            base = cleaned[:cut].rstrip(" .?!")
            extracted = _extract_arithmetic_intent(base)
            if extracted is not None and extracted.expr:
                return extracted.model_copy(update={"school_op": "eval_exact_decimal"})
    spoken_power = mtm.spoken_power_request(cleaned)
    if spoken_power is not None:
        variable = next((char for char in spoken_power if char.isalpha()), "x")
        return MathIntent(
            kind="arithmetic",
            school_op="symbolic_power" if any(char.isalpha() for char in spoken_power) else "eval",
            expr=spoken_power,
            operation="solve",
            variable=variable,
        )
    addition = mtm.written_addition_request(cleaned)
    if addition is not None:
        return MathIntent(
            kind="arithmetic",
            school_op="column_addition",
            expr="+".join(addition),
            arithmetic_operands=addition,
            operation="solve",
        )
    written = mtm.written_arithmetic_request(cleaned)
    if written is not None:
        left, right, operator, school_op = written
        return MathIntent(
            kind="arithmetic",
            school_op=school_op,
            expr=f"{left}{operator}{right}",
            arithmetic_operands=[left, right],
            division_answer_mode=(
                mtm.division_answer_mode(cleaned, left, right)
                if school_op == "long_division"
                else None
            ),
            operation="solve",
        )
    substituted = substituted_eval_expr(cleaned)
    if substituted is not None:
        return MathIntent(kind="arithmetic", school_op="eval", expr=substituted, operation="solve")
    if mtm.has_equation(cleaned):
        return None
    from app.modules.math.tools.school.charges import extract_charge_intent

    charge = read(extract_charge_intent, cleaned)
    if charge is not None:
        return charge
    percent = _extract_percent_or_ratio(cleaned)
    if percent is not None:
        return percent
    formulas = read(extract_arithmetic_formulas, cleaned)
    if formulas is not None:
        return formulas
    lower = cleaned.lower()
    interest = _extract_interest_intent(cleaned, lower)
    if interest is not None:
        return interest
    from app.modules.math.tools.school.shopping import extract_change_intent

    change = read(extract_change_intent, cleaned)
    if change is not None:
        return change
    sets = _extract_set_intent(cleaned, lower)
    if sets is not None:
        return sets
    word = _extract_word_problem_intent(cleaned, lower)
    if word is not None:
        return word
    infinite = extract_infinite_geometric(cleaned)
    if infinite is not None:
        return infinite
    sequence = _extract_sequence_intent(cleaned)
    if sequence is not None:
        return sequence
    expr = mtm.bare_arithmetic_expr(cleaned)
    if expr is None:
        return None
    return MathIntent(kind="arithmetic", school_op="eval", expr=expr, operation="solve")


_ArithmeticBuilder = Callable[[MathIntent, list[str]], VerifiedMathBlock | None]

_WRITTEN_OPS = frozenset(
    {"column_addition", "column_subtraction", "column_multiplication", "long_division"}
)


class _OpBlock(NamedTuple):
    """One school op's block, and whether the intent has the fields that block reads."""

    ready: Callable[[MathIntent], bool]
    build: _ArithmeticBuilder


def _always(intent: MathIntent) -> bool:
    return True


def _rate_and_base(intent: MathIntent) -> bool:
    return intent.percent_rate is not None and intent.percent_base is not None


def _rate_base_and_count(intent: MathIntent) -> bool:
    return _rate_and_base(intent) and intent.combo_n is not None


def _numbers(intent: MathIntent) -> bool:
    return bool(intent.stats_numbers)


def _change_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math.tools.school.shopping import change_block

    return change_block(intent, lines)


def _charge_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math.tools.school.charges import charge_block

    return charge_block(intent, lines)


# One block per school op. An intent without the fields its op's block reads goes on to
# the expression it carries (``arithmetic_expression.py``).
_ARITHMETIC_BLOCKS: dict[str, _OpBlock] = {
    "z_score": _OpBlock(lambda i: i.point_x is not None and _rate_and_base(i), _block_z_score),
    "percent": _OpBlock(_rate_and_base, _block_percent),
    "percent_chain": _OpBlock(_always, _block_percent_chain),
    "percent_increase": _OpBlock(_rate_and_base, _block_percent_change),
    "percent_decrease": _OpBlock(_rate_and_base, _block_percent_change),
    "percent_is": _OpBlock(_rate_and_base, _block_percent_is),
    "discount": _OpBlock(_rate_and_base, _block_discount),
    "original_before_decrease": _OpBlock(_always, _block_original_before_percent),
    "original_before_increase": _OpBlock(_always, _block_original_before_percent),
    "percent_change_from": _OpBlock(_rate_and_base, _block_percent_change_from),
    "direct_proportion": _OpBlock(_numbers, _block_proportion),
    "inverse_proportion": _OpBlock(_numbers, _block_proportion),
    **dict.fromkeys(
        ROUNDING_OPS,
        _OpBlock(lambda i: i.percent_base is not None and i.combo_n is not None, rounding_block),
    ),
    "infinite_gp": _OpBlock(_numbers, _block_infinite_gp),
    "present_value": _OpBlock(_rate_base_and_count, _block_present_value),
    "ratio": _OpBlock(_rate_and_base, _block_ratio),
    "ratio_split": _OpBlock(
        lambda i: i.percent_base is not None and _numbers(i), _block_ratio_split
    ),
    **dict.fromkeys(
        ("sequence_nth", "sequence_sum"),
        _OpBlock(lambda i: _numbers(i) and i.combo_n is not None, _block_sequence),
    ),
    **dict.fromkeys(
        ("simple_interest", "compound_interest", "compound_amount"),
        _OpBlock(_rate_base_and_count, _block_interest),
    ),
    **dict.fromkeys(
        ("set_union", "set_intersection", "set_difference"),
        _OpBlock(lambda i: i.vec_a is not None and i.vec_b is not None, _block_sets),
    ),
    "work_together": _OpBlock(_rate_and_base, _block_work_together),
    "mixture": _OpBlock(lambda i: bool(i.vec_a and i.vec_b and len(i.vec_a) == 2), _block_mixture),
    "change_from_payment": _OpBlock(_always, _change_block),
    "percent_charge": _OpBlock(_always, _charge_block),
    "twice_as_many": _OpBlock(lambda i: i.percent_base is not None, _block_twice_as_many),
}


def _verified_block_arithmetic(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.teaching_op and intent.teaching_payload:
        return _block_teaching(intent, lines)
    fact_block = _fact_block(intent.school_op)
    if fact_block is not None:
        return fact_block(intent, lines)
    # A fraction or a written method that cannot be laid out goes on to the op table.
    if intent.school_op and intent.school_op.startswith("fraction_"):
        fraction_block = _block_fraction(intent, lines)
        if fraction_block is not None:
            return fraction_block
    written = _written_block(intent, lines)
    if written is not None:
        return written
    op_block = _ARITHMETIC_BLOCKS.get(intent.school_op or "")
    if op_block is not None and op_block.ready(intent):
        return op_block.build(intent, lines)
    return expression_block(intent, lines)


def _fact_block(school_op: str | None) -> _ArithmeticBuilder | None:
    """The fact family that owns ``school_op``, tried in this order before any other block."""
    if school_op in {"function_value", "expression_value"}:
        from app.modules.math.tools.school.function_value import _block_function_value

        return _block_function_value
    if school_op in {
        "pythagoras_leg",
        "polygon_angle_sum",
        "polygon_interior",
        "polygon_exterior",
    }:
        from app.modules.math.tools.school.geometry_facts import geometry_fact_block

        return geometry_fact_block
    from app.modules.math.tools.school.algebra_facts import ALGEBRA_FACT_OPS, algebra_fact_block
    from app.modules.math.tools.school.geometry_measures import (
        geometry_measure_block,
        is_geometry_measure,
    )
    from app.modules.math.tools.school.number_facts import NUMBER_FACT_OPS, number_fact_block

    if is_geometry_measure(school_op):
        return geometry_measure_block
    if school_op in NUMBER_FACT_OPS:
        return number_fact_block
    if school_op in ALGEBRA_FACT_OPS:
        return algebra_fact_block
    from app.modules.math.tools.school.equation_features import (
        FEATURE_OPS,
        equation_feature_block,
    )

    if school_op in FEATURE_OPS:
        return equation_feature_block
    return None


def _written_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    """Column addition, subtraction or multiplication, or long division, when it lays out."""
    if intent.school_op not in _WRITTEN_OPS or not intent.expr:
        return None
    from app.modules.math.solve.written_arithmetic import build_written_arithmetic_operands

    # ``intent.expr`` is the extractor-owned canonical expression. Prefix
    # its ASCII slash with a calculation cue so the public grammar can
    # keep rejecting ambiguous bare dates such as ``9/9``.
    operands = intent.arithmetic_operands
    if operands is None:
        request = mtm.written_arithmetic_request(f"calculate {intent.expr}")
        operands = list(request[:2]) if request is not None else None
    if operands is not None:
        arithmetic_work = build_written_arithmetic_operands(
            operands,
            intent.school_op,
            intent.expr,
            division_answer_mode=intent.division_answer_mode,
        )
        if arithmetic_work is not None:
            from app.modules.math.tools.direct_arithmetic import (
                final_answer,
                written_fact_line,
            )

            lines.append(f"Verified {arithmetic_work.operation} procedure:")
            lines.extend(arithmetic_work.explanations)
            block = finish_with_answer(lines, final_answer(arithmetic_work))
            return replace(
                block,
                canonical_fences=[arithmetic_work.model_dump()],
                display_answer=written_fact_line(arithmetic_work),
            )
    return None
