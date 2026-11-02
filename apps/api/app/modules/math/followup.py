"""Presentation-only context for a short follow-up to the immediately prior math turn."""

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.modules.math.response_intent import (
    MathResponseMode,
    classify_math_response_intent,
)
from app.modules.math.tools.prompt import needs_symbolic_math
from app.services.answer_fence import answer_fence_value
from app.services.number_text import FRACTION_OR_DECIMAL
from app.services.student_claim import CHECK, CLAIM_LEAD

MATH_FOLLOWUP_HINT = (
    "This short request refers to the immediately preceding math exchange. Give only "
    "the requested reasoning, proof, hint, or examples, then stop. For 'how' or 'why', "
    "show the calculation or mathematical argument connecting the preceding problem "
    "to its result, stating any theorem needed and showing how it applies. "
    "A request for a proof, hint, or examples "
    "keeps its requested scope; a hint must not reveal the solution. Do not add "
    "unrequested comparisons, unit conversions, real-world applications, history, "
    "trivia, fun facts, or a second "
    "recap/explanation section. Retain units, conditions, and mathematical distinctions "
    "needed for correctness. Previous results are conversation context, not fresh "
    "solver verification."
)


def _message_field(message: Any, field: str) -> Any:
    if isinstance(message, Mapping):
        return message.get(field)
    return getattr(message, field, None)


def _referenced_math_problem(
    query: str | None,
    recent: Sequence[Any],
    *,
    working_only: bool,
    blocked: Callable[[str], bool] | None = None,
) -> str | None:
    """Return the problem from an adjacent chain of math follow-ups.

    A learner may naturally say ``What?`` → ``Show me`` → ``Do it again``.
    Walk backward only through those short, explicitly referential exchanges;
    any unrelated or incomplete exchange still stops the lookup immediately.
    """
    response = classify_math_response_intent(query or "")
    if not response.referential or len(recent) < 2:
        return None
    if working_only and response.mode not in {
        MathResponseMode.EXPLAIN,
        MathResponseMode.STEPS,
        MathResponseMode.DETAILED,
    }:
        return None
    # Four complete exchanges are enough for a natural clarification chain
    # without turning this into a search over stale chat history.
    cursor = len(recent) - 2
    checked = 0
    while cursor >= 0 and checked < 4:
        question, answer = recent[cursor : cursor + 2]
        if (
            _message_field(question, "role") != "user"
            or _message_field(answer, "role") != "assistant"
        ):
            return None
        prior = _message_field(question, "content")
        reply = _message_field(answer, "content")
        if not (
            isinstance(prior, str) and prior.strip() and isinstance(reply, str) and reply.strip()
        ):
            return None
        if blocked is not None and blocked(prior):
            return None
        if needs_symbolic_math(prior):
            return prior
        if not classify_math_response_intent(prior).referential:
            return None
        cursor -= 2
        checked += 1
    return None


# A lone unknown or value: ``x``, ``$\theta$``, ``5``, ``-2.5``, ``for y``.
_FRAGMENT_RE = re.compile(
    r"(?:for\s+)?(?:[a-z\u03b1-\u03c9]|\\[a-z]+|[-+\u2212]?\d+(?:\.\d+)?)\s*[.?!]?",
    re.IGNORECASE,
)
_RELATION_RE = re.compile(r"[=<>≤≥≠]|\\(?:leq|geq|le|ge|lt|gt|neq|ne)(?![a-z])", re.IGNORECASE)


def is_fragment(text: str) -> bool:
    """A lone number or letter (``5``, ``x``, ``for x``): part of the open problem, not one."""
    cleaned = " ".join(text.strip().strip("$").split())
    return bool(_FRAGMENT_RE.fullmatch(cleaned))


def open_math_problem(text: str, prior_user_messages: list[str] | None) -> str | None:
    """The equation still in progress when this message is only a fragment.

    ``5`` or ``x`` after ``3x^2 + 3 = 5`` is the same problem, not a new chat.
    Anything else is a message of its own: ``What?`` asks about the last reply
    and ``[4,4]`` is new input, and re-solving ``convert 1 m to cm`` answered
    neither. Earlier fragments on the same equation are walked past; any
    other message ends it.
    """
    if not prior_user_messages or not is_fragment(text):
        return None
    from app.modules.turn_reading.routing import is_lightweight_chat_turn

    if is_lightweight_chat_turn(" ".join(text.split())):
        return None
    for prior in reversed(prior_user_messages):
        if not prior or not prior.strip() or is_fragment(prior):
            continue
        if _RELATION_RE.search(prior) and needs_symbolic_math(prior):
            return prior
        return None
    return None


def is_math_followup(
    query: str | None,
    recent: Sequence[Any],
    *,
    blocked: Callable[[str], bool] | None = None,
) -> bool:
    """Require one complete adjacent user/assistant math exchange; never scan older topics."""
    return _referenced_math_problem(query, recent, working_only=False, blocked=blocked) is not None


def math_working_followup_problem(
    query: str | None,
    recent: Sequence[Any],
    *,
    blocked: Callable[[str], bool] | None = None,
) -> str | None:
    """Return the adjacent problem when a follow-up asks for its verified working."""
    return _referenced_math_problem(query, recent, working_only=True, blocked=blocked)


# A short go-ahead after the assistant wrote an equation. These are not
# "do it again" (that re-solves the user's earlier problem).
_PROCEED_PHRASES = frozenset(
    {
        "do it",
        "do that",
        "do this",
        "solve it",
        "solve this",
        "solve that",
        "show the steps",
        "show steps",
        "show me",
        "work it out",
        "go ahead",
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "please",
        "sure",
    }
)


def _proceed_phrase(query: str) -> bool:
    cleaned = " ".join(query.casefold().split())
    while cleaned and cleaned[-1] in ".!?":
        cleaned = cleaned[:-1].rstrip()
    return cleaned in _PROCEED_PHRASES


def _last_assistant_text(recent: Sequence[Any]) -> str | None:
    for message in reversed(recent):
        if _message_field(message, "role") != "assistant":
            continue
        content = _message_field(message, "content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def offered_equation_problem(query: str | None, recent: Sequence[Any]) -> str | None:
    """Solve the one equation the assistant just offered.

    ``Do it`` after ``5x^2 - 3 = -3`` has no equation of its own, and walking
    back to the previous user line re-solves the problem already finished.
    The offered line is the previous assistant message. A verified lesson
    (an ``answer`` fence), a message with several different equations, and a
    bare formula with no number (the hint of a word problem) stay with the
    model.
    """
    if not query or not recent or not _proceed_phrase(query):
        return None
    if needs_symbolic_math(query):
        return None
    assistant = _last_assistant_text(recent)
    if assistant is None or "```answer" in assistant:
        return None
    from app.modules.math.solve.extract_eq import try_extract_equations_from_text

    pairs = try_extract_equations_from_text(assistant)
    if not pairs:
        return None
    unique = {(lhs.strip(), rhs.strip()) for lhs, rhs in pairs}
    if len(unique) != 1:
        return None
    lhs, rhs = next(iter(unique))
    if not lhs or not rhs:
        return None
    problem = f"{lhs} = {rhs}"
    # A formula with no number in it (``F = ma`` in a word problem's hint) is
    # a law the problem uses, not the equation the assistant offered to solve.
    if not any(ch.isdigit() for ch in problem):
        return None
    if not needs_symbolic_math(problem):
        return None
    return problem


# "what if it was 2x + 5 = 21?" restates the problem with new numbers: the lead
# kept the equation from reading as maths at all.
_RESTATE_LEAD = re.compile(
    r"^(?:(?:and|ok(?:ay)?|so|now|then)[ ,]+)*"
    r"(?:what if (?:it|this|that|the equation|the question) (?:was|were|is)"
    r"|what about|how about|(?:now )?(?:try|do)|and)[ ,:]+",
    re.IGNORECASE,
)


def restated_math_problem(
    query: str | None,
    recent: Sequence[Any],
    *,
    blocked: Callable[[str], bool] | None = None,
) -> str | None:
    """``what about 2x + 5 = 21`` after a solved equation is that new equation.

    Only after an adjacent maths exchange, and only when what follows the lead
    is a complete equation that reads as maths on its own.
    """
    if not query or len(recent) < 2:
        return None
    line = " ".join(query.split()).rstrip("?.! ")
    match = _RESTATE_LEAD.match(line)
    if match is None or "=" not in line[match.end() :]:
        from app.modules.math.followup_what_if import changed_part_problem

        return changed_part_problem(line, recent, blocked)
    problem = line[match.end() :].strip()
    if "=" not in problem or not needs_symbolic_math(problem):
        return None
    prior = _last_user_text(recent[:-1]) if recent else None
    if _message_field(recent[-1], "role") != "assistant" or prior is None:
        return None
    if (blocked is not None and blocked(prior)) or not needs_symbolic_math(prior):
        return None
    return problem


# The claim's lead-in and check are the shared grammar (``services/student_claim``).
_CLAIM_LEAD = re.compile(
    r"^(?:(?:can|could)\s+you\s+|please\s+)?"
    r"(?:(?:check|verify|mark)\s+(?:my|this|the)\s+(?:answer|solution|result|work)\s*[:,-]?\s*"
    rf"|(?:{CLAIM_LEAD}|\bi\s+(?:get|have)\b)\s*:?\s*"
    r"|answer\s*:\s*|is\s+it\s+|is\s+|so\s+)",
    re.IGNORECASE,
)
_CLAIM_TAIL = re.compile(rf"[,\s]*(?:{CHECK})?\s*[?.!]*\s*$", re.IGNORECASE)
_CLAIM = re.compile(
    rf"(?P<var>[A-Za-z])\s*=\s*(?P<first>{FRACTION_OR_DECIMAL})"
    rf"(?P<more>(?:\s*(?:,|\bor\b|\band\b)\s*(?:(?P=var)\s*=\s*)?{FRACTION_OR_DECIMAL})*)",
)
_MORE_VALUES = re.compile(FRACTION_OR_DECIMAL)


def _claimed_values(query: str) -> tuple[str, list[str]] | None:
    """``check my answer: x = 6`` → ``("x", ["6"])``; anything more is not a bare claim."""
    text = " ".join(query.split())
    text = _CLAIM_LEAD.sub("", text, count=1)
    text = _CLAIM_TAIL.sub("", text, count=1)
    match = _CLAIM.fullmatch(text)
    if match is None or match["var"] in {"e", "E", "i", "I"}:
        return None
    rest = re.sub(rf"(?:\b{match['var']}\s*=)", " ", match["more"] or "")
    values = [match["first"], *_MORE_VALUES.findall(rest)]
    cleaned = [value.replace(" ", "") for value in values]
    if len(cleaned) > 4:
        return None
    return match["var"], cleaned


def _markdown_free(text: str) -> str:
    return text.replace("**", " ").replace("__", " ").replace("$", " ")


def _one_equation_in(text: str, variable: str) -> tuple[str, str] | None:
    """The single equation in one unknown that ``text`` states, or None."""
    from app.modules.math.solve import guess_variables
    from app.modules.math.solve.extract_eq import try_extract_equations_from_text
    from app.modules.math.tools.extractors.stated import already_solved

    pairs = {
        (lhs.strip(" *:"), rhs.strip(" *:."))
        for lhs, rhs in try_extract_equations_from_text(_markdown_free(text))
    }
    if len(pairs) != 1:
        return None
    lhs, rhs = next(iter(pairs))
    if not lhs or not rhs or already_solved(lhs, rhs):
        return None
    if guess_variables(f"{lhs} {rhs}") != [variable]:
        return None
    return lhs, rhs


def answer_claim_problem(
    query: str | None,
    recent: Sequence[Any],
    *,
    blocked: Callable[[str], bool] | None = None,
) -> str | None:
    """A typed answer (``x = 6``) checked against the problem still open in the thread.

    Solving ``x = 6`` on its own certified whatever the student typed. The
    problem is the one equation the assistant just offered (a practice
    problem), or else the equation in the user's last message. With no single
    such equation the claim is not checked here; the model answers.
    """
    if not query or not recent:
        return None
    claim = _claimed_values(query)
    if claim is None:
        return None
    variable, values = claim
    assistant = _last_assistant_text(recent)
    problem: tuple[str, str] | None = None
    if assistant is not None and "```answer" not in assistant:
        problem = _one_equation_in(assistant, variable)
    if problem is None:
        prior = _last_user_text(recent)
        if prior is None or (blocked is not None and blocked(prior)):
            return None
        problem = _one_equation_in(prior, variable)
    if problem is None:
        return None
    answer = " or ".join(f"{variable} = {value}" for value in values)
    return f"check my work:\n{problem[0]} = {problem[1]}\n{answer}"


def _last_user_text(recent: Sequence[Any]) -> str | None:
    for message in reversed(recent):
        if _message_field(message, "role") != "user":
            continue
        content = _message_field(message, "content")
        if isinstance(content, str) and content.strip():
            return content
        return None
    return None


_PRONOUN_VERBS = {
    "simplify": "simplify",
    "factor": "factor",
    "factorise": "factor",
    "factorize": "factor",
    "expand": "expand",
    "differentiate": "differentiate",
    "derive": "differentiate",
    "integrate": "integrate",
}
_PRONOUN_REQUEST = re.compile(
    r"^(?:(?:ok(?:ay)?|so|and|then|now|please|can\s+you|could\s+you|pls)[,\s]+)*"
    r"(?:(?P<verb>simplify|factori[sz]e|factor|expand|differentiate|derive|integrate)\s+"
    r"|(?:find\s+|what(?:'s|\s+is)\s+)?the\s+(?P<noun>derivative|integral)\s+of\s+)"
    r"(?:it|this|that|this\s+expression|that\s+expression|the\s+expression|the\s+result)"
    r"(?P<wrt>\s+(?:with\s+respect\s+to|wrt)\s+[a-z])?"
    r"(?:[,\s]+(?:now|please|pls|too|again))*\s*[?.!]*$",
    re.IGNORECASE,
)
_EXPRESSION_LEADS = re.compile(
    r"^(?:(?:what|how)\s+about|what\s+is|what'?s|consider|take|here'?s|here\s+is|now|and|"
    r"ok(?:ay)?|so)(?![a-z])[\s:,]*",
    re.IGNORECASE,
)


def is_pronoun_math_request(query: str) -> bool:
    """``simplify it`` / ``now integrate it``: an operation whose object is in the thread."""
    return _PRONOUN_REQUEST.fullmatch(" ".join(query.split())) is not None


# Operations that keep the value of what they act on. After "derivative of
# x^3" (answer 3x^2), "integrate it" could mean either, so it is not resolved.
_SAME_VALUE_OPERATIONS = frozenset({"simplify", "expand", "factor"})


def _expression_in(text: str) -> str | None:
    """The one expression a message is about: ``expand (x+1)^2`` → ``(x+1)^2``."""
    from app.modules.math.tools.expr_rewrite import math_expr_or_none
    from app.modules.math.tools.extract import extract_math_intent

    if "=" in text or "<" in text or ">" in text:
        return None
    intent = extract_math_intent(text)
    if intent is not None:
        if intent.kind not in {"calculus", "arithmetic"} or not intent.expr:
            return None
        if intent.integral_lower is not None or intent.evaluation_point is not None:
            return None
        if intent.kind == "calculus" and (
            intent.school_op is not None or intent.operation not in _SAME_VALUE_OPERATIONS
        ):
            return None
        return intent.expr
    body = " ".join(text.split()).strip().rstrip("?.!")
    while True:
        stripped = _EXPRESSION_LEADS.sub("", body, count=1)
        if stripped == body:
            break
        body = stripped
    expression = math_expr_or_none(body)
    if expression is None or not re.search(r"[A-Za-z0-9]", expression):
        return None
    return expression if re.search(r"[-+*/^()]", expression) else None


def pronoun_math_problem(
    query: str | None,
    recent: Sequence[Any],
    *,
    blocked: Callable[[str], bool] | None = None,
) -> str | None:
    """``simplify it`` → ``simplify (x^2-1)/(x-1)``, from the user's last expression.

    Read alone, "it" was the product ``i t`` and got a verified card. With no
    expression in the user's last message the request is not resolved, and
    the model answers it.
    """
    if not query:
        return None
    match = _PRONOUN_REQUEST.fullmatch(" ".join(query.split()))
    if match is None:
        return None
    verb_word = match["verb"]
    if verb_word is not None:
        verb = _PRONOUN_VERBS[verb_word.lower()]
    else:
        verb = "differentiate" if match["noun"].lower() == "derivative" else "integrate"
    prior: str | None = None
    for message in reversed(recent):
        if _message_field(message, "role") != "user":
            continue
        content = _message_field(message, "content")
        if not isinstance(content, str) or not content.strip():
            return None
        if is_pronoun_math_request(content):
            # "simplify it" then "now factor it": the same expression.
            continue
        prior = content
        break
    if prior is None or (blocked is not None and blocked(prior)):
        return None
    expression = _expression_in(prior)
    if expression is None:
        return None
    return f"{verb} {expression}{match['wrt'] or ''}"


def readable_standalone_answer(content: str) -> str | None:
    """Keep only a complete, standalone owned answer as math, never fenced payloads.

    General prose/mixed fences retain the existing prompt-history stripping path.
    No truncation or symbolic re-evaluation: preserve a supported answer body intact.
    """
    lines = content.strip().splitlines()
    if len(lines) < 3 or lines[0] != "```answer" or lines[-1] != "```":
        return None
    # The value only: never the card's protocol lines (``verified: true``).
    body = answer_fence_value("\n".join(lines[1:-1]))
    if not body or len(body) > 4000 or "`" in body or "$" in body:
        return None
    # JSON/tool data is not a mathematical answer. Preserve such unfamiliar
    # content through neither this narrow exception nor a raw owned fence.
    if body.startswith(("{", "[")):
        return None
    return f"Previous result:\n\\[\n{body}\n\\]"
