"""Prompt inject + camera extract → MathIntent."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, replace

from app.core.config import Settings
from app.core.readings import read_off_loop, reading
from app.modules.math import solve as math_solve
from app.modules.math.reply_policy import GRAPH_NO_SUBSTITUTE_CLAUSE, MATH_REPLY_POLICY
from app.modules.math.request_consumption import request_consumption_complete
from app.modules.math.response_intent import (
    MathResponseIntent,
    classify_math_response_intent,
    response_intent_prompt,
)
from app.modules.math.schemas import (
    MathImageExtract,
    MathIntent,
)
from app.modules.math.tools.bare_answer import BARE_ANSWER_NOTE, bare_answer
from app.modules.math.tools.block import VerifiedMathBlock
from app.modules.math.tools.extract import (
    extract_math_intent,
    is_graph_followup,
    resolve_graph_followup,
    trig_domain_would_be_dropped,
)
from app.modules.math.tools.function_def import has_assignment_evaluation_request
from app.modules.math.tools.image_intent import intent_from_image_extract
from app.modules.math.tools.llm_extract import llm_extract_math_intent
from app.modules.math.tools.model_readings import image_intent_on_the_page, unchecked_setup
from app.modules.math.tools.solve_timeouts import note as note_solve_timeout
from app.services.solving import VERIFIED_MATH_BEGIN, VERIFIED_MATH_END
from app.services.workout import SELF_CHECK_PROMPT_RULE

logger = logging.getLogger(__name__)

_MAX_SYMBOLIC_INPUT = 1000

# "Graph it" when nothing earlier in the thread names a function. With no
# guidance the model drew the lines as ASCII art, which the phone cannot render.
_NO_VERIFIED_RESULT = (
    "No verified solver result is available for this request. "
    "Do not claim verification or invent missing measures.\n\n"
    f"{MATH_REPLY_POLICY}"
)
NOTHING_TO_GRAPH = (
    "The user asked to graph the previous problem, but no function y = f(x) to plot "
    "was found in it. Ask in one short sentence which function to graph, for example "
    "`y = 2x + 3`. Do not draw a graph in text: no ASCII or text-art sketch, no table "
    "of points, no Mermaid diagram, and no ```graph fence."
)

# The server's reader missed the expression; the question is still the user's to answer.
UNREAD_EVALUATION_NOTE = (
    "The app's solver could not read the expression to evaluate, so nothing here is "
    "verified. Answer the whole question yourself, working it in full; ask the user to "
    "rewrite it only if you cannot tell what expression they mean. Never answer only the "
    "given assignment, and do not claim a verified result.\n\n"
    f"{MATH_REPLY_POLICY}"
)

VERIFIED_MATH_REPLY_HINT = (
    "Reply guidance for this request: The solver working above is supporting data, "
    "not a request to explain every step. "
    f"{MATH_REPLY_POLICY}"
)


def _intent_preserves_request(user_content: str, intent: MathIntent) -> bool:
    """Apply whole-request guards to intents produced outside the regex seam."""
    if not request_consumption_complete(user_content, intent):
        return False
    return not (
        intent.kind == "equation"
        and trig_domain_would_be_dropped(f"{intent.lhs or ''} {intent.rhs or ''}", user_content)
    )


def _withhold_hint_answer(
    verified: VerifiedMathBlock,
    response_intent: MathResponseIntent,
) -> VerifiedMathBlock:
    """Remove every answer-bearing channel before a hint reaches the model/UI."""
    if verified.canonical_answer is None:
        return replace(verified, response_intent=response_intent)
    next_move = (
        verified.key_steps[0].label
        if verified.key_steps
        else "Identify one reversible operation you can apply next"
    )
    hint = f"{next_move}. Try only that move, then send me your next line."
    safe_text = (
        f"{VERIFIED_MATH_BEGIN}\n"
        "Hint-only request: the verified final result and answer-bearing formulas are withheld.\n"
        f"Permitted next-move hint: {next_move}.\n"
        f"{VERIFIED_MATH_END}"
    )
    return replace(
        verified,
        text=safe_text,
        canonical_fence=None,
        canonical_fences=[],
        canonical_answer=None,
        display_answer=None,
        key_steps=(),
        check_latex=None,
        alternate_method_note=None,
        direct_reply=f"**Hint:** {hint}",
        direct_answer_binding=None,
        response_intent=response_intent,
    )


@reading(declined=False)
def needs_symbolic_math(text: str, *, has_image_attachment: bool = False) -> bool:
    from app.modules.math import match as math_match
    from app.modules.math.tools.keyboard_notation import keyboard_math_to_plain
    from app.modules.math.tools.lesson import strip_lesson_prefixes

    # Match scanning rejects normalized inputs above this bound. Reject the
    # raw message before repeatedly stripping lesson phrases too; otherwise a
    # maximum-size string of repeated prefixes makes the stripping loop copy
    # a shrinking string once per occurrence.
    if len(text) > _MAX_SYMBOLIC_INPUT:
        return False
    from app.modules.math.tools.word_problem import word_problem_candidate
    from app.modules.math.tools.work_request import parse_work_request

    if parse_work_request(text) is not None:
        return True
    # "ok cool. what is 2+2": the question after the chat, as the extractor reads it.
    from app.modules.math.match.chatter import question_after_chat

    question = question_after_chat(text)
    if question is not None and needs_symbolic_math(
        question, has_image_attachment=has_image_attachment
    ):
        return True

    # Teaching / answer-style wrappers are response metadata, not part of the
    # expression. The extractor already removes them, so the cheaper routing
    # gate must inspect the same underlying math or it will skip SymPy before
    # extraction ever runs (for example, ``Show steps: 2x+3=11``).
    math_text = strip_lesson_prefixes(text)
    if math_match.needs_symbolic(math_text, has_image_attachment=has_image_attachment):
        return True
    # The math keyboard's LaTeX (``$\int_{0}^{1}…$``, ``$\binom{5}{2}$``) reads
    # as math once it is in the notation the extractors know.
    plain = keyboard_math_to_plain(math_text)
    if plain != math_text and math_match.needs_symbolic(
        plain, has_image_attachment=has_image_attachment
    ):
        return True
    # Maths said in words ("what is 3 squared"), in its symbols (match/spoken.py).
    from app.modules.math.match.spoken import spoken_math_to_plain

    spoken = spoken_math_to_plain(math_text)
    if spoken != math_text and math_match.needs_symbolic(
        spoken, has_image_attachment=has_image_attachment
    ):
        return True
    # An algebra word problem states no equation; the translation is tried
    # only after every extractor has passed on it.
    if has_image_attachment:
        return False
    from app.modules.math.tools.word_templates import word_template_setup

    return word_problem_candidate(text) or word_template_setup(text) is not None


@dataclass(frozen=True)
class MathReading:
    """What reading a maths request found, before any model is asked.

    ``note`` set: the turn's maths block is that note and nothing is solved. Otherwise
    ``content`` is the request to solve (a graph follow-up or an opened earlier problem
    replaces the message) and ``intent`` what the regex readers made of it, if anything.
    """

    content: str
    note: str | None = None
    intent: MathIntent | None = None
    answered: bool = False


def borrows_earlier_lines(text: str) -> bool:
    """Whether ``read_math_request`` may solve ``text`` from the user's earlier lines:
    "graph it" plots the last plottable one, and a fragment ("5", "x") continues the open
    equation. A gate on what the readers read holds those lines to it too."""
    from app.modules.math.followup import is_fragment

    return is_graph_followup(text) or is_fragment(text)


def read_math_request(
    user_content: str,
    *,
    has_image_attachment: bool,
    image_math_extract: MathImageExtract | None,
    needs_math: bool | None,
    prior_user_messages: list[str] | None,
) -> MathReading:
    """The sync, CPU-bound half of ``build_math_augmentation``: runs in the SymPy pool.

    The graph reader parses with SymPy and solves; on the event loop one message held
    it for 56 s (code-health audit SCALE-01).
    """
    if image_math_extract is None:
        user_content, skip_math = resolve_graph_followup(user_content, prior_user_messages)
        if skip_math:
            return MathReading(user_content, note=NOTHING_TO_GRAPH, answered=True)
    if needs_math is None:
        needs_math = needs_symbolic_math(user_content, has_image_attachment=has_image_attachment)
    if not needs_math and image_math_extract is None:
        from app.modules.math.followup import open_math_problem

        opened = open_math_problem(user_content, prior_user_messages)
        if opened:
            user_content = opened
            needs_math = True
    if not needs_math:
        return MathReading(user_content, answered=True)

    if image_math_extract is not None:
        # OCR already produced a Pydantic-validated extract — map it straight
        # to MathIntent (do not re-parse through the text regex, which mangles
        # unicode ops / abs bars a photographed problem can contain).
        intent: MathIntent | None = intent_from_image_extract(image_math_extract)
        if intent is not None:
            audit_sources = [user_content]
            if image_math_extract.source_text:
                audit_sources.append(image_math_extract.source_text)
            if image_math_extract.alternate_source_text:
                audit_sources.append(image_math_extract.alternate_source_text)
            if any(not _intent_preserves_request(source, intent) for source in audit_sources):
                intent = None
            elif not image_intent_on_the_page(intent, image_math_extract):
                intent = None
    else:
        intent = extract_math_intent(user_content)
    if intent is not None:
        return MathReading(user_content, intent=intent)
    if has_image_attachment:
        lines = [
            "The user attached an image that may contain a math problem. "
            "Extract the equation as lhs/rhs only if the notation and measures are legible. "
            "Do NOT claim SymPy verification unless a verified system block is present. "
            "Use $...$ for formulas. Do not emit ```geometry / ```graph. "
            "Never invent measures.",
            MATH_REPLY_POLICY,
        ]
        return MathReading(user_content, note="\n".join(lines), answered=True)
    if image_math_extract is not None:
        return MathReading(user_content)
    from app.modules.math.solve.extract_eq import rejected_equality_chain

    if rejected_equality_chain(user_content):
        # An empty extract is also what a regex miss looks like. A chain
        # must not fall through to the LLM extractor, which can rewrite
        # ``a=b=c`` into one solvable equation.
        return MathReading(
            user_content,
            note=(
                "The message chains equalities (a=b=c). Ask which single "
                "equation to solve. Do not collapse the chain or claim a "
                "verified answer.\n\n"
                f"{MATH_REPLY_POLICY}"
            ),
            answered=True,
        )
    if has_assignment_evaluation_request(user_content):
        # The deterministic substitution parser saw an assignment followed by
        # an evaluation request, but could not parse the requested expression.
        # Do not let a word-problem or LLM fallback certify only the easy
        # binding (for example x=-5) while silently dropping malformed x^2.
        # The parser's miss is not the user's: "Express z = 1 - i√3 in polar form
        # and evaluate z^10" was answered "Could you rewrite it?" (2026-10-31).
        return MathReading(user_content, note=UNREAD_EVALUATION_NOTE, answered=True)
    if bare_answer(user_content):
        return MathReading(user_content, note=BARE_ANSWER_NOTE, answered=True)
    return MathReading(user_content)


async def build_math_augmentation(
    user_content: str,
    settings: Settings,
    *,
    has_image_attachment: bool = False,
    image_math_extract: MathImageExtract | None = None,
    needs_math: bool | None = None,
    prior_user_messages: list[str] | None = None,
    response_intent_text: str | None = None,
) -> tuple[str | None, VerifiedMathBlock | None]:
    """Compute the verified-math system block (or None) without mutating messages.

    Safe to run concurrently with web-search augmentation on the same base
    prompt — the caller injects returned blocks after gather.

    ``needs_math`` lets a caller that already evaluated the math-intent signal
    (e.g. prompt_builder uses it to gate the "calculating" status) pass it
    through so the same message isn't scanned twice per turn. When None,
    needs_symbolic_math is evaluated here (the historical behavior, kept for
    any caller that doesn't pre-compute it).

    ``prior_user_messages`` lets ``graph it`` reuse the last plottable
    equation or curve from this thread.
    """
    if not settings.math_tools_enabled:
        return None, None
    reading = await read_off_loop(
        read_math_request,
        user_content,
        has_image_attachment=has_image_attachment,
        image_math_extract=image_math_extract,
        needs_math=needs_math,
        prior_user_messages=prior_user_messages,
        timeout=settings.subject_read_timeout_seconds,
    )
    if reading is None:
        # Reading gave up (a timeout, or no pool): a maths turn with nothing verified.
        return _unverified_math_note(None), None
    if reading.answered:
        return reading.note, None
    user_content, intent = reading.content, reading.intent
    if intent is None:
        intent = await _model_math_intent(
            user_content, settings, word_problem=image_math_extract is None
        )

    if intent is None:
        return _NO_VERIFIED_RESULT, None
    if intent.word_problem is not None and not intent.word_problem.read_from_text:
        # A translation is never a verified card (``tools/model_readings.py``).
        note = await unchecked_setup(intent.word_problem, settings)
        unverified = _unverified_math_note("word_problem")
        return (f"{note}\n\n{unverified}" if note else unverified), None

    from app.modules.math import tools as mt

    verified = await mt._build_verified_block_async(intent, settings)
    if not verified:
        # Intent matched but SymPy timed out / rejected / had no builder result.
        # Inject honesty so the model does not reuse the same "verified" UX.
        return _unverified_math_note(intent.kind), None
    # A terse follow-up is solved from the prior mathematical problem, but its
    # own wording still controls presentation.  Otherwise the final fence pass
    # sees the original answer-only request and removes the freshly requested
    # working from “Show me” / “Do it again”.
    response_intent = classify_math_response_intent(response_intent_text or user_content)
    if intent.kind == "work_check":
        # The work block applies hint mode itself: the slip as a question, no
        # fix, no answer. When every line is right and finished, the answer
        # it carries is the student's own, and the reply says the work is right.
        if not response_intent.reveal_answer and verified.canonical_answer is not None:
            response_intent = replace(response_intent, reveal_answer=True)
        verified = replace(verified, response_intent=response_intent)
    elif not response_intent.reveal_answer:
        verified = _withhold_hint_answer(verified, response_intent)
    else:
        verified = replace(verified, response_intent=response_intent)
    # Keep presentation guidance adjacent to the result, after any worked
    # steps, so the model does not treat solver data as a tutorial request.
    # The canonical block remains data-only for direct replies/fence validation.
    return (
        f"{verified.text}\n\n{response_intent_prompt(response_intent)}\n{VERIFIED_MATH_REPLY_HINT}",
        verified,
    )


async def _model_math_intent(
    user_content: str, settings: Settings, *, word_problem: bool
) -> MathIntent | None:
    """The intent no regex extractor found, from the two model helpers side by side.

    A translated word problem wins, as before. Otherwise the gate fired but no
    extractor matched (the "Couldn't verify under a correct ∫ x²" class): one
    bounded structured extraction on a fast alias, whose candidate still has to
    survive SymPy. Both start at once under one budget, so the extraction no
    longer waits out a translation that finds nothing (up to 6 s); when the
    translation wins, the extraction is dropped. That costs one small extraction
    call on word problems the translation reads; gate-miss and regex-hit turns
    never get here. A translation still running when the budget ends gives way
    to an extraction that has finished.
    """
    from app.modules.math.tools.word_problem import word_problem_intent

    extract = asyncio.ensure_future(_llm_extract_preserving(user_content, settings))
    budget = settings.math_model_intent_budget_seconds
    try:
        async with asyncio.timeout(budget):
            if word_problem:
                translated = await word_problem_intent(user_content, settings)
                if translated is not None:
                    return translated
            return await extract
    except TimeoutError:
        logger.warning("math model helpers ran past their %ss budget", budget)
        if extract.done() and not extract.cancelled() and extract.exception() is None:
            return extract.result()
        return None
    finally:
        # Dropped (or finished): either way nothing is left running or unread.
        extract.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await extract


async def _llm_extract_preserving(user_content: str, settings: Settings) -> MathIntent | None:
    intent = await llm_extract_math_intent(user_content, settings)
    if intent is not None and not await read_off_loop(
        _model_intent_is_users,
        user_content,
        intent,
        timeout=settings.subject_read_timeout_seconds,
    ):
        return None
    return intent


def _model_intent_is_users(user_content: str, intent: MathIntent) -> bool:
    """A model's reading may be solved and certified only when it is the user's own maths:
    the whole request, and an equation or expression the user wrote (``tool_check``)."""
    from app.modules.math.tool_check import intent_in_user_text

    return _intent_preserves_request(user_content, intent) and intent_in_user_text(
        intent, user_content
    )


def _unverified_math_note(kind: str | None) -> str:
    """System note when symbolic intent fired but no VerifiedMathBlock landed."""
    detected = f" (kind={kind})" if kind else ""
    return (
        f"Math note: a symbolic problem was detected{detected}, "
        "but a verified result could not be produced "
        "(timeout, unsupported expression, or incomplete extract).\n"
        "Do NOT claim the answer was "
        "verified. Never tell the user that a result is unverified, not "
        "verified, or could not be verified. "
        "Write the result in `$...$`. Do NOT emit ```answer, ```geometry, or ```graph. "
        "Do not invent geometry/graph dimensions or point lists. "
        f"{GRAPH_NO_SUBSTITUTE_CLAUSE}\n\n"
        f"{MATH_REPLY_POLICY} {SELF_CHECK_PROMPT_RULE}"
    )


async def _build_verified_block_async(
    intent: MathIntent, settings: Settings
) -> VerifiedMathBlock | None:
    """Run the sync, CPU-bound SymPy work in a bounded subprocess with a
    hard timeout + SIGTERM on timeout.

    ``_build_verified_block`` calls into SymPy's ``solve``/``integrate``/etc.,
    which are synchronous and can take arbitrarily long on a pathological
    expression. Running them on the shared default ``asyncio.to_thread`` pool
    would (a) starve unrelated async work and (b) leak the thread on timeout
    (the await cancels but the thread keeps running). Isolated 1-worker
    process slots can be hard-killed on timeout without terminating siblings.
    """
    from app.core.sympy_executor import run_sympy
    from app.modules.math import tools as mt

    try:
        return await run_sympy(
            mt._build_verified_block,
            intent,
            settings,
            timeout=settings.stem_solve_timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "math_tools solve timed out after %ss for kind=%s",
            settings.stem_solve_timeout_seconds,
            intent.kind,
        )
        note_solve_timeout(intent.kind)
        return None
    except math_solve.SolveServiceError as exc:
        # Sync builder also catches this; keep the async boundary honest if a
        # patched/edge path raises through the executor.
        # The class only: a SolveServiceError's message quotes the user's expression.
        logger.info("math_tools skipped: %s", type(exc).__name__)
        return None
    except Exception:
        # BrokenProcessPool / cancelled sibling futures after another caller's
        # timeout kill — degrade to the honesty note, do not fail the turn.
        logger.warning(
            "math_tools solve failed for kind=%s",
            intent.kind,
            exc_info=True,
        )
        return None
