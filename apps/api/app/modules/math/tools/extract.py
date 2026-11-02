"""Ordered MathIntent extraction behind the stable public seam."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from app.core.readings import reading
from app.modules.math.function_names import MATH_FUNCTION_NAMES
from app.modules.math.match.literal_plot import literal_plot_point
from app.modules.math.request_consumption import request_consumption_complete
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.expr_rewrite import math_expr_or_none
from app.modules.math.tools.extractors.algebra import (
    ALGEBRA_EXTRACTORS,
    PRE_DISCRETE_ALGEBRA_EXTRACTORS,
    oversized_system,
)
from app.modules.math.tools.extractors.calculus import CALCULUS_EXTRACTORS
from app.modules.math.tools.extractors.calculus_applications import CALCULUS_APPLICATION_EXTRACTORS
from app.modules.math.tools.extractors.discrete_statistics import DISCRETE_STATISTICS_EXTRACTORS
from app.modules.math.tools.extractors.functions import (
    FUNCTION_EXTRACTORS,
    function_analysis_constraint_would_be_dropped,
)
from app.modules.math.tools.extractors.geometry_graph import (
    GEOMETRY_GRAPH_EXTRACTORS,
    SOLID_EXTRACTOR,
)
from app.modules.math.tools.extractors.geometry_request import finish_geometry_intent
from app.modules.math.tools.extractors.readings import read
from app.modules.math.tools.function_def import (
    has_assignment_evaluation_request,
    peel_function_definition,
)

# "graph it" after an equation lives in its own module; callers keep this public path.
from app.modules.math.tools.graph_followup import is_graph_followup as is_graph_followup
from app.modules.math.tools.graph_followup import (
    resolve_graph_followup as resolve_graph_followup,
)
from app.modules.math.tools.keyboard_notation import (
    keyboard_bounds_read_first,
    keyboard_math_to_plain,
)
from app.modules.math.tools.request_text import _split_response_instruction_sentence
from app.modules.math.tools.school import SCHOOL_EXTRACTORS

_INTENT_EXTRACTORS: Sequence[Callable[[str], MathIntent | None]] = (
    SOLID_EXTRACTOR,
    # Ahead of the school and algebra extractors. "area between y=x and y=x^2
    # from 0 to 1" reads as two simultaneous equations to the algebra side,
    # which is how it once answered with the curves' intersection points.
    *CALCULUS_APPLICATION_EXTRACTORS,
    *SCHOOL_EXTRACTORS,
    *GEOMETRY_GRAPH_EXTRACTORS,
    *FUNCTION_EXTRACTORS,
    *CALCULUS_EXTRACTORS,
    *PRE_DISCRETE_ALGEBRA_EXTRACTORS,
    *DISCRETE_STATISTICS_EXTRACTORS,
    *ALGEBRA_EXTRACTORS,
)

_MAKE_SUBJECT_RE = re.compile(
    r"\bmake\s+([a-zA-Z])\s+the\s+subject\s+of\s+(?:the\s+formula\s+)?(\S.*=.*?)[.?!]?$",
    re.IGNORECASE,
)
_ROOTS_RE = re.compile(r"\b(?:find(?:\s+the)?\s+)?(?:roots|zeros)\s+of\s+(.+)", re.IGNORECASE)
_TRIG_FUNCTION_RE = re.compile(
    r"\b(?:sin|cos|tan|cot|sec|csc)\s*(?:\^\s*(?:\{\d+\}|\d+)|[²³])?\s*\(",
    re.IGNORECASE,
)
_RESTRICTED_TRIG_DOMAIN_RE = re.compile(
    r"[<>\u2264\u2265\u2208\u2102\u2124\u2115\u211a\[\]]"
    r"|\\in\b|\\mathbb\s*\{[CZNQ]\}"
    r"|\b(?:complex|imaginary|integers?|naturals?|rationals?|irrationals?|"
    r"positive|negative|nonnegative|nonpositive|degrees?)\b"
    r"|\bin\s*(?:\(|[CZNQ]\b)",
    re.IGNORECASE,
)
_INTERVAL_BOUND = (
    r"[-+]?\s*(?:\d+(?:\.\d+)?|\.\d+|pi|π|\\pi|oo|infinity|∞)"
    r"(?:\s*[*/]\s*(?:\d+(?:\.\d+)?|pi|π|\\pi))*"
)
_TRIG_INTERVAL_RE = re.compile(
    rf"\bfrom\s+{_INTERVAL_BOUND}\s+to\s+{_INTERVAL_BOUND}"
    rf"|\bbetween\s+{_INTERVAL_BOUND}\s+and\s+{_INTERVAL_BOUND}"
    r"|\bwithin\s+(?:the\s+)?interval\b",
    re.IGNORECASE,
)


def trig_domain_would_be_dropped(expression: str, text: str) -> bool:
    """The trig solver owns all real values, not an interval or another domain.

    Equation extraction peels surrounding prose. Do not silently drop a
    user-specified domain and certify an all-real answer in its place.
    Explicit real-domain wording remains supported.
    """
    return bool(
        _TRIG_FUNCTION_RE.search(expression)
        and (_RESTRICTED_TRIG_DOMAIN_RE.search(text) or _TRIG_INTERVAL_RE.search(text))
    )


# An area, arc length or volume over a region is a calculus application, and
# the curves in it are the *input*. No extractor here solves one, so the whole
# shape is refused at the funnel rather than left for whichever extractor
# recognises half of it.
#
# Measured before this guard: "area between y=x and y=x^2 from 0 to 1" was
# claimed by the simultaneous-system extractor and answered
# `x = 0, y = 0; x = 1, y = 1` - where the curves *cross*, not the area
# between them, which is 1/6. Guarding only that extractor moved the bug
# rather than fixing it: the question then fell through to the single-equation
# extractor, which answered `y = 0`.
#
# A verified block tells the model not to recompute, so a confident answer to
# a question nobody asked is worse than no block at all.
# #1344 refused every area/arc-length/volume-over-a-region question outright,
# after "area between y=x and y=x^2 from 0 to 1" was answered with the curves'
# *intersection points*. Three of those shapes are solved now, so the guard
# moved from *before* the extractors to *after* them: whatever the calculus
# application extractors claim is let through, and whatever they decline is
# still refused.
#
# It has to stay this broad. Narrowing it to the unimplemented wordings
# reopened the original bug immediately: "area between y=x and y=x^2" with no
# stated interval is declined by the application extractor, fell through to the
# algebra side, and answered `x = 0, y = 0; x = 1, y = 1` all over again.
_REGION_QUESTION_RE = re.compile(
    r"\b(?:area|arc\s+length|volume)\b[^.?!]{0,80}?"
    r"\b(?:between|under|bounded\s+by|enclosed\s+by|of\s+revolution|revolved|rotated)\b",
    re.IGNORECASE,
)

_SOLVED_REGION_OPS = {
    "area_between_curves",
    "arc_length",
    "volume_revolution_x",
    "volume_revolution_y",
}


# ``f(x)``, ``g(t)``: a single-letter function of a single-letter variable.
_FUNCTION_NOTATION = re.compile(r"(?<![A-Za-z\\])[a-zA-Z]\s*\(\s*[a-zA-Z]\s*\)")
# Prose before an equation that ends inside a function call: the equation's left side was
# cut out of ``log_(2)(x+1)`` or ``log _2(x+1)``, so its "equation" is 2(x+1) = 3.
_CUT_FROM_A_CALL = re.compile(
    r"(?:[_^]|\b(?:log|ln|lg|sin|cos|tan|sec|csc|cot|sqrt|exp))\s*$", re.IGNORECASE
)

_FUNCTION_NAMES = re.compile(
    r"\b(?:sqrt|cbrt|sin|cos|tan|cot|sec|csc|arcsin|arccos|arctan|log|ln|exp|abs|pi)\b",
    re.IGNORECASE,
)


def _numeric_statement(text: str, intent: MathIntent) -> bool:
    """``15% of 80 = 12?`` or ``sqrt(16) = 4?`` is a claim to check, not an equation.

    Neither side has an unknown, so solving it can only answer "no solution"
    or "all real numbers", which is wrong or meaningless to a student. A
    typed ``solve 0 = 1`` still reads as the contradiction it is.
    """
    if intent.kind not in {"equation", "inequality"} or intent.system_equations:
        return False
    sides = _FUNCTION_NAMES.sub(" ", f"{intent.lower or ''} {intent.lhs or ''} {intent.rhs or ''}")
    if re.search(r"[A-Za-df-z]", sides):  # e is Euler's number, never the unknown
        return False
    return re.search(r"\bsolve\b", text, re.IGNORECASE) is None


@reading(declined=None)
def extract_math_intent(text: str) -> MathIntent | None:
    intent = _extract_math_intent_any(text)
    if intent is None or (intent.kind == "graph" and not intent.expr):
        intent = _heard_math_intent(text) or intent
    if intent is None or _numeric_statement(text, intent):
        return None
    if intent.kind == "complex":
        return _letter_i_reading(text, intent)
    if intent.kind == "point":
        intent.plot_point = literal_plot_point(text)
    return intent


def _letter_i_reading(text: str, intent: MathIntent) -> MathIntent | None:
    """A complex reading checked against the whole message. A reader may see one sentence
    of it: "Let i be the interest rate. Simplify 1000(1+i)^2 - 1000" made -1000 + 2000i.
    Where the message says i is a rate, an index or a vector, i is a letter."""
    from app.modules.math.tools.school.complex import imaginary_unit_meant, lone_i

    expression = intent.expr or ""
    if not lone_i(expression) or imaginary_unit_meant(text, expression):
        return intent
    if intent.school_op not in {"eval", "expand"}:
        return None
    reread = MathIntent(
        kind="calculus",
        expr=expression,
        operation="expand" if intent.school_op == "expand" else "simplify",
        variable="i",
    )
    reread._request_text = intent._request_text
    return reread


def _heard_math_intent(text: str) -> MathIntent | None:
    """The reading of maths said in words ("what is 3 squared", "graph y equals x
    squared", match/spoken.py), when the written text gave none (or a graph with no
    function). Kept only when it reads: "plus I'm over it" stays chat."""
    from app.modules.math.match.spoken import spoken_math_to_plain

    spoken = spoken_math_to_plain(text)
    if spoken == text:
        return None
    heard = _extract_math_intent_any(spoken)
    if heard is None or (heard.kind == "graph" and not heard.expr):
        return None
    heard._request_text = text.strip()
    return heard


def _extract_math_intent_any(text: str) -> MathIntent | None:
    # iOS smart punctuation turns derivative primes into curly apostrophes.
    # Normalize them before every extractor while retaining the original
    # request text for whole-request direct-reply checks.
    normalized = text.translate({ord("\u2019"): "'", ord("\u2032"): "'", ord("\u2035"): "'"})
    # Read on the raw text: prepare() collapses the newlines that separate
    # a student's lines of work.
    work = work_check_intent(normalized)
    if work is not None:
        work._request_text = text.strip()
        return work
    # The scanner caption is English plus a confirmed line. Solving the whole
    # caption leaves "I read this as" unconsumed, so a bare equation never
    # verifies. The line after the prefix is the problem.
    from app.services.subject_scan import confirmed_scan_reading

    reading = confirmed_scan_reading(normalized)
    if reading and reading.strip() != normalized.strip():
        intent = _extract_math_intent(reading)
        if intent is not None and request_consumption_complete(reading, intent):
            intent._request_text = text.strip()
            return intent
    # The math keyboard's LaTeX (``\int_{0}^{1}…\,dx``, ``\frac{d}{dx}``,
    # ``\binom``, ``30^{\circ}``) in the plain notation the extractors read.
    # A product's ``n=1`` bound reads as an equation, so it goes plain first.
    plain = keyboard_math_to_plain(normalized)
    readings = [normalized, plain]
    if keyboard_bounds_read_first(normalized):
        readings.reverse()
    for candidate in dict.fromkeys(readings):
        intent = _extract_math_intent(candidate)
        if intent is not None and request_consumption_complete(candidate, intent):
            intent._request_text = text.strip()
            return intent
    # A second sentence can specify the teaching method or output format
    # without changing the mathematical input: ``cos(75°). Use an angle-sum
    # identity``. Give every extractor one shared retry at that sentence
    # boundary instead of teaching each subject a growing list of phrasings.
    presentation_free = _split_response_instruction_sentence(normalized).strip()
    if presentation_free and presentation_free != normalized.strip():
        intent = _extract_math_intent(presentation_free)
        if intent is not None and request_consumption_complete(presentation_free, intent):
            intent._request_text = text.strip()
            return intent
    # "Explain how to solve 2x+3<7" / "show steps for …": the teaching words
    # are response metadata. Some extractors find math inside prose; the
    # stricter ones (inequalities) need them gone. One retry, same grammar.
    from app.modules.math.tools.lesson import lesson_math_text

    stripped = lesson_math_text(normalized)
    if stripped and stripped != normalized.strip() and _bare_math_request(stripped):
        intent = _extract_math_intent(stripped)
        if intent is not None and request_consumption_complete(stripped, intent):
            intent._request_text = text.strip()
            return intent
    # Chat before the question: "ok cool. what is 2+2" (match/chatter.py). The
    # question alone has no chat left, so this retries once.
    from app.modules.math.match.chatter import question_after_chat

    question = question_after_chat(normalized)
    if question is not None:
        intent = _extract_math_intent_any(question)
        if intent is not None:
            intent._request_text = text.strip()
            return intent
    # A system longer than the solver allows must not fall through to the
    # first free-standing equation and certify that one clause.
    if oversized_system(normalized):
        return None
    recovered = _intent_from_free_standing_equation(normalized)
    if recovered is not None:
        recovered._request_text = text.strip()
        return recovered
    return None


def _intent_from_free_standing_equation(text: str) -> MathIntent | None:
    """Solve the one equation in a file excerpt or a one-sentence caption.

    The caption and a trailing "Show your work" are not part of the equation.
    A prefix that is itself a math ask (``solve``, ``area of the circle``)
    keeps the normal extractors.
    """
    from app.modules.math.match.scan import _without_attachment_markers, has_math_keyword
    from app.modules.math.solve.extract_eq import free_standing_equation

    marked = any(head in text for head in ("[File:", "[Image:", "[File attached:", "[File ("))
    found = free_standing_equation(_without_attachment_markers(text))
    if found is None:
        return None
    prefix, problem, suffix = found
    # ``Solve x^2=4 where x is positive`` must stay unverified. A file
    # excerpt may keep a trailing "Show your work". A caption with nothing
    # after the equation is the equation.
    if not marked and suffix.strip(" .!?"):
        return None
    if has_math_keyword(prefix.lower()) or _CUT_FROM_A_CALL.search(prefix):
        return None
    intent = _extract_math_intent(problem)
    if intent is not None and request_consumption_complete(problem, intent):
        return intent
    return None


def work_check_intent(text: str) -> MathIntent | None:
    """A check-my-work request with the student's lines, or a bare worked column."""
    from app.modules.math.response_intent import classify_math_response_intent
    from app.modules.math.tools.work_request import parse_work_request

    request = parse_work_request(text)
    if request is None:
        return None
    # A hint request the work grammar did not word-match is still a hint.
    hint_only = request.hint_only or not classify_math_response_intent(text).reveal_answer
    return MathIntent(
        kind="work_check",
        work_lines=list(request.lines),
        work_hint_only=hint_only,
        variable=request.variable,
        operation="solve",
    )


_SOLVE_VERB_RE = re.compile(
    r"^(?:solve|simplify|differentiate|integrate|factor|expand|evaluate)\s+"
    r"(?:the\s+(?:inequality|equation|system)\s+)?"
)
_PROSE_WORD_RE = re.compile(r"[a-z]{3,}")
_FUNCTION_WORDS = MATH_FUNCTION_NAMES


def _bare_math_request(text: str) -> bool:
    """Only math, or a math verb and math, is left: "why y=mx+b" is still prose."""
    body = _SOLVE_VERB_RE.sub("", text.lower().strip())
    return all(word in _FUNCTION_WORDS for word in _PROSE_WORD_RE.findall(body))


def _extract_math_intent(text: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    cleaned = mtm.prepare(text)
    if not cleaned:
        return None
    from app.modules.math.tools.extractors.teaching import closed_teaching_declined

    if closed_teaching_declined(cleaned):
        return None
    if oversized_system(cleaned):
        return None
    # Function analysis currently verifies the maximal real domain only.
    # Refuse the whole extraction before inequality/algebra fallbacks can
    # verify just the trailing restriction and silently ignore the actual ask.
    if function_analysis_constraint_would_be_dropped(cleaned):
        return None
    subject = _MAKE_SUBJECT_RE.search(cleaned)
    if subject is not None:
        # "make r the subject of A = pi r^2" is "solve A = pi r^2 for r".
        cleaned = f"solve {subject.group(2).strip()} for {subject.group(1)}"
    roots_match = _ROOTS_RE.search(cleaned)
    if roots_match:
        # "zeros of f(x) = x^2 - 4x": the function's formula, not the equation f(x) = ….
        tail = math_expr_or_none(peel_function_definition(roots_match.group(1)))
        if tail is not None and "=" not in tail:
            cleaned = f"solve {tail} = 0"
    region_question = _REGION_QUESTION_RE.search(cleaned) is not None
    for extractor in _INTENT_EXTRACTORS:
        # The math gate may have read the line already: its reads are reused.
        intent = read(extractor, cleaned)
        if intent is not None:
            if region_question and intent.school_op not in _SOLVED_REGION_OPS:
                # A region question the application extractors declined must
                # not be answered by whichever other extractor recognises half
                # of it. Declining means a given is missing, not that some
                # other reading is available.
                return None
            # Successful substitution arithmetic wins earlier. If that did
            # not parse, never certify just the given assignment(s) while
            # silently ignoring the requested evaluation.
            if intent.kind in {"equation", "system"} and has_assignment_evaluation_request(text):
                return None
            if intent.kind in {"equation", "system"} and _FUNCTION_NOTATION.search(cleaned):
                # ``f(x) = 2x + 3`` names a function. Solved as an equation it
                # reads ``f * x`` and answers for ``f`` or in terms of it.
                return None
            if intent.kind == "equation" and trig_domain_would_be_dropped(
                f"{intent.lhs or ''} {intent.rhs or ''}", text
            ):
                return None
            return finish_geometry_intent(intent, cleaned)
    return None
