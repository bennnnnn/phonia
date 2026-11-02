"""Direct verified-math replies that skip the LLM when language adds nothing."""

from __future__ import annotations

import json

from app.modules.math.followup_what_if import is_part_change
from app.modules.math.match.scan import closed_request_text
from app.modules.math.tools.direct_fences import MAX_DIRECT_ANSWER_CHARS, solver_fences
from app.modules.math.tools.direct_graph import (
    can_direct_graph,
    can_direct_number_line,
    can_direct_point_or_vertical,
)
from app.modules.math.tools.direct_shape_questions import (
    nonmeasurement_geometry_reply,
    underdetermined_triangle_measurement,
)
from app.modules.math.tools.direct_working import working_above_card
from app.modules.math.tools.lesson import (
    format_equation_lesson_reply,
    lesson_math_text,
    should_render_equation_lesson,
    strip_teaching_signals,
    wants_answer_check,
    wants_detailed_math_explanation,
    wants_math_explanation,
    with_requested_check,
)
from app.modules.math.tools.school.complex import without_form_clause
from app.services.solving import VerifiedMathBlock

# Polite glue around a closed compute; two more English words ("tell joke") keep the LLM.
_MATH_REQUEST_GLUE = frozenset(
    {
        "solve",
        "isolate",
        "factor",
        "expand",
        "simplify",
        "calculate",
        "compute",
        "evaluate",
        "determine",
        "find",
        "please",
        "thanks",
        "thank",
        "now",
        "quickly",
        "briefly",
        "here",
        "what",
        "whats",
        "the",
        "value",
        "of",
        "over",
        "for",
        "and",
        "then",
        "is",
        "equals",
        "equal",
        "plus",
        "minus",
        "times",
        "can",
        "you",
        "could",
        "this",
        "that",
        "real",
        "numbers",
    }
)


def _looks_math_token(tok: str) -> bool:
    if not tok:
        return True
    if any(tok.startswith(f"{name}(") for name in ("sqrt", "sin", "cos", "tan", "log", "ln")):
        return True
    return any(ch.isdigit() or ch in "=^*/+-%" for ch in tok)


def leftover_non_math_request(text: str) -> bool:
    """True when the message asks for something besides the verified value.

    ``Solve x+1=2 and tell me a joke`` must not become an instant ``x = 1``.
    Linear token walk — no regex on user text.
    """
    english = 0
    for raw in text.replace("'", "").split():
        tok = raw.lower().strip(".,?!:;")
        if _looks_math_token(tok) or len(tok) < 3 or tok in _MATH_REQUEST_GLUE:
            continue
        english += 1
        if english >= 2:
            return True
    return False


def _plain_prime_factorization_request(text: str) -> bool:
    """Match the complete one-integer ask; extra clauses still need language."""
    request = closed_request_text(text)
    if request is None:
        return False
    for prefix in (
        "prime factorization of ",
        "prime factorisation of ",
        "prime factors of ",
        "factorize ",
        "factorise ",
        "factor ",
    ):
        if request.startswith(prefix):
            number = request[len(prefix) :]
            if number.endswith(" please"):
                number = number[:-7]
            return bool(number and number.isascii() and number.isdecimal())
    return False


def _closed_school_request(user_text: str, calculus_text: str) -> bool:
    """A school grammar that reads the whole request, so no prose rides along.

    Function values, counting questions in words, one roll or draw, and
    tangent lines or stationary points.
    """
    from app.modules.math.match.discrete import counting_word_signal
    from app.modules.math.tools.extractors.calculus_methods import average_value_request
    from app.modules.math.tools.school.algebra_facts import extract_algebra_fact_intent
    from app.modules.math.tools.school.bag_draws import extract_bag_draws_intent
    from app.modules.math.tools.school.curve_points import extract_curve_point_intent
    from app.modules.math.tools.school.equation_features import extract_equation_feature_intent
    from app.modules.math.tools.school.function_value import extract_function_value_intent
    from app.modules.math.tools.school.geometry_facts import extract_geometry_fact_intent
    from app.modules.math.tools.school.geometry_measures import extract_geometry_measure_intent
    from app.modules.math.tools.school.number_facts import extract_number_fact_intent
    from app.modules.math.tools.school.shopping import extract_change_intent
    from app.modules.math.tools.school.single_draw import extract_single_draw_intent

    return (
        average_value_request(user_text)
        or extract_function_value_intent(user_text) is not None
        or extract_geometry_fact_intent(user_text) is not None
        or extract_geometry_measure_intent(user_text) is not None
        or extract_number_fact_intent(user_text) is not None
        or extract_algebra_fact_intent(user_text) is not None
        or extract_equation_feature_intent(user_text) is not None
        or counting_word_signal(user_text) is not None
        or extract_single_draw_intent(user_text) is not None
        or extract_bag_draws_intent(user_text) is not None
        or extract_change_intent(user_text) is not None
        or extract_curve_point_intent(calculus_text) is not None
    )


def can_direct_verified_math_reply(
    verified: VerifiedMathBlock,
    user_text: str,
    *,
    has_image_attachment: bool = False,
    verified_request_text: str | None = None,
) -> bool:
    """Skip the LLM for a short closed answer or an explicit verified function plot.

    Geometry, camera homework, mixed leftover requests, and explanations that
    have no verified trace keep the inject+stream path. Detailed / "show steps"
    take the direct path when ``key_steps`` exist so the lesson cannot drift
    from the chip.
    """
    from app.modules.math.response_intent import classify_math_response_intent

    response_intent = verified.response_intent or classify_math_response_intent(user_text)
    if not response_intent.reveal_answer and verified.canonical_answer is not None:
        return False
    if has_image_attachment:
        return False
    if nonmeasurement_geometry_reply(verified, user_text) is not None:
        return True
    from app.modules.math.tools.direct_arithmetic import (
        arithmetic_work_spec,
        can_direct_fraction,
        can_direct_written_arithmetic,
        fraction_work_spec,
    )

    written_arithmetic = arithmetic_work_spec(verified)
    if written_arithmetic is not None:
        guard_text = verified_request_text or user_text
        return can_direct_written_arithmetic(verified, guard_text, written_arithmetic)
    fraction_work = fraction_work_spec(verified)
    if fraction_work is not None:
        guard_text = verified_request_text or user_text
        return can_direct_fraction(verified, guard_text, fraction_work)
    lesson = should_render_equation_lesson(verified, user_text)
    if wants_math_explanation(user_text) and not lesson:
        return False
    if not verified.allow_direct:
        return False
    from app.modules.math.tools.direct_newton import can_direct_newton, has_newton_request

    if verified.newton_input is not None or has_newton_request(user_text):
        return can_direct_newton(verified, user_text, solver_fences(verified))
    if underdetermined_triangle_measurement(verified, user_text) is not None:
        return True
    from app.modules.math.tools.direct_geometry import (
        can_direct_curved_or_slanted_geometry,
        can_direct_rectangle,
        can_direct_square_or_triangle,
        can_direct_triangle_angles,
    )

    geometry_fences = solver_fences(verified)
    if can_direct_curved_or_slanted_geometry(verified, user_text, geometry_fences):
        return True
    if can_direct_triangle_angles(user_text, geometry_fences):
        return True
    if can_direct_rectangle(verified, user_text, geometry_fences) or can_direct_square_or_triangle(
        verified, user_text, geometry_fences
    ):
        return True
    if can_direct_point_or_vertical(verified, user_text):
        return True
    if can_direct_graph(verified, user_text):
        return True
    if can_direct_number_line(verified, user_text):
        return True
    presentation_free = lesson_math_text(user_text)
    if presentation_free != user_text and can_direct_number_line(
        verified, presentation_free, require_solve=False
    ):
        return True
    if lesson and can_direct_number_line(
        verified, lesson_math_text(user_text), require_solve=False
    ):
        return True
    # Prime factorization has two operation words the prose counter rejects: match the
    # whole request ("factorize 60 and 2+2" keeps the model). A rebuilt "what if" passes.
    from app.modules.math.match.coordinate_vector import (
        has_coordinate_vector_request,
        is_closed_coordinate_vector_request,
    )
    from app.modules.math.tools.direct_calculus import calculus_direct_request
    from app.modules.math.tools.direct_solids import solid_direct_request
    from app.modules.math.tools.direct_statistics import statistics_direct_request
    from app.modules.math.tools.direct_units import unit_direct_request
    from app.modules.math.tools.school.probability import binomial_trials_direct_request

    trials_request = binomial_trials_direct_request(user_text)
    # A lesson wraps calculus in teaching words ("show steps:"); the grammar reads under them.
    calculus_text = lesson_math_text(user_text) if lesson else user_text
    closed_request = _closed_school_request(user_text, calculus_text)
    # A closed grammar has read the whole request, so the other subjects'
    # grammars do not get a veto: "the sum of two dice" is not a series and
    # "convert 3/8 to a percentage" is not a unit conversion.
    statistics_request = None if closed_request else statistics_direct_request(user_text)
    unit_request = None if closed_request else unit_direct_request(user_text)
    solid_request = None if closed_request else solid_direct_request(user_text)
    calculus_request = (
        None
        if closed_request
        else calculus_direct_request(calculus_text, answer=verified.canonical_answer)
    )
    if (
        statistics_request is False
        or unit_request is False
        or solid_request is False
        or calculus_request is False
    ):
        return False
    if statistics_request or unit_request or solid_request or calculus_request:
        from app.modules.math.schemas.teaching import TEACHING_TYPES

        fences = solver_fences(verified)
        answers = [fence for fence in fences if fence.get("type") == "answer"]
        pictures = [fence for fence in fences if fence.get("type") in TEACHING_TYPES]
        if (
            len(answers) != 1
            or answers[0].get("content") != verified.canonical_answer
            or len(fences) != len(answers) + len(pictures)
        ):
            return False
    lower = user_text.lower()
    coordinate_vector_request = has_coordinate_vector_request(user_text)
    if coordinate_vector_request and not is_closed_coordinate_vector_request(user_text):
        return False
    factorization_request = "prime factor" in lower or "factorize" in lower
    if factorization_request and not _plain_prime_factorization_request(user_text):
        return False
    if not (
        factorization_request
        or coordinate_vector_request
        or trials_request
        or closed_request
        or statistics_request
        or unit_request
        or solid_request
        or calculus_request
    ) and leftover_non_math_request(strip_teaching_signals(without_form_clause(user_text))):
        if not (verified_request_text and is_part_change(user_text)):
            return False
    answer = (verified.canonical_answer or "").strip()
    if calculus_request and any(
        token in answer
        for token in (r"\lim", r"\int", r"\sum", r"\frac{d}{d", r"\langle", "Derivative", "NaN")
    ):
        return False
    if not answer or len(answer) > MAX_DIRECT_ANSWER_CHARS:
        return False
    from app.modules.math.schemas.teaching import TEACHING_TYPES

    fences = solver_fences(verified)
    if not fences:
        return True
    return all(fence.get("type") in {"answer", *TEACHING_TYPES} for fence in fences)


def format_direct_math_reply(verified: VerifiedMathBlock, user_text: str = "") -> str:
    """Display a verified value, diagram, or the missing scale for an AAA request."""
    from app.modules.math.tools.direct_arithmetic import (
        arithmetic_work_spec,
        format_direct_fraction,
        format_direct_written_arithmetic,
        fraction_work_spec,
    )

    written_arithmetic = arithmetic_work_spec(verified)
    if written_arithmetic is not None:
        return format_direct_written_arithmetic(written_arithmetic, user_text)
    fraction_work = fraction_work_spec(verified)
    if fraction_work is not None:
        from app.modules.math.tools.direct_teaching import prepend_teaching_fence

        return prepend_teaching_fence(
            format_direct_fraction(fraction_work, user_text), verified, user_text
        )
    geometry_reply = nonmeasurement_geometry_reply(verified, user_text)
    if geometry_reply is not None:
        return geometry_reply
    if verified.newton_input is not None:
        from app.modules.math.tools.direct_newton import format_newton_reply

        return format_newton_reply(verified)
    quantity = underdetermined_triangle_measurement(verified, user_text)
    if quantity is not None:
        return f"The {quantity} cannot be determined from angles alone. What is one side length?"
    if verified.worked_reply is not None:
        return verified.worked_reply
    fences = solver_fences(verified)
    answer = (verified.canonical_answer or "").strip()
    display_answer = (verified.display_answer or answer).strip()
    return _format_direct_math_body(verified, user_text, fences, answer, display_answer)


def _format_direct_math_body(
    verified: VerifiedMathBlock,
    user_text: str,
    fences: list[dict[str, object]],
    answer: str,
    display_answer: str,
) -> str:
    if len(fences) == 1 and fences[0].get("relative_lengths") is True:
        return f"```geometry\n{json.dumps(fences[0], separators=(',', ':'))}\n```\n"
    if len(fences) == 1 and fences[0].get("type") in {
        "function",
        "inequality",
        "vertical",
        "trajectory",
    }:
        # The mobile stream scanner needs the newline after the closing fence
        # to render the graph immediately, before the done event arrives.
        graph_reply = f"```graph\n{json.dumps(fences[0], separators=(',', ':'))}\n```\n"
        if answer:
            return f"```answer\n{display_answer}\n```\n\n{graph_reply}"
        return graph_reply
    if len(fences) == 1 and fences[0].get("type") in {
        "rectangle",
        "square",
        "triangle",
        "right_triangle",
        "triangle_sides",
        "parallelogram",
        "trapezoid",
        "circle",
        "sector",
    }:
        from app.modules.math.tools.direct_geometry_working import (
            format_direct_geometry_working,
        )

        working = format_direct_geometry_working(
            verified.geometry_request, fences[0], answer, display_answer.startswith("\\approx")
        )
        prefix = f"{working}\n\n" if working else ""
        return (
            f"{prefix}```answer\n{display_answer}\n```\n\n"
            f"```geometry\n{json.dumps(fences[0], separators=(',', ':'))}\n```\n"
        )
    if len(fences) == 1 and fences[0].get("type") == "number_line":
        return (
            f"```answer\n{display_answer}\n```\n\n"
            f"```graph\n{json.dumps(fences[0], separators=(',', ':'))}\n```\n"
        )
    # The answer fence already typesets the result. Emitting a second math
    # paragraph repeats the same answer on the phone. The final newline also
    # lets the streaming client close and render this fence immediately.
    from app.modules.math.tools.direct_geometry_working import format_direct_solid_working

    rounded = display_answer.startswith("\\approx")
    solid_working = format_direct_solid_working(verified.geometry_request, answer, rounded)
    prefix = f"{solid_working}\n\n" if solid_working else ""
    from app.modules.math.tools.direct_teaching import prepend_teaching_fence

    return prepend_teaching_fence(
        f"{prefix}```answer\n{display_answer}\n```\n", verified, user_text
    )


def _chip_answer(verified: VerifiedMathBlock, *, answer_only: bool) -> str:
    """The checked line. A bare fact reads ``4 x 4 = 16``; answer-only is the number."""
    from app.modules.math.tools.direct_arithmetic import equation_line_hides_for_answer_only

    if answer_only and equation_line_hides_for_answer_only(verified):
        return (verified.canonical_answer or "").strip()
    return (verified.display_answer or verified.canonical_answer or "").strip()


def maybe_direct_math_reply(
    verified: VerifiedMathBlock | None,
    user_text: str,
    *,
    has_image_attachment: bool = False,
    verified_request_text: str | None = None,
) -> str | None:
    if verified is None:
        return None
    from app.modules.math.response_intent import MathResponseMode, classify_math_response_intent

    response_intent = verified.response_intent or classify_math_response_intent(user_text)
    if verified.direct_reply is not None:
        # Built from verified data (check my work); with a photo the model reads it.
        if has_image_attachment:
            return None
        if not response_intent.reveal_answer and verified.canonical_answer is not None:
            return None
        if verified.direct_request_text is not None:
            current = " ".join(user_text.split()).strip()
            origin = " ".join(verified.direct_request_text.split()).strip()
            if current != origin:
                return None
        # A deterministic calculus block can be extracted from only the first
        # clause of a compound request. Keep the model whenever the strict
        # whole-request grammar says something would be dropped (for example,
        # “differentiate ... and tell me a joke”).
        if verified.direct_requires_calculus_guard:
            from app.modules.math.tools.direct_calculus import calculus_direct_request

            guarded_text = (
                lesson_math_text(user_text) if wants_math_explanation(user_text) else user_text
            )
            if calculus_direct_request(
                guarded_text, answer=verified.canonical_answer
            ) is not True and not _closed_school_request(user_text, guarded_text):
                return None
        if verified.canonical_answer is not None:
            if verified.direct_answer_binding != verified.canonical_answer:
                return None
            fences = solver_fences(verified)
            if not any(
                fence.get("type") == "answer" and fence.get("content") == verified.canonical_answer
                for fence in fences
            ):
                return None
        if response_intent.mode == MathResponseMode.ANSWER_ONLY and verified.canonical_answer:
            return f"```answer\n{_chip_answer(verified, answer_only=True)}\n```\n"
        checked = with_requested_check(verified.direct_reply, verified, user_text)
        return working_above_card(checked, user_text)
    if not can_direct_verified_math_reply(
        verified,
        user_text,
        has_image_attachment=has_image_attachment,
        verified_request_text=verified_request_text,
    ):
        return None
    if response_intent.mode == MathResponseMode.ANSWER_ONLY and verified.canonical_answer:
        return f"```answer\n{_chip_answer(verified, answer_only=True)}\n```\n"
    reply = format_direct_math_reply(verified, user_text)
    if should_render_equation_lesson(verified, user_text):
        reply = format_equation_lesson_reply(
            verified,
            include_check=wants_answer_check(user_text),
            include_reasons=wants_detailed_math_explanation(user_text),
        )
    return working_above_card(reply, user_text)
