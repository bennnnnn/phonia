"""Subject formatting for a short continuation of the prior exchange.

"Another" is not physics. When the current line is only a continuation, the
subject comes from the nearest earlier exchange that is not itself a
continuation. A new topic does not inherit that subject.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.core.readings import reading
from app.modules.turn_reading.routing import is_lightweight_chat_turn
from app.modules.turn_reading.writing_kind import is_writing_deliverable_request
from app.services.problem_followup import adjacent_problem, message_role_content
from app.services.text_normalize import collapse_ws

_MAX_CHARS = 80
_POLITE_PREFIXES = ("please ", "can you ", "could you ", "would you ", "will you ")
_PHRASES = frozenset(
    {
        "another",
        "another one",
        "another problem",
        "another such question",
        "another harder",
        "another trickier",
        "give me another",
        "give me a harder one",
        "give me a trickier one",
        "one more",
        "one more problem",
        "next",
        "next one",
        "again",
        "do it again",
        "once more",
        "same again",
        "harder",
        "trickier",
        "easier",
        "harder one",
        "trickier one",
        "same but harder",
        "same but easier",
        "a harder one",
        "a trickier one",
        "make it harder",
        "make it trickier",
        "change chapter",
        "change the chapter",
        "next chapter",
        "show me",
        "show me how",
        "show the steps",
        "show me the steps",
        "how",
        "how so",
        "why",
        "why not",
        "explain",
        "explain how",
        "explain it",
        "explain this",
        "go on",
        "continue",
        "keep going",
        "carry on",
        "keep writing",
        "continue writing",
        "continue the story",
        "continue from there",
        "continue where you left off",
        "finish it",
        "fix it",
        "fix that",
        "fix this",
    }
)
# Of those, the ones that ask the last reply to go on from where it stopped.
_RESUME_PHRASES = frozenset(
    {
        "go on",
        "continue",
        "keep going",
        "carry on",
        "keep writing",
        "continue writing",
        "continue the story",
        "continue from there",
        "continue where you left off",
        "finish it",
    }
)
_FIX_PHRASES = frozenset({"fix it", "fix that", "fix this"})
# A fresh problem of the same kind, not the last one again. "Another way" or
# "another method" asks about the same problem, so those stay out.
_NEW_PROBLEM_PHRASES = frozenset(
    {
        "another",
        "another one",
        "another problem",
        "another such question",
        "another harder",
        "another trickier",
        "give me another",
        "give me a harder one",
        "give me a trickier one",
        "one more",
        "one more problem",
        "next",
        "next one",
        "harder",
        "trickier",
        "easier",
        "harder one",
        "trickier one",
        "same but harder",
        "same but easier",
        "a harder one",
        "a trickier one",
        "make it harder",
        "make it trickier",
    }
)
_NEW_PROBLEM_RE = re.compile(
    r"(?:(?:no|i said|i asked for|i want|give me|show me|do|try)\s+)*"
    r"(?:another|one more|a new|a different|new|different|next)"
    r"(?:\s+(?:harder|easier|trickier|similar|practice))?"
    r"(?:\s+(?:one|example|problem|question|exercise|exercises|examples|problems|questions))?"
)
_STATISTICS_CUES = (
    "standard deviation",
    "z-score",
    "z score",
    "p-value",
    "p value",
    "confidence interval",
    "normal distribution",
    "null hypothesis",
    "sample mean",
    "variance",
)
# Biology has no solver: these name a biology line, for its presentation hint and its
# follow-up questions.
BIOLOGY_CUES = (
    "dilution",
    "punnett",
    "hardy-weinberg",
    "hardy weinberg",
    "allele",
    "enzyme kinetics",
    "michaelis",
    "population growth",
    "photosynthesis",
    "mitosis",
)


def is_pure_continuation(text: str | None) -> bool:
    """True only for an exact continuation phrase, not a new question."""
    if not text:
        return False
    collapsed = collapse_ws(text)
    if not collapsed or len(collapsed) > _MAX_CHARS:
        return False
    if is_writing_deliverable_request(collapsed):
        return False
    if is_lightweight_chat_turn(collapsed):
        return False
    return _phrase(collapsed) in _PHRASES


def is_resume_request(text: str | None) -> bool:
    """True for "continue" / "keep going": the last reply goes on, it does not restart."""
    return is_pure_continuation(text) and _phrase(text or "") in _RESUME_PHRASES


def works_on_last_reply(text: str | None) -> bool:
    """True for "continue" or "fix that": the last reply is the whole subject of the turn."""
    return is_resume_request(text) or (
        is_pure_continuation(text) and _phrase(text or "") in _FIX_PHRASES
    )


def is_new_problem_request(text: str | None) -> bool:
    """True when a short line asks for a new problem like the last one.

    "One more" after a solved problem wants a different problem, so the reply
    must not replay or restate the previous answer.
    """
    if not text:
        return False
    collapsed = collapse_ws(text)
    if not collapsed or len(collapsed) > _MAX_CHARS or _has_digit(collapsed):
        return False
    phrase = _phrase(collapsed).replace(",", "")
    phrase = " ".join(phrase.split())
    return phrase in _NEW_PROBLEM_PHRASES or _NEW_PROBLEM_RE.fullmatch(phrase) is not None


def classify_presentation_subject(text: str | None) -> str | None:
    """Subject of this text, or None when it does not name one.

    Which STEM subject a line is, is ``detect_subject``'s alone: the prompt pack follows
    the subject whose solver answers it. "h = 20t - 5t^2, find the maximum height" is
    solved by maths and got physics' pack when this asked physics first (code-health
    audit DUP-05). Statistics and biology have no solver: their cues name only a line no
    solver claimed.
    """
    if not text or not text.strip():
        return None
    from app.modules.turn_reading.coding import has_code_syntax
    from app.services.subjects.dispatch import detect_subject

    subject = detect_subject(text)
    # Pasted code gets code ink: `i <= 3` is a loop bound, `variance` a variable.
    if subject is not None or has_code_syntax(text):
        return subject
    if _has_phrase(text, _STATISTICS_CUES):
        return "statistics"
    if _has_digit(text) and _has_phrase(text, BIOLOGY_CUES):
        return "biology"
    return None


def blocks_math_followup(text: str) -> bool:
    """Physics and chemistry problems are not replayed through the math solver."""
    from app.services.subjects.dispatch import detect_subject

    return detect_subject(text) in {"physics", "chemistry"}


def chemistry_working_followup_problem(query: str | None, recent: Sequence[Any]) -> str | None:
    """Re-solve the adjacent chemistry problem when this line only continues it.

    A later math or physics question is its own text, so it does not come back here.
    """
    if not is_pure_continuation(query) or is_new_problem_request(query):
        return None
    own = classify_presentation_subject(query)
    if own in {"math", "physics"}:
        return None
    from app.services.subjects.registry import subject_adapter

    return adjacent_problem(recent, subject_adapter("chemistry").asks)


def exchange_pairs(messages: Sequence[Any]) -> tuple[tuple[str, str], ...]:
    """The user and assistant lines of an exchange as ``(role, content)`` pairs."""
    pairs: list[tuple[str, str]] = []
    for message in messages:
        role, content = message_role_content(message)
        if role in {"user", "assistant"} and content is not None:
            pairs.append((role, content))
    return tuple(pairs)


@reading(declined=None)
def effective_presentation_subject(
    query: str | None,
    prior_messages: Sequence[tuple[str, str]] | None = None,
) -> str | None:
    """Subject hints for this turn, including a pure continuation.

    A reading (``core/readings``): pass ``prior_messages`` as ``exchange_pairs`` gives it.
    """
    if not query or not query.strip():
        return None
    own = classify_presentation_subject(query)
    if own:
        return own
    if is_pure_continuation(query) or is_new_problem_request(query):
        return _continuation_subject(prior_messages or ())
    from app.services.subjects.registry import subject_adapter

    if subject_adapter("chemistry").followups.continues(query, prior_messages or ()):
        return "chemistry"
    if subject_adapter("physics").followups.continues(query, prior_messages or ()):
        return "physics"
    return None


def _phrase(text: str) -> str:
    cleaned = collapse_ws(text).lower().strip(" \"'`")
    cleaned = cleaned.strip(".,!?:;")
    changed = True
    while changed:
        changed = False
        for prefix in _POLITE_PREFIXES:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                changed = True
    if cleaned.endswith(" please"):
        cleaned = cleaned[: -len(" please")].strip()
    return cleaned.strip(".,!?:;")


def _continuation_subject(messages: Sequence[tuple[str, str]]) -> str | None:
    index = len(messages) - 1
    while index >= 0:
        role, content = messages[index]
        if role != "user":
            index -= 1
            continue
        if is_pure_continuation(content) or is_new_problem_request(content):
            index -= 1
            continue
        subject = classify_presentation_subject(content)
        if subject:
            return subject
        for later_role, later in messages[index + 1 :]:
            if later_role == "user":
                break
            if later_role == "assistant":
                subject = classify_presentation_subject(later)
                if subject:
                    return subject
        return None
    return None


def _has_digit(text: str) -> bool:
    return any(char.isdigit() for char in text)


def _has_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _contains_phrase(haystack: str, phrase: str) -> bool:
    lower = haystack.lower()
    start = 0
    size = len(phrase)
    while True:
        index = lower.find(phrase, start)
        if index < 0:
            return False
        before = lower[index - 1] if index else " "
        after = lower[index + size] if index + size < len(lower) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = index + 1
