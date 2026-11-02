"""Primary-school algorithms are exact server-owned procedure data."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.math import match as math_match
from app.modules.math import tools as math_tools
from app.modules.math.fence import validate_math_fences
from app.modules.math.response_intent import classify_math_response_intent
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.direct_arithmetic import arithmetic_work_spec
from app.tests.modules.math.card_support import card_with_working

_SETTINGS = Settings(math_tools_enabled=True)


def _work(question: str):
    intent = math_tools.extract_math_intent(question)
    assert intent is not None
    assert intent.kind == "arithmetic"
    block = math_tools._build_verified_block(intent, _SETTINGS)
    assert block is not None
    spec = arithmetic_work_spec(block)
    assert spec is not None
    return intent, block, spec


@pytest.mark.parametrize(
    "question, school_op, answer",
    [
        ("Show steps: 478 + 356", "column_addition", "834"),
        ("Show every step for 503 - 278", "column_subtraction", "225"),
        ("23 multiplied by 14", "column_multiplication", "322"),
        ("Use long division to calculate 1,572 ÷ 12", "long_division", "131"),
        ("437 divided by 6", "long_division", r"\frac{437}{6}\approx 72.83"),
        ("456/56", "long_division", r"\frac{57}{7}\approx 8.14"),
        ("59595 devided by 54", "long_division", r"\frac{19865}{18}\approx 1103.61"),
    ],
)
def test_written_arithmetic_extracts_on_existing_kind(
    question: str, school_op: str, answer: str
) -> None:
    intent, block, _spec = _work(question)
    assert intent.school_op == school_op
    assert block.canonical_answer == answer
    assert math_match.needs_symbolic(question) is True


def test_addition_trace_keeps_real_carry_state() -> None:
    _intent, _block, spec = _work("Show steps: 478 + 356")
    assert [column.carry_in for column in spec.addition_columns] == [0, 1, 1]
    assert [column.carry_out for column in spec.addition_columns] == [1, 1, 0]
    assert [column.result_digit for column in spec.addition_columns] == [4, 3, 8]
    assert "carry 1" in spec.explanations[0].lower()


def test_addition_trace_supports_more_than_two_aligned_addends() -> None:
    intent, _block, spec = _work("Show steps: 478 + 356 + 99")

    assert intent.arithmetic_operands == ["478", "356", "99"]
    assert spec.operands == ["478", "356", "99"]
    assert spec.answer == "933"
    assert spec.addition_columns[0].addends == [8, 6, 9]
    assert spec.addition_columns[0].carry_out == 2
    assert spec.addition_columns[1].carry_in == 2


def test_subtraction_trace_regroups_across_zero() -> None:
    _intent, _block, spec = _work("Show steps: 503 - 278")
    assert spec.regrouped_minuend == ["4", "9", "13"]
    ones = spec.subtraction_columns[0]
    assert ones.working_top == 13
    assert ones.regrouped_from == ["hundreds", "tens"]
    assert "hundreds → tens" in spec.explanations[0]


def test_multiplication_trace_has_shifted_partial_products() -> None:
    _intent, _block, spec = _work("Show steps: 23 × 14")
    assert [row.unshifted_product for row in spec.partial_products] == ["92", "23"]
    assert [row.shifted_product for row in spec.partial_products] == ["92", "230"]
    assert [column.carry_out for column in spec.partial_products[0].columns] == [1, 0]


def test_long_division_trace_has_bring_down_and_remainder() -> None:
    _intent, _block, spec = _work("Show long division: 437 ÷ 6")
    assert spec.quotient == "72"
    assert spec.remainder == "5"
    assert spec.answer_mode == "remainder"
    assert 437 == 6 * int(spec.quotient) + int(spec.remainder)
    assert [step.partial_dividend for step in spec.division_steps[:2]] == ["43", "17"]
    assert [step.column_end for step in spec.division_steps[:2]] == [1, 2]
    assert spec.division_steps[0].bring_down == 7
    assert spec.division_steps[0].next_partial == "17"


@pytest.mark.parametrize(
    "question, operands, answer",
    [
        ("Show steps: 12.40 + 3.6", ["12.40", "03.60"], "16.00"),
        ("Show steps: 10.00 - 2.75", ["10.00", "02.75"], "7.25"),
        ("Show steps: 1.2 × 3.4", ["1.2", "3.4"], "4.08"),
        ("Show steps: 12.6 ÷ 0.3", ["12.6", "0.3"], "42"),
        ("Show long division: 1.0 ÷ 4", ["1.0", "4"], "0.25"),
    ],
)
def test_decimal_written_methods_align_and_remain_exact(
    question: str, operands: list[str], answer: str
) -> None:
    _intent, _block, spec = _work(question)
    assert spec.operands == operands
    assert spec.answer == answer


def test_decimal_long_division_appends_visible_placeholder_zeros() -> None:
    _intent, _block, spec = _work("Show long division: 1.0 ÷ 4")
    assert spec.working_operands == ["1.00", "4"]
    assert [step.column_end for step in spec.division_steps] == [1, 2]


def test_division_below_the_divisor_keeps_appended_zeros_in_its_step() -> None:
    _intent, _block, spec = _work("Show steps: 1 divided by 3000")
    assert spec.quotient == "0.000"
    assert spec.working_operands == ["1.000", "3000"]
    assert [step.partial_dividend for step in spec.division_steps] == ["1000"]
    assert [step.column_end for step in spec.division_steps] == [3]
    assert spec.remainder == "1000"
    assert "1000 ÷ 3000 gives 0." in spec.explanations[1]


@pytest.mark.parametrize(
    "question",
    [
        "Show steps: 1 divided by 3000",
        "Show steps: 5 divided by 7000",
        "Show steps: 2 divided by 3",
        "Show steps: 1 divided by 6",
    ],
)
def test_repeating_division_trace_accounts_for_every_working_column(question: str) -> None:
    _intent, _block, spec = _work(question)
    dividend, divisor = spec.working_operands
    dividend_digits = dividend.replace(".", "")
    quotient_digits = (spec.quotient or "").replace(".", "")
    last = spec.division_steps[-1]
    assert last.column_end == len(dividend_digits) - 1
    assert last.remainder == spec.remainder
    assert int(dividend_digits) == int(divisor) * int(quotient_digits) + int(spec.remainder or "0")


@pytest.mark.parametrize(
    "question, quotient, answer",
    [
        ("1 divided by 4", "0.25", "0.25"),
        ("1 divided by 6", "0.166", r"\frac{1}{6}\approx 0.17"),
        ("1 divided by 4 as a decimal", "0.25", "0.25"),
        ("1 divided by 6 as a decimal", "0.166", r"\frac{1}{6}\approx 0.17"),
        ("437 divided by 6 as a fraction", "72", r"\frac{437}{6}"),
    ],
)
def test_whole_number_division_honors_requested_answer_mode(
    question: str,
    quotient: str,
    answer: str,
) -> None:
    _intent, _block, spec = _work(question)

    assert spec.quotient == quotient
    assert spec.answer == answer


def test_large_repeating_division_does_not_depend_on_decimal_context_precision() -> None:
    numerator = "10000000000000000000000000000"
    _intent, block, spec = _work(f"{numerator} divided by 3")

    assert spec.quotient == "3333333333333333333333333333.333"
    assert block.canonical_answer == (
        rf"\frac{{{numerator}}}{{3}}\approx 3333333333333333333333333333.33"
    )


def test_large_exact_division_preserves_every_input_digit() -> None:
    numerator = "12345678901234567890123456789"
    _intent, block, spec = _work(f"{numerator} divided by 7")

    assert spec.operands == [numerator, "7"]
    assert spec.quotient == "1763668414462081127160493827"
    assert block.canonical_answer == "1763668414462081127160493827"


def test_division_interpretations_are_explicit_and_preserve_the_invariant() -> None:
    for question, mode, answer in (
        ("437 divided by 6 with a remainder", "remainder", "72 R5"),
        ("437 divided by 6 round up", "round_up", "73"),
        ("437 divided by 6 discard the remainder", "discard", "72"),
    ):
        _intent, _block, spec = _work(question)
        assert spec.answer_mode == mode
        assert spec.answer == answer
        assert 437 == 6 * int(spec.quotient or "0") + int(spec.remainder or "0")


def test_remainder_phrase_on_a_decimal_keeps_the_decimal_quotient() -> None:
    _intent, _block, spec = _work("1.5 ÷ 2 with a remainder")

    assert spec.answer_mode == "decimal"
    assert spec.answer == "0.75"
    assert "R" not in spec.answer


@pytest.mark.parametrize(
    "question, working_operands, answer",
    [
        ("Show long division: 100 ÷ 4", ["100", "4"], "25"),
        ("Show long division: 1.2 ÷ 0.03", ["120", "3"], "40"),
    ],
)
def test_long_division_preserves_significant_trailing_zeros(
    question: str,
    working_operands: list[str],
    answer: str,
) -> None:
    _intent, _block, spec = _work(question)
    assert spec.working_operands == working_operands
    assert spec.answer == answer


def test_direct_reply_separates_division_answer_mode_from_working_visibility() -> None:
    _intent, plain_block, _spec = _work("478 + 356")
    assert maybe_direct_math_reply(plain_block, "478 + 356") == card_with_working(
        "478 + 356 = 834", "478 + 356"
    )

    _intent, division_block, _spec = _work("59595 devided by 54")
    division_reply = maybe_direct_math_reply(division_block, "59595 devided by 54")
    assert division_reply == card_with_working(
        "59595 \u00f7 54 = \\frac{19865}{18}\\approx 1103.61", "59595 devided by 54"
    )
    assert "```arithmetic" not in validate_math_fences(division_reply, verified=division_block)

    answer_only = "Just the answer: 59595 divided by 54"
    _intent, answer_block, _spec = _work(answer_only)
    assert maybe_direct_math_reply(answer_block, answer_only) == (
        "```answer\n\\frac{19865}{18}\\approx 1103.61\n```\n"
    )

    _intent, steps_block, _spec = _work("Show steps: 478 + 356")
    reply = maybe_direct_math_reply(steps_block, "Show steps: 478 + 356")
    assert reply is not None
    assert "```arithmetic" in reply
    assert reply.rstrip().endswith("```answer\n834\n```")

    _intent, division_block, _spec = _work("Show long division: 1,572 ÷ 12")
    division_reply = maybe_direct_math_reply(
        division_block,
        "Show long division: 1,572 ÷ 12",
    )
    assert division_reply is not None
    assert "```arithmetic" in division_reply
    assert division_reply.rstrip().endswith("```answer\n131\n```")


def test_referential_how_replays_the_verified_school_method() -> None:
    question = "503 - 278"
    _intent, block, _spec = _work(question)

    reply = maybe_direct_math_reply(
        block,
        "how?",
        verified_request_text=question,
    )

    assert reply is not None
    assert "```arithmetic" in reply
    assert '"answer":"225"' in reply
    assert reply.rstrip().endswith("```answer\n225\n```")


def test_followup_presentation_intent_keeps_canonical_long_division() -> None:
    question = "456/56"
    _intent, block, _spec = _work(question)
    block = replace(block, response_intent=classify_math_response_intent("Show me"))

    reply = maybe_direct_math_reply(
        block,
        "Show me",
        verified_request_text=question,
    )

    assert reply is not None
    assert "```arithmetic" in reply
    cleaned = validate_math_fences(reply, verified=block)
    assert "```arithmetic" in cleaned
    assert '"answer":"\\\\frac{57}{7}\\\\approx 8.14"' in cleaned


def test_fence_rewriter_uses_only_canonical_written_work() -> None:
    question = "Show steps: 478 + 356"
    _intent, block, spec = _work(question)
    block = replace(block, response_intent=classify_math_response_intent(question))
    invented = '```arithmetic\n{"type":"arithmetic","answer":"999"}\n```'
    cleaned = validate_math_fences(invented, verified=block)
    assert '"answer":"834"' in cleaned
    assert '"answer":"999"' not in cleaned
    assert spec.answer == "834"


def test_written_working_reads_before_the_answer_card() -> None:
    question = "Show steps: 478 + 356"
    _intent, block, _spec = _work(question)
    block = replace(block, response_intent=classify_math_response_intent(question))
    cleaned = validate_math_fences("Add the columns.\n\n**Answer**\n$834$", verified=block)
    assert cleaned.count("**Answer**") == 1
    assert cleaned.index("```arithmetic") < cleaned.index("**Answer**")
    # The card holds the sum alone; the columns above are the working.
    assert cleaned.index("**Answer**") < cleaned.index("```answer\nverified: true\n834\n```")


def test_unverified_written_work_is_stripped_without_showing_raw_json() -> None:
    content = '```arithmetic\n{"type":"arithmetic","answer":"999"}\n```'
    cleaned = validate_math_fences(content)

    assert "999" not in cleaned
    assert cleaned == ""


def test_mismatched_written_work_uses_the_specific_failure_note() -> None:
    question = "Show steps: 478 + 356"
    _intent, block, _spec = _work(question)
    block = replace(block, response_intent=classify_math_response_intent(question))

    cleaned = validate_math_fences('```arithmetic\n{"type":"not-arithmetic"}\n```', verified=block)

    assert "Could not render that written working" in cleaned


def test_answer_only_strips_written_working() -> None:
    question = "Just the answer: 478 + 356"
    _intent, block, _spec = _work(question)
    block = replace(block, response_intent=classify_math_response_intent(question))
    content = "```arithmetic\n{}\n```\n\n```answer\n834\n```"
    cleaned = validate_math_fences(content, verified=block)
    assert "```arithmetic" not in cleaned
    assert "```answer\nverified: true\n834" in cleaned


def test_written_grammar_rejects_compound_or_malformed_requests() -> None:
    assert math_match.written_arithmetic_request("478 + 356 and tell me a joke") is None
    assert math_match.written_arithmetic_request("12,34 + 1") is None
    assert math_match.written_arithmetic_request("-5 + 2") is None
    assert math_match.written_arithmetic_request("9/9") is None
    assert math_match.written_arithmetic_request("2026/09") is None
    assert math_match.written_arithmetic_request("456/56") == (
        "456",
        "56",
        "/",
        "long_division",
    )
    assert math_match.written_arithmetic_request("2026-09") is None
    assert math_match.written_arithmetic_request("555-1234") is None


def test_written_grammar_consumes_school_method_metadata() -> None:
    assert math_match.written_arithmetic_request("Show 478 + 356 using carrying.") == (
        "478",
        "356",
        "+",
        "column_addition",
    )
    assert math_match.written_arithmetic_request("Show 503 - 278 using borrowing.") == (
        "503",
        "278",
        "-",
        "column_subtraction",
    )
    assert math_match.written_arithmetic_request("Show 12 + 3 using borrowing.") is None


def test_school_method_request_uses_the_typed_direct_trace() -> None:
    question = "Show 478 + 356 using carrying."
    _intent, block, spec = _work(question)
    block = replace(block, response_intent=classify_math_response_intent(question))

    assert block.response_intent.wants_explanation
    reply = maybe_direct_math_reply(block, question)
    assert reply is not None
    assert reply.startswith("```arithmetic\n")
    assert '"operation":"addition"' in reply
    assert spec.answer == "834"
